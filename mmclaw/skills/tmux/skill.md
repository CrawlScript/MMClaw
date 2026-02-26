---
name: tmux
description: Remote-control tmux sessions for interactive CLIs by sending keystrokes and scraping pane output.
metadata:
  { "mmclaw": { "emoji": "🐾", "os": ["darwin", "linux"], "requires": { "bins": ["tmux"] } } }
---
# tmux Session Control
Control tmux sessions by sending keystrokes and reading output. Essential for managing AI agent sessions.

## When to Use
✅ **USE this skill when:**
- Monitoring AI agent sessions in tmux
- Sending input to interactive terminal applications
- Scraping output from long-running processes in tmux
- Navigating tmux panes/windows programmatically
- Checking on background work in existing sessions

## When NOT to Use
❌ **DON'T use this skill when:**
- Running one-off shell commands → use `exec` tool directly
- Starting new background processes → use `exec` with `background:true`
- Non-interactive scripts → use `exec` tool
- The process isn't in tmux
- You need to create a new tmux session → use `exec` with `tmux new-session`

## Example Sessions
| Session                  | Purpose                     |
| ------------------------ | --------------------------- |
| `mmclaw-main`            | Primary interactive session |
| `mmclaw-1` - `mmclaw-8` | Parallel agent sessions     |

## Common Commands

### List Sessions
```bash
tmux list-sessions
tmux ls
```

### Capture Output
```bash
# Last 20 lines of pane
tmux capture-pane -t mmclaw-main -p | tail -20
# Entire scrollback
tmux capture-pane -t mmclaw-main -p -S -
# Specific pane in window
tmux capture-pane -t mmclaw-main:0.0 -p
```

### Send Keys
```bash
# Send text (doesn't press Enter)
tmux send-keys -t mmclaw-main "hello"
# Send text + Enter
tmux send-keys -t mmclaw-main "y" Enter
# Send special keys
tmux send-keys -t mmclaw-main Enter
tmux send-keys -t mmclaw-main Escape
tmux send-keys -t mmclaw-main C-c          # Ctrl+C
tmux send-keys -t mmclaw-main C-d          # Ctrl+D (EOF)
tmux send-keys -t mmclaw-main C-z          # Ctrl+Z (suspend)
```

### Window/Pane Navigation
```bash
# Select window
tmux select-window -t mmclaw-main:0
# Select pane
tmux select-pane -t mmclaw-main:0.1
# List windows
tmux list-windows -t mmclaw-main
```

### Session Management
```bash
# Create new session
tmux new-session -d -s mmclaw-main
# Kill session
tmux kill-session -t mmclaw-4
# Rename session
tmux rename-session -t mmclaw-1 mmclaw-9
```

## Sending Input Safely
For interactive TUIs, split text and Enter into separate sends to avoid paste/multiline edge cases:
```bash
tmux send-keys -t mmclaw-main -l -- "Please apply the patch in src/foo.ts"
sleep 0.1
tmux send-keys -t mmclaw-main Enter
```

## Agent Session Patterns

### Check if Session Needs Input
```bash
# Look for prompts
tmux capture-pane -t mmclaw-3 -p | tail -10 | grep -E "❯|Yes.*No|proceed|permission"
```

### Approve Agent Prompt
```bash
# Send 'y' and Enter
tmux send-keys -t mmclaw-3 'y' Enter
# Or select numbered option
tmux send-keys -t mmclaw-3 '2' Enter
```

### Check All Sessions Status
```bash
for s in mmclaw-main mmclaw-1 mmclaw-2 mmclaw-3 mmclaw-4 mmclaw-5 mmclaw-6 mmclaw-7 mmclaw-8; do
  echo "=== $s ==="
  tmux capture-pane -t $s -p 2>/dev/null | tail -5
done
```

### Send Task to Session
```bash
tmux send-keys -t mmclaw-4 "Fix the bug in auth.js" Enter
```

## Notes
- Use `capture-pane -p` to print to stdout (essential for scripting)
- `-S -` captures entire scrollback history
- Target format: `session:window.pane` (e.g., `mmclaw-main:0.0`)
- Sessions persist across SSH disconnects