import sys
import time
import subprocess
import threading
import json
from pathlib import Path


def notify(message: str):
    """Call this from a watcher script to send a notification to MMClaw."""
    # Use JSON to escape newlines and ensure the notification is a single line
    payload = json.dumps(message, ensure_ascii=False)
    print(f"[NOTIFY] {payload}", flush=True)


class WatcherManager:
    SKILLS_DIR = Path.home() / ".mmclaw" / "skills"

    def __init__(self, chat_queue):
        self.chat_queue = chat_queue

    def start(self):
        if not self.SKILLS_DIR.exists():
            return
        for skill_dir in sorted(self.SKILLS_DIR.iterdir()):
            if not skill_dir.is_dir():
                continue
            watcher_file = skill_dir / "watcher.py"
            if watcher_file.exists():
                self._start_watcher(skill_dir.name, watcher_file)

    def _start_watcher(self, name: str, watcher_file: Path):
        threading.Thread(
            target=self._run,
            args=(name, watcher_file),
            daemon=True,
        ).start()
        print(f"[*] WatcherManager: started '{name}'")

    def _run(self, name: str, watcher_file: Path):
        while True:
            try:
                proc = subprocess.Popen(
                    [sys.executable, "-u", str(watcher_file)],
                    stdout=subprocess.PIPE,
                    stderr=None,  # stderr passes through to console
                    text=True,
                )
                for line in proc.stdout:
                    line = line.rstrip()
                    if line.startswith("[NOTIFY] "):
                        payload = line[len("[NOTIFY] "):]
                        try:
                            # Attempt to parse as JSON (new multi-line support)
                            msg = json.loads(payload)
                        except Exception:
                            # Fallback to raw text (old single-line support)
                            msg = payload
                        
                        self.chat_queue.put(f"[WATCHER: {name}]\n{msg}")
                        print(f"[*] WatcherManager: queued notification from '{name}'")
                    else:
                        if line:
                            print(f"[watcher/{name}] {line}")
                proc.wait()
                print(f"[!] WatcherManager: '{name}' exited (code {proc.returncode}), restarting in 5s...")
            except Exception as e:
                print(f"[!] WatcherManager: error for '{name}': {e}")
            time.sleep(5)
