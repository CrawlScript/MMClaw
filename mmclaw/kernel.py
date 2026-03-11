import threading
import traceback
import queue
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from .providers import Engine
from .tools import ShellTool, AsyncShellTool, FileTool, TimerTool, SessionTool, UpgradeTool, BrowserTool
from .memory import FileMemory
from .watcher import WatcherManager


class HeartbeatManager:
    HEARTBEAT_DIR = Path.home() / ".mmclaw" / "heartbeat"
    CONFIG_FILE   = Path.home() / ".mmclaw" / "heartbeat" / "heartbeat-config.json"
    LOG_FILE      = Path.home() / ".mmclaw" / "heartbeat" / "heartbeat-log.jsonl"
    SKILLS_DIR    = Path.home() / ".mmclaw" / "skills"

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
        heartbeat_file = self.SKILLS_DIR / skill_name / "heartbeat.md"
        if not heartbeat_file.exists():
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
            heartbeat_file = skill_dir / "heartbeat.md"
            if not heartbeat_file.exists():
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


class MMClaw(object):
    def __init__(self, config, connector, system_prompt):
        self.config = config
        self.engine = Engine(config)
        self.connector = connector
        self.memory = FileMemory(system_prompt)
        self.connector.file_saver = self.memory.save_file
        self.chat_queue = queue.Queue()
        self.heartbeat_queue = queue.Queue()
        self.debug = config.get("debug", False)

        threading.Thread(target=self._worker, args=(self.chat_queue, False), daemon=True).start()
        threading.Thread(target=self._worker, args=(self.heartbeat_queue, True), daemon=True).start()

        self.heartbeat = HeartbeatManager(self.heartbeat_queue, self.connector)
        self.heartbeat.start()

        self.watcher = WatcherManager(self.chat_queue)
        self.watcher.start()


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

    def _worker(self, q: queue.Queue, is_heartbeat: bool):
        while True:
            user_text = q.get()
            if user_text is None:
                break

            if is_heartbeat:
                silent = "all" if user_text.startswith("[HEARTBEAT_DISCOVER:") else "tools"
                history = [{"role": "user", "content": user_text}]
            else:
                silent = False
                self.memory.add("user", user_text)

            self.connector.start_typing()
            try:
                while True:
                    # Refresh system prompt before every call to pick up new skills or context changes
                    from .config import ConfigManager
                    new_prompt = ConfigManager.get_full_prompt(mode=self.connector.__class__.__name__.lower().replace("connector", ""))
                    self.memory.update_system_prompt(new_prompt)

                    ask_messages = [self.memory.get_all()[0]] + history if is_heartbeat else self.memory.get_all()

                    response_msg = self.engine.ask(ask_messages)
                    raw_text = response_msg.get("content", "")

                    if is_heartbeat:
                        history.append({"role": "assistant", "content": raw_text})
                    else:
                        self.memory.add("assistant", raw_text)

                    data = self._extract_json(raw_text)
                    # print(f"[D] data={repr(data)}")
                    if not data:
                        if silent != "all":
                            self.connector.send(raw_text)
                        break

                    if data.get("content"):
                        content = data["content"]
                        if not isinstance(content, str):
                            try:
                                content = json.dumps(content, ensure_ascii=False)
                            except Exception:
                                content = "[Error: unexpected content format]"
                        if silent != "all":
                            self.connector.send(content)

                    tools = data.get("tools", [])
                    if not tools:
                        break

                    session_reset = False
                    for tool in tools:
                        name = tool.get("name")
                        args = tool.get("args", {})

                        print(f"    [Tool Call: {name}]")
                        if self.debug:
                            print(f"    Args: {json.dumps(args)}")

                        result = ""
                        if name == "shell_execute":
                            if silent is False: self.connector.send(f"🐚 Shell: `{args.get('command')}`")
                            result = ShellTool.execute(args.get("command"))
                        elif name == "shell_async":
                            if silent is False: self.connector.send(f"🚀 Async Shell: `{args.get('command')}`")
                            result = AsyncShellTool.execute(args.get("command"))
                        elif name == "file_read":
                            if silent is False: self.connector.send(f"📖 Read: `{args.get('path')}`")
                            result = FileTool.read(args.get("path"))
                        elif name == "file_write":
                            if silent is False: self.connector.send(f"💾 Write: `{args.get('path')}`")
                            result = FileTool.write(args.get("path"), args.get("content"))
                        elif name == "file_upload":
                            if silent is False: self.connector.send(f"📤 Upload: `{args.get('path')}`")
                            self.connector.send_file(args.get("path"))
                            result = f"File {args.get('path')} sent."
                        elif name == "wait":
                            if silent is False: self.connector.send(f"⏳ Waiting {args.get('seconds')}s...")
                            result = TimerTool.wait(args.get("seconds"))
                        elif name == "reset_session":
                            self.memory.reset()
                            if silent is False: self.connector.send("✨ Session reset! Starting fresh.")
                            result = "Success: Session history cleared."
                            session_reset = True
                            break
                        elif name == "memory_add":
                            if silent is False: self.connector.send(f"🧠 Memorize: `{args.get('memory', '')}`")
                            result = self.memory.global_memory_add(args.get("memory", ""))
                        elif name == "memory_list":
                            if silent is False: self.connector.send("🧠 Listing global memories...")
                            result = self.memory.global_memory_list()
                        elif name == "memory_delete":
                            indices = args.get("indices", args.get("index", -1))
                            if isinstance(indices, list):
                                indices = [int(i) for i in indices]
                            else:
                                indices = int(indices)
                            if silent is False: self.connector.send(f"🧠 Delete memory {indices}")
                            result = self.memory.global_memory_delete(indices)
                        elif name == "browser_start":
                            if silent is False: self.connector.send("🌐 Starting browser...")
                            user_data_dir = self.config.get("browser", {}).get("data_dir")
                            result = BrowserTool.start(user_data_dir=user_data_dir)
                        elif name == "browser_stop":
                            if silent is False: self.connector.send("🌐 Stopping browser...")
                            result = BrowserTool.stop()
                        elif name == "browser_navigate":
                            if silent is False: self.connector.send(f"🌐 Navigate: `{args.get('url')}`")
                            result = BrowserTool.navigate(args.get("url"))
                        elif name == "browser_click":
                            if silent is False: self.connector.send(f"🌐 Click: `{args.get('selector')}`")
                            result = BrowserTool.click(args.get("selector"))
                        elif name == "browser_fill":
                            if silent is False: self.connector.send(f"🌐 Fill: `{args.get('selector')}`")
                            result = BrowserTool.fill(args.get("selector"), args.get("text", ""))
                        elif name == "browser_get_text":
                            if silent is False: self.connector.send(f"🌐 Get text: `{args.get('selector', 'body')}`")
                            result = BrowserTool.get_text(args.get("selector"))
                        elif name == "browser_screenshot":
                            if silent is False: self.connector.send("🌐 Screenshot...")
                            result = BrowserTool.screenshot(args.get("path"))
                            if result.startswith("OK:"):
                                if silent is False: self.connector.send_file(result[4:].strip())
                        elif name == "upgrade":
                            if silent is False: self.connector.send("⬆️ Upgrading MMClaw... (this is tricky — there's no notification when it's done. Please wait a moment, then ask me for my version number to confirm the upgrade succeeded.)")
                            result = UpgradeTool.upgrade()  # restarts process on success; only returns on failure
                            if silent is False: self.connector.send(f"❌ Upgrade failed: {result}")

                        if self.debug:
                            print(f"\n    [Tool Output: {name}]\n    {result}\n")
                        tool_output = f"Tool Output ({name}):\n{result}"
                        if is_heartbeat:
                            history.append({"role": "user", "content": tool_output})
                        else:
                            self.memory.add("user", tool_output)

                    if session_reset:
                        break

            except Exception as e:
                print(f"[!] Worker error: {e}")
                traceback.print_exc()
            finally:
                self.connector.stop_typing()
                q.task_done()

    def handle(self, text):
        self.chat_queue.put(text)

    def run(self, stop_on_auth=False):
        try:
            self.connector.listen(self.handle, stop_on_auth=stop_on_auth)
        except TypeError:
            self.connector.listen(self.handle)
