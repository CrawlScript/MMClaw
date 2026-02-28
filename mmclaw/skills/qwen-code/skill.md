---
name: qwen-code
description: Run Qwen Code CLI to execute AI-powered coding tasks in a local repo. Use when the user wants to ask Qwen to write, edit, refactor, or explain code in their project.
metadata:
  { "emoji": "🧠", "os": ["linux", "darwin", "win32"], "requires": { "bins": ["qwen"] } }
---

# Qwen Code Skill

Use this skill when the user wants to delegate a coding task to Qwen Code CLI — writing new code, editing existing files, refactoring, explaining code, or running multi-step agentic tasks inside a project.

Trigger phrases: "use qwen", "ask qwen", "let qwen", "qwen do", "qwen fix", "qwen write", "run qwen".

## Core Invocation

Qwen Code is always run in **non-interactive / auto-approve mode** using positional prompt with `--yolo` (or `--approval-mode yolo`) to avoid interactive prompts blocking execution.

```bash
qwen --yolo "<prompt>"
```

If the user specifies a working directory, `cd` into it first:

```bash
cd /path/to/project && qwen --yolo "<prompt>"
```

If a specific model is needed, use `-m`:

```bash
qwen --yolo -m <model-name> "<prompt>"
```

---

## Choosing Between Foreground and Background Execution

### Run in the FOREGROUND (default) when:
- The task is simple or small-scope (fix a bug, write a function, explain code, add a test)
- The user expects a quick result
- You need the output immediately to answer the user

Run directly and capture output — the command blocks until Qwen finishes.

### Run in the BACKGROUND when:
- The task is large or open-ended (implement a feature, refactor an entire module, generate a full component)
- The user says "background", "don't wait", "async", "long task", or similar
- You expect the task will take more than ~30 seconds

**Linux / macOS:**
```bash
SESSION="$(python -c 'import tempfile, os, time; print(os.path.join(tempfile.gettempdir(), "qwen_" + str(int(time.time()))))')"
cd /path/to/project && nohup qwen --yolo "<prompt>" > "${SESSION}.log" 2>&1 & echo $! > "${SESSION}.pid" && echo "Session: ${SESSION}"
```

**Windows (PowerShell):**
```powershell
$session = "$env:TEMP\qwen_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
Start-Process -FilePath "qwen" -ArgumentList "--yolo `"<prompt>`"" -WorkingDirectory "C:\path\to\project" -RedirectStandardOutput "$session.log" -RedirectStandardError "$session.err" -PassThru | Select-Object -ExpandProperty Id | Out-File "$session.pid"
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

## Resuming Sessions

Qwen Code supports session persistence. Use these flags when relevant:

```bash
# Resume most recent session for the current project
qwen --yolo -c "<follow-up prompt>"

# Resume a specific session by ID
qwen --yolo -r <session-id> "<follow-up prompt>"
```

---

## Controlling Output Format

For machine-readable output (e.g., piping results into another tool):

```bash
# JSON output
qwen --yolo -o json "<prompt>"

# Streaming JSON
qwen --yolo -o stream-json "<prompt>"
```

Default output is plain text, which is preferred for most tasks.

---

## Limiting Scope

To cap the number of turns Qwen takes (useful for predictable, bounded tasks):

```bash
qwen --yolo --max-session-turns 5 "<prompt>"
```

To restrict which tools Qwen may use:

```bash
# Allow only specific tools (bypass confirmation for those)
qwen --yolo --allowed-tools <tool1> <tool2> "<prompt>"

# Exclude specific tools entirely
qwen --yolo --exclude-tools <tool1> "<prompt>"
```

---

## After Execution

### Foreground tasks
Always parse and summarize what Qwen did — which files were modified, what code was written, any errors encountered. Do NOT relay raw output verbatim; extract the key result for the user.

### Background tasks
Report:
1. The session log path (e.g. `/tmp/qwen_1234567890.log`)
2. The PID
3. How to tail the log to monitor progress

When the user asks for results later, tail the log and summarize.

---

## Notes

- Session log files live in the OS temp directory and will be cleaned up automatically on reboot — do not rely on them for permanent storage.
- Qwen may modify files on disk. If the user wants a dry run, use `--approval-mode plan` first to preview actions before committing.
- If Qwen exits with a non-zero code, report the error and suggest the user check their API key (`--openai-api-key`) or base URL (`--openai-base-url`) configuration.
- To list recent sessions (Linux/macOS): `ls -lt /tmp/qwen_*.log`
- To list recent sessions (Windows): `Get-ChildItem $env:TEMP\qwen_*.log | Sort-Object LastWriteTime -Descending`
- For sandbox execution (isolated environment), add `-s` or `--sandbox` flag.