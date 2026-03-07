import threading
import traceback
import queue
import json
import re
from .providers import Engine
from .tools import ShellTool, AsyncShellTool, FileTool, TimerTool, SessionTool, UpgradeTool, BrowserTool
from .memory import FileMemory

class MMClaw(object):
    def __init__(self, config, connector, system_prompt):
        self.config = config
        self.engine = Engine(config)
        self.connector = connector
        self.memory = FileMemory(system_prompt)
        self.connector.file_saver = self.memory.save_file
        self.task_queue = queue.Queue()
        self.debug = config.get("debug", False)
        
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

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

    def _worker(self):
        while True:
            user_text = self.task_queue.get()
            if user_text is None: break
            
            self.memory.add("user", user_text)

            self.connector.start_typing()
            try:
                while True:
                    # Refresh system prompt before every call to pick up new skills or context changes
                    from .config import ConfigManager
                    new_prompt = ConfigManager.get_full_prompt(mode=self.connector.__class__.__name__.lower().replace("connector", ""))
                    self.memory.update_system_prompt(new_prompt)

                    response_msg = self.engine.ask(self.memory.get_all())
                    raw_text = response_msg.get("content", "")

                    # We save the raw response to memory to maintain context
                    self.memory.add("assistant", raw_text)

                    data = self._extract_json(raw_text)
                    # print(f"[D] data={repr(data)}")
                    if not data:
                        self.connector.send(raw_text)
                        break

                    if data.get("content"):
                        content = data["content"]
                        if not isinstance(content, str):
                            try:
                                content = json.dumps(content, ensure_ascii=False)
                            except Exception:
                                content = "[Error: unexpected content format]"
                        self.connector.send(content)

                    tools = data.get("tools", [])
                    if not tools:
                        break

                    session_reset = False
                    for tool in tools:
                        name = tool.get("name")
                        args = tool.get("args", {})

                        # Always print the tool name
                        print(f"    [Tool Call: {name}]")
                        if self.debug:
                            print(f"    Args: {json.dumps(args)}")

                        result = ""
                        if name == "shell_execute":
                            self.connector.send(f"🐚 Shell: `{args.get('command')}`")
                            result = ShellTool.execute(args.get("command"))
                        elif name == "shell_async":
                            self.connector.send(f"🚀 Async Shell: `{args.get('command')}`")
                            result = AsyncShellTool.execute(args.get("command"))
                        elif name == "file_read":
                            self.connector.send(f"📖 Read: `{args.get('path')}`")
                            result = FileTool.read(args.get("path"))
                        elif name == "file_write":
                            self.connector.send(f"💾 Write: `{args.get('path')}`")
                            result = FileTool.write(args.get("path"), args.get("content"))
                        elif name == "file_upload":
                            self.connector.send(f"📤 Upload: `{args.get('path')}`")
                            self.connector.send_file(args.get("path"))
                            result = f"File {args.get('path')} sent."
                        elif name == "wait":
                            self.connector.send(f"⏳ Waiting {args.get('seconds')}s...")
                            result = TimerTool.wait(args.get("seconds"))
                        elif name == "reset_session":
                            self.memory.reset()
                            self.connector.send("✨ Session reset! Starting fresh.")
                            result = "Success: Session history cleared."
                            session_reset = True
                            break
                        elif name == "memory_add":
                            self.connector.send(f"🧠 Memorize: `{args.get('memory', '')}`")
                            result = self.memory.global_memory_add(args.get("memory", ""))
                        elif name == "memory_list":
                            self.connector.send("🧠 Listing global memories...")
                            result = self.memory.global_memory_list()
                        elif name == "memory_delete":
                            indices = args.get("indices", args.get("index", -1))
                            if isinstance(indices, list):
                                indices = [int(i) for i in indices]
                            else:
                                indices = int(indices)
                            self.connector.send(f"🧠 Delete memory {indices}")
                            result = self.memory.global_memory_delete(indices)
                        elif name == "browser_start":
                            self.connector.send("🌐 Starting browser...")
                            user_data_dir = self.config.get("browser", {}).get("data_dir")
                            result = BrowserTool.start(user_data_dir=user_data_dir)
                        elif name == "browser_stop":
                            self.connector.send("🌐 Stopping browser...")
                            result = BrowserTool.stop()
                        elif name == "browser_navigate":
                            self.connector.send(f"🌐 Navigate: `{args.get('url')}`")
                            result = BrowserTool.navigate(args.get("url"))
                        elif name == "browser_click":
                            self.connector.send(f"🌐 Click: `{args.get('selector')}`")
                            result = BrowserTool.click(args.get("selector"))
                        elif name == "browser_fill":
                            self.connector.send(f"🌐 Fill: `{args.get('selector')}`")
                            result = BrowserTool.fill(args.get("selector"), args.get("text", ""))
                        elif name == "browser_get_text":
                            self.connector.send(f"🌐 Get text: `{args.get('selector', 'body')}`")
                            result = BrowserTool.get_text(args.get("selector"))
                        elif name == "browser_screenshot":
                            self.connector.send("🌐 Screenshot...")
                            result = BrowserTool.screenshot(args.get("path"))
                            if result.startswith("OK:"):
                                self.connector.send_file(result[4:].strip())
                        elif name == "upgrade":
                            self.connector.send("⬆️ Upgrading MMClaw... (this is tricky — there's no notification when it's done. Please wait a moment, then ask me for my version number to confirm the upgrade succeeded.)")
                            result = UpgradeTool.upgrade()  # restarts process on success; only returns on failure
                            self.connector.send(f"❌ Upgrade failed: {result}")

                        if self.debug:
                            print(f"\n    [Tool Output: {name}]\n    {result}\n")
                        # self.memory.add("system", f"Tool Output ({name}):\n{result}")
                        self.memory.add("user", f"Tool Output ({name}):\n{result}")

                    if session_reset:
                        break

            except Exception as e:
                print(f"[!] Worker error: {e}")
                traceback.print_exc()
            finally:
                self.connector.stop_typing()
                self.task_queue.task_done()

    def handle(self, text):
        self.task_queue.put(text)

    def run(self, stop_on_auth=False):
        try:
            self.connector.listen(self.handle, stop_on_auth=stop_on_auth)
        except TypeError:
            self.connector.listen(self.handle)
