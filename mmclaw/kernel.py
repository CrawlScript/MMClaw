import threading
import traceback
import queue
import json
import re

JSON_PARSE_RETRIES = 1
import time
import subprocess
import random
from datetime import datetime, timezone
from pathlib import Path
from .providers import Engine
from .tools import ShellTool, AsyncShellTool, FileTool, TimerTool, SessionTool, UpgradeTool, BrowserTool
from .config import _find_file_icase
from .memory import FileMemory, StatelessMemory
from .watcher import WatcherManager


class StopRequested(Exception):
    """Raised inside the chat worker when the user sends /stop."""
    pass


class HeartbeatManager:
    HEARTBEAT_DIR = None
    CONFIG_FILE   = None
    LOG_FILE      = None
    SKILLS_DIR    = None

    def __init__(self, task_queue: queue.Queue, connector):
        self.task_queue = task_queue
        self.connector  = connector
        self._running   = set()  # skill names with active threads

    def start(self):
        self.HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)

        cfg = self._load_config()
        for skill_name, opts in cfg.items():
            self._start_skill(skill_name, opts)

        # Queue discovery messages for skills not yet in config
        self._queue_discoveries(cfg)

        # Watch config for new entries written by the AI
        threading.Thread(target=self._watch_config, daemon=True).start()

    def _load_config(self) -> dict:
        if not self.CONFIG_FILE.exists():
            return {}
        try:
            return json.loads(self.CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[!] HeartbeatManager: failed to load config: {e}")
            return {}

    def _start_skill(self, skill_name: str, opts: dict):
        if skill_name in self._running:
            return
        if not opts.get("enabled", True):
            return
        interval_seconds = max(10, int(opts.get("interval_seconds", 1800)))
        heartbeat_file = _find_file_icase(self.SKILLS_DIR / skill_name, "heartbeat.md")
        if not heartbeat_file:
            print(f"[!] HeartbeatManager: no heartbeat.md for '{skill_name}', skipping.")
            return
        is_new = self._last_run(skill_name) is None
        threading.Thread(
            target=self._run,
            args=(skill_name, heartbeat_file, interval_seconds, is_new),
            daemon=True,
        ).start()
        self._running.add(skill_name)
        print(f"[*] HeartbeatManager: '{skill_name}' every {interval_seconds}s")

    def _queue_discoveries(self, existing_cfg: dict):
        if not self.SKILLS_DIR.exists():
            return
        for skill_dir in sorted(self.SKILLS_DIR.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_name = skill_dir.name
            if skill_name in existing_cfg:
                continue
            heartbeat_file = _find_file_icase(skill_dir, "heartbeat.md")
            if not heartbeat_file:
                continue
            try:
                content = heartbeat_file.read_text(encoding="utf-8")
                msg = (
                    f"[HEARTBEAT_DISCOVER: {skill_name}]\n"
                    f"{content}\n\n"
                    f"The above is the heartbeat.md for skill '{skill_name}'. "
                    f"If the above heartbeat.md explicitly states an interval (e.g. 'every 30s', 'every 1 minute'), "
                    f"use that exact value converted to seconds. "
                    f"Only choose your own value if no interval is specified. Minimum 10 seconds. "
                    f"Then read {self.CONFIG_FILE}, add an entry for '{skill_name}' "
                    f"with {{\"enabled\": true, \"interval_seconds\": <value>}}, "
                    f"and write the updated config back. "
                    f"Do NOT send any message to the user. Stay completely silent."
                )
                self.task_queue.put(msg)
                print(f"[*] HeartbeatManager: queued discovery for '{skill_name}'")
            except Exception as e:
                print(f"[!] HeartbeatManager: discovery failed for '{skill_name}': {e}")

    def _watch_config(self):
        """Poll config file for new entries and start threads for them."""
        last_mtime = 0
        while True:
            time.sleep(5)
            try:
                if not self.CONFIG_FILE.exists():
                    continue
                mtime = self.CONFIG_FILE.stat().st_mtime
                if mtime <= last_mtime:
                    continue
                last_mtime = mtime
                cfg = self._load_config()
                for skill_name, opts in cfg.items():
                    if skill_name not in self._running:
                        self._start_skill(skill_name, opts)
            except Exception as e:
                print(f"[!] HeartbeatManager: watcher error: {e}")

    def _last_run(self, skill_name: str):
        if not self.LOG_FILE.exists():
            return None
        last = None
        try:
            for line in self.LOG_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("skill") == skill_name:
                    last = entry.get("fired_at")
        except Exception:
            pass
        if last:
            try:
                return datetime.fromisoformat(last)
            except Exception:
                pass
        return None

    def _log(self, skill_name: str):
        entry = {
            "skill":    skill_name,
            "fired_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _run(self, skill_name: str, heartbeat_file: Path, interval_secs: int, is_new: bool):
        if is_new:
            wait = 0
        else:
            last = self._last_run(skill_name)
            if last:
                elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                wait = max(0, interval_secs - elapsed)
                if wait > 0:
                    print(f"[*] HeartbeatManager: '{skill_name}' resumes in {int(wait)}s")
            else:
                wait = interval_secs

        time.sleep(wait)

        while True:
            try:
                content = heartbeat_file.read_text(encoding="utf-8")
                self.task_queue.put(f"[HEARTBEAT: {skill_name}]\n{content}")
                self._log(skill_name)
                print(f"[*] HeartbeatManager: queued heartbeat for '{skill_name}'")
            except Exception as e:
                print(f"[!] HeartbeatManager: error for '{skill_name}': {e}")
            time.sleep(interval_secs)


class CronManager:
    CRON_DIR  = None
    JOBS_FILE = None

    def __init__(self, cron_queue: queue.Queue):
        self.cron_queue = cron_queue
        self._scheduler = None

    def start(self):
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except ImportError:
            print("[!] CronManager: apscheduler not installed. Run: pip install apscheduler")
            return
        self.CRON_DIR.mkdir(parents=True, exist_ok=True)
        self._scheduler = BackgroundScheduler()
        self._scheduler.start()
        jobs = self._load_jobs()
        for job in jobs:
            self._schedule_job(job)
        print(f"[*] CronManager: started with {len(jobs)} job(s)")

    def _load_jobs(self) -> list:
        if not self.JOBS_FILE.exists():
            return []
        jobs = []
        try:
            for line in self.JOBS_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    jobs.append(json.loads(line))
        except Exception as e:
            print(f"[!] CronManager: failed to load jobs: {e}")
        return jobs

    def _save_jobs(self, jobs: list):
        self.CRON_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.JOBS_FILE, "w", encoding="utf-8") as f:
            for job in jobs:
                f.write(json.dumps(job, ensure_ascii=False) + "\n")

    def _make_trigger(self, cron: str):
        from apscheduler.triggers.cron import CronTrigger
        fields = cron.strip().split()
        if len(fields) == 5:
            return CronTrigger.from_crontab(cron)
        elif len(fields) == 6:
            s, mi, h, d, mo, dow = fields
            return CronTrigger(second=s, minute=mi, hour=h, day=d, month=mo, day_of_week=dow)
        else:
            raise ValueError(f"Expected 5 or 6 fields, got {len(fields)}")

    def _schedule_job(self, job: dict):
        if self._scheduler is None:
            return
        name = job["name"]
        try:
            trigger = self._make_trigger(job["cron"])
            self._scheduler.add_job(
                self._fire,
                trigger=trigger,
                args=[name, job["prompt"]],
                id=name,
                replace_existing=True,
            )
        except Exception as e:
            print(f"[!] CronManager: failed to schedule '{name}': {e}")

    def _fire(self, name: str, prompt: str):
        self.cron_queue.put(f"[CRON: {name}]\n{prompt}")
        print(f"[*] CronManager: fired '{name}'")

    def create(self, name: str, cron: str, prompt: str) -> str:
        if self._scheduler is None:
            return "Error: CronManager not started (apscheduler missing)."
        try:
            self._make_trigger(cron)
        except Exception as e:
            return f"Error: invalid cron expression '{cron}': {e}"
        jobs = self._load_jobs()
        if any(j["name"] == name for j in jobs):
            return f"Error: job '{name}' already exists. Delete it first."
        job = {
            "name": name,
            "cron": cron,
            "prompt": prompt,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        jobs.append(job)
        self._save_jobs(jobs)
        self._schedule_job(job)
        return f"Cron job '{name}' created ({cron})."

    def delete(self, indices) -> str:
        if isinstance(indices, int):
            indices = [indices]
        else:
            indices = [int(i) for i in indices]
        jobs = self._load_jobs()
        invalid = [i for i in indices if i < 0 or i >= len(jobs)]
        if invalid:
            return f"Error: indices {invalid} out of range (0-{len(jobs)-1})."
        to_remove = [jobs[i]["name"] for i in indices]
        new_jobs = [j for i, j in enumerate(jobs) if i not in set(indices)]
        self._save_jobs(new_jobs)
        if self._scheduler:
            for name in to_remove:
                try:
                    self._scheduler.remove_job(name)
                except Exception:
                    pass
        remaining = "\n".join(f"[{i}] {j['name']} | {j['cron']} | {j['prompt']}" for i, j in enumerate(new_jobs))
        return f"Deleted {len(indices)} job(s). Remaining:\n{remaining or '(none)'}"

    def list_jobs(self) -> str:
        jobs = self._load_jobs()
        if not jobs:
            return "No cron jobs."
        lines = [f"[{i}] ({j['name']}) {j['cron']} — {j['prompt']}" for i, j in enumerate(jobs)]
        return "\n".join(lines)


class MMClaw(object):
    def __init__(self, config, connector, system_prompt, use_stateless_arg_connector=False, stateless_use_global_memory=False):
        self.config = config
        self.engine = Engine(config)
        self.connector = connector
        self.memory = StatelessMemory(system_prompt, use_global_memory=stateless_use_global_memory) if use_stateless_arg_connector else FileMemory(system_prompt)
        self.connector.file_saver = self.memory.save_file
        self.chat_queue = queue.Queue()
        self.heartbeat_queue = queue.Queue()
        self.cron_queue = queue.Queue()
        self.debug = config.get("debug", False)
        self.use_stateless_arg_connector = use_stateless_arg_connector

        threading.Thread(target=self._worker, args=(self.chat_queue, "chat"), daemon=True).start()
        threading.Thread(target=self._worker, args=(self.heartbeat_queue, "heartbeat"), daemon=True).start()
        threading.Thread(target=self._worker, args=(self.cron_queue, "cron"), daemon=True).start()

        if not use_stateless_arg_connector:
            self.heartbeat = HeartbeatManager(self.heartbeat_queue, self.connector)
            self.heartbeat.start()

            self.cron = CronManager(self.cron_queue)
            self.cron.start()

            self.watcher = WatcherManager(self.chat_queue)
            self.watcher.start()

        # /stop support
        self._stop_event  = threading.Event()
        self._current_proc = None
        self._proc_lock    = threading.Lock()

    # ------------------------------------------------------------------
    # /stop support
    # ------------------------------------------------------------------

    def stop(self):
        """Cancel the current chat job immediately."""
        self._stop_event.set()
        with self._proc_lock:
            if self._current_proc is not None:
                try:
                    self._current_proc.kill()
                except Exception:
                    pass
        self.connector.stop_typing()
        self.connector.send("✋ Job cancelled.")

    def _check_stop(self):
        if self._stop_event.is_set():
            raise StopRequested()

    def _ask_with_stop(self, messages):
        """Run engine.ask() in a daemon thread, interruptible by the stop event."""
        result_box = [None]
        error_box  = [None]
        done       = threading.Event()

        def _ask():
            try:
                result_box[0] = self.engine.ask(messages)
            except Exception as e:
                error_box[0] = e
            finally:
                done.set()

        threading.Thread(target=_ask, daemon=True).start()
        while not done.wait(timeout=0.2):
            self._check_stop()
        self._check_stop()  # one final check after completion
        if error_box[0]:
            raise error_box[0]
        return result_box[0]

    def _shell_execute_with_stop(self, command):
        """Execute a shell command, killable via the stop event."""
        import locale
        try:
            proc = subprocess.Popen(
                command, shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as e:
            return f"Error executing command: {str(e)}"

        with self._proc_lock:
            self._current_proc = proc

        deadline = time.time() + ShellTool.TIMEOUT
        try:
            while proc.poll() is None:
                if self._stop_event.is_set():
                    proc.kill()
                    proc.wait()
                    raise StopRequested()
                if time.time() > deadline:
                    proc.kill()
                    proc.wait()
                    return f"Error executing command: timed out after {ShellTool.TIMEOUT}s"
                time.sleep(0.1)
        finally:
            with self._proc_lock:
                if self._current_proc is proc:
                    self._current_proc = None

        stdout = proc.stdout.read()
        stderr = proc.stderr.read()
        output = stdout if proc.returncode == 0 else stderr
        try:
            output = output.decode('utf-8')
        except UnicodeDecodeError:
            output = output.decode(locale.getpreferredencoding(False), errors='replace')
        return f"Return Code {proc.returncode}:\n{output}"

    def _wait_with_stop(self, seconds):
        """Sleep for N seconds, interruptible by the stop event."""
        try:
            secs = float(seconds)
        except Exception as e:
            return f"Timer error: {str(e)}"
        end = time.time() + secs
        while time.time() < end:
            if self._stop_event.is_set():
                raise StopRequested()
            time.sleep(0.1)
        return f"Waited for {secs} seconds."

    # ------------------------------------------------------------------

    def _extract_json(self, text):
        """Finds and parses the first JSON block from text."""
        # Strip markdown code blocks if present
        text = re.sub(r'```json\s*(.*?)\s*```', r'\1', text, flags=re.DOTALL)
        
        try:
            start_idx = text.find('{')
            if start_idx != -1:
                # Use JSONDecoder to find the first complete JSON object
                decoder = json.JSONDecoder()
                obj, _ = decoder.raw_decode(text[start_idx:])
                return obj
        except Exception as e:
            print(f"[!] _extract_json failed: {e}\n    text: {repr(text[:200])}")
            return None
        return None

    def _worker(self, q: queue.Queue, mode: str):
        while True:
            user_text = q.get()
            if user_text is None:
                break

            is_background = mode != "chat"

            if mode == "heartbeat":
                silent_tools   = True
                silent_content = user_text.startswith("[HEARTBEAT_DISCOVER:")
                history = [{"role": "user", "content": user_text}]
            elif mode == "cron":
                silent_tools   = True
                silent_content = False
                history = [{"role": "user", "content": user_text}]
            else:  # chat
                self._stop_event.clear()
                silent_tools   = isinstance(user_text, str) and user_text.startswith("[WATCHER:")
                silent_content = False
                if self.use_stateless_arg_connector:
                    history = [{"role": "user", "content": user_text}]
                else:
                    self.memory.add("user", user_text)

            self.connector.start_typing()
            try:
                json_retries_left = JSON_PARSE_RETRIES
                while True:
                    if not is_background:
                        self._check_stop()

                    # Refresh system prompt before every call to pick up new skills or context changes
                    from .config import ConfigManager
                    new_prompt = ConfigManager.get_full_prompt()
                    self.memory.update_system_prompt(new_prompt)

                    use_local_history = is_background or self.use_stateless_arg_connector
                    ask_messages = [self.memory.get_all()[0]] + history if use_local_history else self.memory.get_all()

                    if is_background:
                        response_msg = self.engine.ask(ask_messages)
                    else:
                        response_msg = self._ask_with_stop(ask_messages)
                    raw_text = response_msg.get("content", "")

                    if use_local_history:
                        history.append({"role": "assistant", "content": raw_text})
                    else:
                        self.memory.add("assistant", raw_text)

                    data = self._extract_json(raw_text)
                    # print(f"[D] data={repr(data)}")
                    if not data:
                        if json_retries_left > 0:
                            json_retries_left -= 1
                            correction = "Your response was not valid JSON. Please respond with valid JSON only."
                            if use_local_history:
                                history.append({"role": "user", "content": correction})
                            else:
                                self.memory.add("user", correction)
                            continue
                        if not silent_content:
                            self.connector.send(raw_text)
                        break

                    if data.get("content"):
                        content = data["content"]
                        if not isinstance(content, str):
                            try:
                                content = json.dumps(content, ensure_ascii=False)
                            except Exception:
                                content = "[Error: unexpected content format]"
                        if not silent_content:
                            self.connector.send(content)

                    tools = data.get("tools", [])
                    if not tools:
                        break

                    session_reset = False
                    for tool in tools:
                        if not is_background:
                            self._check_stop()

                        name = tool.get("name")
                        args = tool.get("args", {})

                        print(f"    [Tool Call: {name}]")
                        if self.debug:
                            print(f"    Args: {json.dumps(args)}")

                        result = ""
                        if name == "shell_execute":
                            if not silent_tools:self.connector.send(f"🐚 Shell: `{args.get('command')}`")
                            if is_background:
                                result = ShellTool.execute(args.get("command"))
                            else:
                                result = self._shell_execute_with_stop(args.get("command"))
                        elif name == "shell_async":
                            if not silent_tools:self.connector.send(f"🚀 Async Shell: `{args.get('command')}`")
                            result = AsyncShellTool.execute(args.get("command"))
                        elif name == "file_read":
                            if not silent_tools:self.connector.send(f"📖 Read: `{args.get('path')}`")
                            result = FileTool.read(args.get("path"))
                        elif name == "file_write":
                            if not silent_tools:self.connector.send(f"💾 Write: `{args.get('path')}`")
                            result = FileTool.write(args.get("path"), args.get("content"))
                        elif name == "file_upload":
                            if not silent_tools:self.connector.send(f"📤 Upload: `{args.get('path')}`")
                            self.connector.send_file(args.get("path"))
                            result = f"File {args.get('path')} sent."
                        elif name == "wait":
                            if not silent_tools:self.connector.send(f"⏳ Waiting {args.get('seconds')}s...")
                            if is_background:
                                result = TimerTool.wait(args.get("seconds"))
                            else:
                                result = self._wait_with_stop(args.get("seconds"))
                        elif name == "reset_session":
                            self.memory.reset()
                            if not silent_tools:self.connector.send("✨ Session reset! Starting fresh.")
                            result = "Success: Session history cleared."
                            session_reset = True
                            break
                        elif name == "memory_add":
                            if not silent_tools:self.connector.send(f"🧠 Memorize: `{args.get('memory', '')}`")
                            result = self.memory.global_memory_add(args.get("memory", ""))
                        elif name == "memory_list":
                            if not silent_tools:self.connector.send("🧠 Listing global memories...")
                            result = self.memory.global_memory_list()
                        elif name == "memory_delete":
                            indices = args.get("indices", args.get("index", -1))
                            if isinstance(indices, list):
                                indices = [int(i) for i in indices]
                            else:
                                indices = int(indices)
                            if not silent_tools:self.connector.send(f"🧠 Delete memory {indices}")
                            result = self.memory.global_memory_delete(indices)
                        elif name == "browser_start":
                            if not silent_tools:self.connector.send("🌐 Starting browser...")
                            user_data_dir = self.config.get("browser", {}).get("data_dir")
                            result = BrowserTool.start(user_data_dir=user_data_dir)
                        elif name == "browser_stop":
                            if not silent_tools:self.connector.send("🌐 Stopping browser...")
                            result = BrowserTool.stop()
                        elif name == "browser_navigate":
                            if not silent_tools:self.connector.send(f"🌐 Navigate: `{args.get('url')}`")
                            result = BrowserTool.navigate(args.get("url"))
                        elif name == "browser_click":
                            if not silent_tools:self.connector.send(f"🌐 Click: `{args.get('selector')}`")
                            result = BrowserTool.click(args.get("selector"))
                        elif name == "browser_fill":
                            if not silent_tools:self.connector.send(f"🌐 Fill: `{args.get('selector')}`")
                            result = BrowserTool.fill(args.get("selector"), args.get("text", ""))
                        elif name == "browser_get_text":
                            if not silent_tools:self.connector.send(f"🌐 Get text: `{args.get('selector', 'body')}`")
                            result = BrowserTool.get_text(args.get("selector"))
                        elif name == "browser_screenshot":
                            if not silent_tools:self.connector.send("🌐 Screenshot...")
                            result = BrowserTool.screenshot(args.get("path"))
                            if result.startswith("OK:"):
                                if not silent_tools:self.connector.send_file(result[4:].strip())
                        elif name == "cron_create":
                            if not silent_tools:self.connector.send(f"⏰ Cron create: `{args.get('name')}`")
                            result = self.cron.create(args.get("name"), args.get("cron"), args.get("prompt"))
                        elif name == "cron_delete":
                            indices = args.get("indices", args.get("index", -1))
                            if isinstance(indices, list):
                                indices = [int(i) for i in indices]
                            else:
                                indices = int(indices)
                            if not silent_tools:self.connector.send(f"⏰ Cron delete: {indices}")
                            result = self.cron.delete(indices)
                        elif name == "cron_list":
                            if not silent_tools:self.connector.send("⏰ Listing cron jobs...")
                            result = self.cron.list_jobs()
                        elif name == "upgrade":
                            if not silent_tools:self.connector.send("⬆️ Upgrading MMClaw... (this is tricky — there's no notification when it's done. Please wait a moment, then ask me for my version number to confirm the upgrade succeeded.)")
                            result = UpgradeTool.upgrade()  # restarts process on success; only returns on failure
                            if not silent_tools:self.connector.send(f"❌ Upgrade failed: {result}")

                        if self.debug:
                            print(f"\n    [Tool Output: {name}]\n    {result}\n")
                        tool_output = f"Tool Output ({name}):\n{result}"
                        if use_local_history:
                            history.append({"role": "user", "content": tool_output})
                        else:
                            self.memory.add("user", tool_output)

                    if session_reset:
                        break

            except StopRequested:
                pass  # Job was cancelled cleanly; no further action needed
            except Exception as e:
                print(f"[!] Worker error: {e}")
                traceback.print_exc()
            finally:
                self.connector.stop_typing()
                q.task_done()

    def handle(self, text):
        if isinstance(text, list):
            self.chat_queue.put(text)
            return
        if text.strip() == "/stop":
            self.stop()
            return
        if text.strip() == "/new":
            self.memory.reset()
            self.connector.send("✨ Session reset! Starting fresh.")
            return
        if not self.use_stateless_arg_connector and random.random() < 0.15:
            self.connector.send("💡 Tip: type /stop at any time to cancel the current job.")
        self.chat_queue.put(text)

    def run(self, stop_on_auth=False):
        try:
            self.connector.listen(self.handle, stop_on_auth=stop_on_auth)
        except TypeError:
            self.connector.listen(self.handle)
