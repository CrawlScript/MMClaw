---
name: ngrok
description: Expose a local port to the public internet using ngrok. Use when the user wants a public URL for a locally running web service.
metadata:
  { "mmclaw": { "emoji": "🌐", "os": ["linux", "darwin", "win32"], "requires": { "bins": ["python3"] } } }
---

# ngrok Skill (MMClaw)

Use this skill when the user wants to expose a local server to the public internet. Trigger phrases: "ngrok", "public URL", "expose my server", "tunnel", "access from outside".

Do NOT run `which ngrok` or check for a `ngrok` binary. There is no standalone `ngrok` command. ngrok is installed as a Python package and must always be invoked via Python.

## Install

Prompt the user to install manually first. Only run automatically if the user explicitly asks for help.

```bash
pip install ngrok
```

## Configuration

The authtoken is stored at `~/.mmclaw/skill-config/ngrok.json`:

```json
{
  "authtoken": "your_token_here"
}
```

Get your token at: https://dashboard.ngrok.com/get-started/your-authtoken

### If the config file does not exist

Ask the user for their authtoken, then create the file:

```python
import json, os
config = {"authtoken": "<token_provided_by_user>"}
path = os.path.expanduser("~/.mmclaw/skill-config/ngrok.json")
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w") as f:
    json.dump(config, f, indent=2)
print(f"Config saved to {path}")
```

## Usage

### Step 1 — Start tunnel in background using `shell_async`

Use the `shell_async` tool for this command to ensure it runs in the background without blocking. Do NOT append `&`.

```bash
python -c "
import ngrok, json, os, threading
config = json.load(open(os.path.expanduser('~/.mmclaw/skill-config/ngrok.json')))
url_path = os.path.expanduser('~/.mmclaw/skill-config/ngrok_url.txt')
listener = ngrok.forward(<PORT>, authtoken=config['authtoken'])
open(url_path, 'w').write(listener.url())
threading.Event().wait()
"
```

### Step 2 — Read and report the URL

```bash
sleep 2 && cat ~/.mmclaw/skill-config/ngrok_url.txt
```

## IMPORTANT — always report the URL

After Step 2, you MUST capture the contents of `ngrok_url.txt` and explicitly report the public URL to the user in your response. Do NOT tell the user to "check the terminal". The URL must appear directly in your reply.

## Notes

- The tunnel stays alive as long as the background process is running
- Free tier: one tunnel at a time, URL changes on each restart
- Paid tier: static domains, multiple concurrent tunnels
- To stop the tunnel, kill the background Python process