import threading
import queue
import json
import re
from .providers import Engine
from .tools import ShellTool, AsyncShellTool, FileTool, TimerTool, SessionTool

class Memory(object):
    def __init__(self, system_prompt):
        self.system_prompt = system_prompt
        self.history = [{"role": "system", "content": system_prompt}]
    
    def add(self, role, content): 
        self.history.append({"role": role, "content": content})
    
    def get_all(self): 
        return self.history

    def reset(self):
        """Clears the history except for the system prompt."""
        self.history = [{"role": "system", "content": self.system_prompt}]

class MMClaw(object):
    def __init__(self, config, connector, system_prompt):
        self.engine = Engine(config)
        self.connector = connector
        self.memory = Memory(system_prompt)
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
        except Exception:
            return None
        return None

    def _worker(self):
        while True:
            user_text = self.task_queue.get()
            if user_text is None: break
            
            self.memory.add("user", user_text)
            
            while True:
                response_msg = self.engine.ask(self.memory.get_all())
                raw_text = response_msg.get("content", "")
                
                # We save the raw response to memory to maintain context
                self.memory.add("assistant", raw_text)

                data = self._extract_json(raw_text)
                if not data:
                    self.connector.send(raw_text)
                    break

                if data.get("content"):
                    self.connector.send(data["content"])

                tools = data.get("tools", [])
                if not tools:
                    break

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
                        # Break inner loop to start with fresh memory on next user input
                        break
                    
                    if self.debug:
                        print(f"\n    [Tool Output: {name}]\n    {result}\n")
                    self.memory.add("system", f"Tool Output ({name}):\n{result}")

            self.task_queue.task_done()

    def handle(self, text):
        self.task_queue.put(text)

    def run(self, stop_on_auth=False):
        try:
            self.connector.listen(self.handle, stop_on_auth=stop_on_auth)
        except TypeError:
            self.connector.listen(self.handle)
