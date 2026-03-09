---
name: file-server
description: Start a local HTTP file server to share files in a directory over the network. Use when the user wants to serve or share files via a browser or HTTP.
metadata:
  { "mmclaw": { "emoji": "📡", "os": ["linux", "darwin", "win32"], "requires": { "bins": ["python"] } } }
---

# file-server Skill (MMClaw)

Use this skill when the user wants to serve files from a local directory over HTTP. Trigger phrases: "file server", "serve files", "share files", "http server", "serve this directory".

## IMPORTANT — Security Check Required

**Before starting the server, you MUST run the `file-server-guard` skill first.**

Read and execute `file-server-guard` using `file_read` on its skill path, then run the guard scan. Only proceed to start the server after the user has reviewed the guard output and confirmed it is safe to continue.

Do NOT skip this step, even if the user seems in a hurry.

## Usage

### Step 1 — Run file-server-guard (mandatory)

Read the file-server-guard skill and run the scan on the target directory before doing anything else.

### Step 2 — Start the server

After guard confirmation, start the server in the background using `shell_async`. Do NOT append `&`.

```bash
python -m http.server <PORT> --directory <DIRECTORY>
```

Replace `<PORT>` with the user's requested port (default: 8000) and `<DIRECTORY>` with the target directory (default: current directory).

### Step 3 — Report to user

Tell the user:
- The local URL: `http://localhost:<PORT>`
- The network URL: `http://<local-ip>:<PORT>` (get local IP via `hostname -I` or `ipconfig`)
- Which directory is being served
- How to stop: ask you to stop the file server

## Stopping the server

To stop the server, kill the background Python process:

```bash
pkill -f "http.server <PORT>"
```

## Notes

- All files in the directory (and subdirectories) are publicly accessible to anyone who can reach the port
- No authentication is provided by default
- Do NOT serve sensitive directories like `~`, `~/Documents`, or any directory the guard flagged
