import os
import json
import glob
from datetime import datetime

TOTAL_HISTORY_TOKENS = 45_000
MAX_MSG_TOKENS = 16_000


def _estimate_tokens(text):
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False)
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return chinese + (len(text) - chinese) // 4


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

    def update_system_prompt(self, prompt):
        self.system_prompt = prompt
        if self.history and self.history[0]["role"] == "system":
            self.history[0]["content"] = prompt


class FileMemory(BaseMemory):
    SESSIONS_DIR = os.path.join(os.path.expanduser("~"), ".mmclaw", "sessions")

    def __init__(self, system_prompt):
        os.makedirs(self.SESSIONS_DIR, exist_ok=True)
        latest_dir = self._find_latest_dir()
        if latest_dir:
            try:
                self._load(latest_dir, system_prompt)
                print(f"[*] Resumed session: {os.path.basename(latest_dir)}")
            except Exception as e:
                print(f"[!] Failed to load session {os.path.basename(latest_dir)}: {e}")
                self._start_new(system_prompt)
                print(f"[*] Using new session: {os.path.basename(self.session_dir)}")
        else:
            self._start_new(system_prompt)
            print(f"[*] New session: {os.path.basename(self.session_dir)}")

    def _start_new(self, system_prompt):
        super().__init__(system_prompt)
        self.session_dir = self._new_dir()
        os.makedirs(self.session_dir, exist_ok=True)
        os.makedirs(os.path.join(self.session_dir, "files"), exist_ok=True)
        self.session_file = os.path.join(self.session_dir, "messages.jsonl")
        self._append({"role": "system", "content": system_prompt})

    def _new_dir(self):
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d_%H-%M-%S")
        ms = now.microsecond // 1000
        return os.path.join(self.SESSIONS_DIR, f"session_{ts}-{ms:03d}")

    def _find_latest_dir(self):
        dirs = [d for d in glob.glob(os.path.join(self.SESSIONS_DIR, "session_*")) if os.path.isdir(d)]
        return max(dirs, key=os.path.basename) if dirs else None

    def _load(self, session_dir, system_prompt):
        self.session_dir = session_dir
        self.session_file = os.path.join(session_dir, "messages.jsonl")
        self.system_prompt = system_prompt
        self.history = []
        with open(self.session_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.history.append(json.loads(line))
        if self.history and self.history[0]["role"] == "system":
            self.history[0]["content"] = system_prompt

    def _append(self, entry):
        with open(self.session_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def add(self, role, content):
        entry = {"role": role, "content": content}
        self.history.append(entry)
        self._append(entry)

    @property
    def files_dir(self):
        return os.path.join(self.session_dir, "files")

    def get_all(self):
        messages = self.history[1:]

        system_tokens = _estimate_tokens(self.history[0]["content"])
        available = TOTAL_HISTORY_TOKENS - system_tokens
        selected = []
        used = 0
        for msg in reversed(messages):
            content = msg.get("content", "")
            if isinstance(content, str) and _estimate_tokens(content) > MAX_MSG_TOKENS:
                content = content[:MAX_MSG_TOKENS * 3] + "\n... [truncated, full content in session file]"
            tokens = _estimate_tokens(content)
            if used + tokens > available:
                break
            selected.append({**msg, "content": content})
            used += tokens
        selected.reverse()

        dropped = len(messages) - len(selected)
        if dropped > 0:
            history_note = (
                f"\n\nSession dir: {self.session_dir} "
                f"({dropped} earlier messages not in context, full log at {self.session_file}). "
                f"Each line is a JSON object with 'role' and 'content'. "
                f"Use shell_execute with a search command (e.g. grep on Unix, findstr on Windows) "
                f"to find relevant history by keyword rather than reading the full file. "
                f"Uploaded files are in {self.files_dir}."
            )
        else:
            history_note = (
                f"\n\nSession dir: {self.session_dir} (full history in context). "
                f"Uploaded files are in {self.files_dir}."
            )

        system = {"role": "system", "content": self.history[0]["content"] + history_note}
        return [system] + selected

    def save_file(self, filename: str, data: bytes) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.files_dir, f"{ts}_{filename}")
        with open(path, "wb") as f:
            f.write(data)
        return path

    def reset(self):
        self._start_new(self.system_prompt)
        print(f"[*] New session: {os.path.basename(self.session_dir)}")
