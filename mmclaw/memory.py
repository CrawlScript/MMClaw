import os
import json
import glob
from datetime import datetime


class BaseMemory(object):
    def __init__(self, system_prompt):
        self.system_prompt = system_prompt
        self.history = [{"role": "system", "content": system_prompt}]

    def add(self, role, content):
        pass

    def get_all(self):
        pass

    def reset(self):
        pass


class InMemoryMemory(BaseMemory):
    def add(self, role, content):
        self.history.append({"role": role, "content": content})

    def get_all(self):
        return self.history

    def reset(self):
        self.history = [{"role": "system", "content": self.system_prompt}]


class FileMemory(BaseMemory):
    SESSIONS_DIR = os.path.join(os.path.expanduser("~"), ".mmclaw", "sessions")

    def __init__(self, system_prompt):
        os.makedirs(self.SESSIONS_DIR, exist_ok=True)
        latest = self._find_latest()
        if latest:
            try:
                self._load(latest, system_prompt)
                print(f"[*] Resumed session: {os.path.basename(self.session_file)}")
            except Exception as e:
                print(f"[!] Failed to load session {os.path.basename(latest)}: {e}")
                self._start_new(system_prompt)
                print(f"[*] Using new session: {os.path.basename(self.session_file)}")
        else:
            self._start_new(system_prompt)
            print(f"[*] New session: {os.path.basename(self.session_file)}")

    def _start_new(self, system_prompt):
        super().__init__(system_prompt)
        self.session_file = self._new_path()
        self._append({"role": "system", "content": system_prompt})

    def _find_latest(self):
        files = glob.glob(os.path.join(self.SESSIONS_DIR, "session_*.jsonl"))
        return max(files, key=lambda f: os.path.basename(f).split("session_")[1]) if files else None

    def _new_path(self):
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d_%H-%M-%S")
        ms = now.microsecond // 1000
        return os.path.join(self.SESSIONS_DIR, f"session_{ts}-{ms:03d}.jsonl")

    def _load(self, path, system_prompt):
        self.system_prompt = system_prompt
        self.history = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.history.append(json.loads(line))
        # Always use the current system prompt
        if self.history and self.history[0]["role"] == "system":
            self.history[0]["content"] = system_prompt
        self.session_file = path

    def _append(self, entry):
        with open(self.session_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def add(self, role, content):
        entry = {"role": role, "content": content}
        self.history.append(entry)
        self._append(entry)

    def get_all(self):
        return self.history

    def reset(self):
        self._start_new(self.system_prompt)
        print(f"[*] New session: {os.path.basename(self.session_file)}")
