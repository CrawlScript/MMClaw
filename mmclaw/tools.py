import subprocess
import os

class ShellTool(object):
    @staticmethod
    def execute(command):
        """Executes a shell command and returns the output."""
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                encoding='utf-8', 
                timeout=30
            )
            output = result.stdout if result.returncode == 0 else result.stderr
            return f"Return Code {result.returncode}:\n{output}"
        except Exception as e:
            return f"Error executing command: {str(e)}"

class FileTool(object):
    @staticmethod
    def read(path):
        """Reads a file and returns its content."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

    @staticmethod
    def write(path, content):
        """Writes content to a file."""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
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
