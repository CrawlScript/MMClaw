import subprocess
import os
import locale

class ShellTool(object):
    TIMEOUT = 60

    @staticmethod
    def execute(command):
        """Executes a shell command and returns the output."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=ShellTool.TIMEOUT
            )
            output = result.stdout if result.returncode == 0 else result.stderr
            try:
                output = output.decode('utf-8')
            except UnicodeDecodeError:
                output = output.decode(locale.getpreferredencoding(False), errors='replace')
            return f"Return Code {result.returncode}:\n{output}"
        except Exception as e:
            return f"Error executing command: {str(e)}"

class AsyncShellTool(object):
    @staticmethod
    def execute(command):
        """Starts a long-running shell command in the background."""
        try:
            # Using Popen to start the process without waiting for it to finish.
            # Redirect stdout/stderr to DEVNULL to avoid cluttering.
            # No start_new_session so the process stays in the same process group.
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return f"Started background process (PID: {process.pid}) for command: {command}"
        except Exception as e:
            return f"Error starting background command: {str(e)}"

class FileTool(object):
    @staticmethod
    def read(path):
        """Reads a file and returns its content."""
        try:
            full_path = os.path.expanduser(path)
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

    @staticmethod
    def write(path, content):
        """Writes content to a file."""
        try:
            full_path = os.path.expanduser(path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Successfully wrote to {path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

class TimerTool(object):
    @staticmethod
    def wait(seconds):
        """Pauses execution for a specified number of seconds (cross-platform)."""
        import time
        try:
            secs = float(seconds)
            time.sleep(secs)
            return f"Waited for {secs} seconds."
        except Exception as e:
            return f"Timer error: {str(e)}"

class SessionTool(object):
    @staticmethod
    def reset():
        """Returns a signal string that the kernel will use to reset the session."""
        return "SESSION_RESET_SIGNAL"

class BrowserTool(object):
    import tempfile as _tempfile
    _tmp = _tempfile.gettempdir()
    CDP_URL = "http://localhost:9222"
    WS_FILE = f"{_tmp}/mmclaw_browser_ws.txt"
    DAEMON_SCRIPT = f"{_tmp}/mmclaw_browser_daemon.py"
    DAEMON_LOG = f"{_tmp}/mmclaw_browser_daemon.log"
    DEFAULT_SCREENSHOT = f"{_tmp}/mmclaw_browser_screenshot.png"
    DEFAULT_DATA_DIR = "~/.mmclaw/browser_data"
    _daemon_process = None

    @classmethod
    def _is_running(cls):
        import urllib.request
        try:
            urllib.request.urlopen(f"{cls.CDP_URL}/json/version", timeout=2)
            return True
        except Exception:
            return False

    @classmethod
    def _get_page(cls, pw):
        browser = pw.chromium.connect_over_cdp(cls.CDP_URL)
        if not browser.contexts:
            raise RuntimeError("No browser context found. Call browser_start first.")
        ctx = browser.contexts[0]  # always the persistent context from launch_persistent_context
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        return browser, page

    @classmethod
    def start(cls, user_data_dir=None):
        if cls._is_running():
            return "Browser already running."
        import subprocess, sys, time, os, textwrap
        data_dir = os.path.join(os.path.expanduser(user_data_dir or cls.DEFAULT_DATA_DIR), "chromium")
        os.makedirs(data_dir, exist_ok=True)
        daemon_code = textwrap.dedent(f"""\
            from playwright.sync_api import sync_playwright
            import os, time, json
            WS_FILE = {repr(cls.WS_FILE)}
            DATA_DIR = {repr(data_dir)}

            # Patch Chrome Preferences to suppress "Restore pages?" dialog.
            # Chrome shows it when exit_type != "Normal" (i.e. it thinks it crashed).
            prefs_path = os.path.join(DATA_DIR, "Default", "Preferences")
            if os.path.exists(prefs_path):
                try:
                    prefs = json.loads(open(prefs_path).read())
                    prefs.setdefault("profile", {{}})["exit_type"] = "Normal"
                    prefs.setdefault("profile", {{}})["crashed"] = False
                    open(prefs_path, "w").write(json.dumps(prefs))
                except Exception:
                    pass

            try:
                with sync_playwright() as pw:
                    context = pw.chromium.launch_persistent_context(
                        DATA_DIR,
                        headless=False,
                        args=["--remote-debugging-port=9222", "--no-first-run", "--no-default-browser-check"],
                    )
                    open(WS_FILE, "w").write("http://localhost:9222")
                    print("Browser ready.", flush=True)
                    while os.path.exists(WS_FILE):
                        time.sleep(1)
                    context.close()
                print("Browser stopped.", flush=True)
            except Exception as e:
                print(f"ERROR: {{e}}", flush=True)
                raise
        """)
        with open(cls.DAEMON_SCRIPT, "w") as f:
            f.write(daemon_code)
        cls._daemon_process = subprocess.Popen(
            [sys.executable, cls.DAEMON_SCRIPT],
            stdout=open(cls.DAEMON_LOG, "w"), stderr=subprocess.STDOUT
        )
        log_pos = 0
        for _ in range(60):  # up to 30s — first launch after fresh install can be slow
            time.sleep(0.5)
            if os.path.exists(cls.DAEMON_LOG):
                with open(cls.DAEMON_LOG) as f:
                    f.seek(log_pos)
                    chunk = f.read()
                    if chunk:
                        print(chunk, end='', flush=True)
                        log_pos = f.tell()
            if cls._is_running():
                return "OK: Browser started."
        log = open(cls.DAEMON_LOG).read() if os.path.exists(cls.DAEMON_LOG) else "(no log)"
        return f"ERROR: Browser did not start within 30s.\n{log}"

    @classmethod
    def stop(cls):
        import os, time
        if not cls._is_running():
            if os.path.exists(cls.WS_FILE):
                os.remove(cls.WS_FILE)
            return "Browser is not running."
        if os.path.exists(cls.WS_FILE):
            os.remove(cls.WS_FILE)
        time.sleep(2)
        return "OK: Browser stopped."

    @classmethod
    def navigate(cls, url):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser, page = cls._get_page(pw)
                page.goto(url, wait_until="domcontentloaded")
                result = f"Title: {page.title()}\nURL: {page.url}"

            return result
        except Exception as e:
            return f"ERROR: {e}"

    @classmethod
    def click(cls, selector):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser, page = cls._get_page(pw)
                page.locator(selector).first.click()
                page.wait_for_load_state("domcontentloaded")
                result = f"Clicked. Title: {page.title()}\nURL: {page.url}"

            return result
        except Exception as e:
            return f"ERROR: {e}"

    @classmethod
    def fill(cls, selector, text):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser, page = cls._get_page(pw)
                page.locator(selector).fill(text)

            return "OK: filled."
        except Exception as e:
            return f"ERROR: {e}"

    @classmethod
    def get_text(cls, selector=None):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser, page = cls._get_page(pw)
                text = page.locator(selector).first.inner_text() if selector else page.inner_text("body")

            return text
        except Exception as e:
            return f"ERROR: {e}"

    @classmethod
    def screenshot(cls, path=None):
        try:
            from playwright.sync_api import sync_playwright
            save_path = path or cls.DEFAULT_SCREENSHOT
            with sync_playwright() as pw:
                browser, page = cls._get_page(pw)
                page.screenshot(path=save_path, full_page=True)

            return f"OK: {save_path}"
        except Exception as e:
            return f"ERROR: {e}"


class UpgradeTool(object):
    @staticmethod
    def upgrade():
        """Upgrades mmclaw via pip, then restarts the current process in-place."""
        import sys
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-U", "mmclaw"],
                capture_output=True,
                timeout=120
            )
            output = result.stdout + result.stderr
            try:
                output = output.decode('utf-8')
            except UnicodeDecodeError:
                output = output.decode(locale.getpreferredencoding(False), errors='replace')
            if result.returncode != 0:
                return f"Upgrade failed:\n{output}"
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            return f"Upgrade error: {str(e)}"
