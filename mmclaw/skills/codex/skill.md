---
name: codex
description: Run OpenAI Codex CLI to execute AI-powered coding tasks in a local repo. Use when the user wants to ask Codex to write, edit, refactor, or explain code in their project.
metadata:
  { "mmclaw": { "emoji": "🤖", "os": ["linux", "darwin", "win32"], "requires": { "bins": ["codex"] } } }
---

# Codex Skill (MMClaw)

Use this skill when the user wants to delegate a coding task to Codex CLI — writing new code, editing existing files, refactoring, explaining code, or running multi-step agentic tasks inside a project.

Trigger phrases: "use codex", "ask codex", "let codex", "codex do", "codex fix", "codex write", "run codex".

## Core Invocation

Use the `exec` subcommand to run Codex non-interactively. Always add `--full-auto` to avoid interactive prompts blocking execution.

```bash
codex exec --full-auto "<prompt>"
```

If the user specifies a working directory, use `-C`:

```bash
codex exec --full-auto -C /path/to/project "<prompt>"
```

If no working directory is mentioned, run from the current directory. Do NOT assume a path.

---

## Choosing Between Foreground and Background Execution

### Run in the FOREGROUND (default) when:
- The task is simple or small-scope (fix a bug, write a function, explain code, add a test)
- The user expects a quick result
- You need the output immediately to answer the user

Run it directly and capture the output. The command blocks until Codex finishes.

### Run in the BACKGROUND when:
- The task is large or open-ended (implement a feature, refactor an entire module, generate a full component)
- The user says "background", "don't wait", "async", "long task", or similar
- You expect the task will take more than ~30 seconds

Use `nohup` (Linux/macOS) or `Start-Process` (Windows) and redirect output to a session log in the system temp directory.

**Linux / macOS:**
```bash
SESSION="$(python -c 'import tempfile, os; print(os.path.join(tempfile.gettempdir(), "codex_$(date +%Y%m%d_%H%M%S)"))')"
nohup codex exec --full-auto -C /path/to/project "<prompt>" > "${SESSION}.log" 2>&1 & echo $! > "${SESSION}.pid" && echo "Session: ${SESSION}"
```

**Windows (PowerShell):**
```powershell
$session = "$env:TEMP\codex_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
Start-Process -FilePath "codex" -ArgumentList "exec --full-auto -C `"C:\path\to\project`" `"<prompt>`"" -RedirectStandardOutput "$session.log" -RedirectStandardError "$session.err" -PassThru | Select-Object -ExpandProperty Id | Out-File "$session.pid"
Write-Output "Session: $session"
```

After launching, report the session path to the user so they can monitor progress.

---

## Monitoring a Background Session

**Linux / macOS — check if still running:**
```bash
PID=$(cat <session>.pid)
ps -p $PID > /dev/null 2>&1 && echo "Still running (PID $PID)" || echo "Finished"
```

**Windows — check if still running:**
```powershell
$pid = Get-Content "<session>.pid"
if (Get-Process -Id $pid -ErrorAction SilentlyContinue) { "Still running (PID $pid)" } else { "Finished" }
```

**Tail latest output (Linux/macOS):**
```bash
tail -n 50 <session>.log
```

**Tail latest output (Windows):**
```powershell
Get-Content "<session>.log" -Tail 50
```

---

## After Execution

### Foreground tasks
Always parse and summarize what Codex did — which files were modified, what code was written, any errors encountered. Do NOT relay raw output verbatim; extract the key result for the user.

### Background tasks
Report:
1. The session log path (e.g. `/tmp/codex_20250226_143012.log` or `C:\Users\...\AppData\Local\Temp\codex_...log`)
2. The PID
3. How to tail the log to monitor progress

When the user asks for results later, tail the log and summarize.

---

## Notes

- Session log files live in the OS temp directory and will be cleaned up automatically on reboot — do not rely on them for permanent storage.
- Codex may modify files on disk. If the user wants a dry run first, ask them to confirm before proceeding with `--full-auto`.
- If Codex exits with a non-zero code, report the error from stderr and suggest the user check their API key or prompt phrasing.
- To list recent sessions (Linux/macOS): `ls -lt /tmp/codex_*.log`
- To list recent sessions (Windows): `Get-ChildItem $env:TEMP\codex_*.log | Sort-Object LastWriteTime -Descending`