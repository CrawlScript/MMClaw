import subprocess
import os
import locale

class ShellTool(object):
    @staticmethod
    def execute(command):
        """Executes a shell command and returns the output."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                # timeout=30
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
