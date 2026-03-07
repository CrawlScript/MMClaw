---
name: browser
description: Automate and interact with web browsers using Playwright. Use when the user wants to browse a URL, click elements, fill forms, take screenshots, scrape page content, or automate any browser interaction.
metadata:
  { "mmclaw": { "emoji": "🌐", "os": ["linux", "darwin", "win32"], "requires": { "bins": ["python"], "pip": ["playwright==1.58.0"] } } }
---

# Browser Skill

**NOTE: If browser tools are available (`browser_start`, `browser_navigate`, etc.), prefer those over this skill for common operations (navigate, click, fill, screenshot, get text). Use this skill only for complex multi-step automation or custom JS/scraping logic that the tools cannot handle.**

Use this skill when the user wants to automate complex browser workflows: multi-step sequences, JS evaluation, or custom scraping logic.

Trigger phrases: "scrape", "extract structured data", "run JS in browser", "automate multi-step browser task".

---

## CRITICAL RULES — Read Before Anything Else

**NEVER use `kill`, `pkill`, or any process signal on the browser or daemon.** Shutdown is always done by deleting `/tmp/mmclaw_browser_ws.txt`.

**NEVER restart the browser between operations.** Each user request is a new operation script that connects via CDP and disconnects — the browser stays open.

**NEVER take a screenshot unless the user explicitly asks for one.** Do not screenshot "to confirm" or "to show the result". If the user asked to navigate or click, just report the resulting URL and title in text.

**NEVER fall back to a standalone browser script if the daemon fails.** A standalone script opens an invisible headless browser the user cannot see, then closes it — this is useless. If the daemon fails, read the log, report the error to the user, and stop.

**Decision tree for every browser request:**

```
Is CDP port 9222 alive?  →  python -c "import urllib.request; urllib.request.urlopen('http://localhost:9222/json/version', timeout=2); print('RUNNING')"
  RUNNING → skip Step 1, go directly to Step 2
  DEAD    → run Step 1 to start the daemon, then Step 2
```

Use the CDP probe, not the WS file, to check liveness. The WS file can be stale (browser crashed but file remains). The port never lies.

---

## Dependencies

Do NOT run dependency checks before using this skill. Just proceed — if playwright is missing or browser binaries are not installed, the error will surface in the script output. At that point, tell the user to run:

- Missing package: `pip install "playwright==1.58.0"`
- Missing binaries: `playwright install chromium`

## Path Convention

All code examples use `/tmp/` as a placeholder. Always replace it with the real temp directory:

```python
import tempfile
TMP = tempfile.gettempdir()
```

Then use `f"{TMP}/mmclaw_browser_daemon.py"` etc. instead of `/tmp/mmclaw_browser_daemon.py`.

---

## Architecture — Persistent Browser via CDP

This skill launches a persistent browser with a fixed CDP debug port. The daemon holds the browser open. Each operation connects to it via CDP, does its work, then disconnects — without closing the browser.

```
shell_async: daemon (launch + CDP port 9222)  →  writes /tmp/mmclaw_browser_ws.txt
                                          │
                    ┌─────────────────────┼─────────────────────┐
              connect_over_cdp       connect_over_cdp       delete WS file
              + op 1 + disconnect    + op 2 + disconnect    → daemon closes browser
```

---

## Step 1 — Start the Browser Server

First, probe the CDP port to check if a browser is already running:

```python
import urllib.request
try:
    urllib.request.urlopen("http://localhost:9222/json/version", timeout=2)
    print("RUNNING")
except:
    print("DEAD")
```

If `RUNNING` → skip the rest of Step 1 and go to Step 2.

If `DEAD` → write this daemon script and launch it with `shell_async`:

**Write to `/tmp/mmclaw_browser_daemon.py`:**
```python
from playwright.sync_api import sync_playwright
import os, time

WS_FILE = "/tmp/mmclaw_browser_ws.txt"
CDP_URL = "http://localhost:9222"

try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=["--remote-debugging-port=9222"]
        )
        open(WS_FILE, "w").write(CDP_URL)
        print(f"Browser ready at {CDP_URL}", flush=True)
        # Keep alive: poll until the WS file is deleted (graceful shutdown signal)
        while os.path.exists(WS_FILE):
            time.sleep(1)
        browser.close()
    print("Browser stopped.", flush=True)
except Exception as e:
    print(f"ERROR: {e}", flush=True)
    raise
```

**Launch with `shell_async`:**
```
python /tmp/mmclaw_browser_daemon.py > /tmp/mmclaw_browser_daemon.log 2>&1
```

Then poll the CDP port until it responds (no fixed wait):

```python
import urllib.request, time, os
for _ in range(20):
    time.sleep(0.5)
    try:
        urllib.request.urlopen("http://localhost:9222/json/version", timeout=1)
        print("OK: browser ready")
        break
    except:
        pass
else:
    log = open("/tmp/mmclaw_browser_daemon.log").read() if os.path.exists("/tmp/mmclaw_browser_daemon.log") else "(no log)"
    print("ERROR: browser did not start.\n" + log)
```

If the browser did not start, read the daemon log and **report the exact error to the user**. Do NOT fall back to a standalone browser script — that will open an invisible, temporary browser that closes at the end of the script, which is not useful.

---

## Polling Helper

After every `shell_async` operation, use this `shell_execute` block to poll for results instead of a fixed `wait`:

```python
import time, os
out = "/tmp/mmclaw_browser_out.txt"  # adjust path to match the operation's output file
for _ in range(30):
    time.sleep(1)
    if os.path.exists(out):
        content = open(out).read()
        if "DONE" in content or "ERROR" in content:
            print(content)
            break
else:
    content = open(out).read() if os.path.exists(out) else "(no output)"
    print("TIMEOUT:", content)
```

Every operation script **must** end with `print("DONE", flush=True)` so the poller knows it finished.


---

## Step 2 — Run an Operation

Write an operation script and run it with `shell_async`. Always redirect output to a file, then `wait` and `file_read` the result.

**Operation script template — write to `/tmp/mmclaw_browser_op.py`:**
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://localhost:9222")

    # Reuse existing page if available, otherwise open a new one
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    # --- task ---
    page.goto("https://example.com")
    print("Title:", page.title(), flush=True)
    print("URL:", page.url, flush=True)
    # --- end task ---

    browser.disconnect()  # detach — does NOT close the browser

print("DONE", flush=True)  # sentinel — always keep this as the last line
```

**Launch with `shell_async`:**
```
python /tmp/mmclaw_browser_op.py > /tmp/mmclaw_browser_out.txt 2>&1
```

**Then poll for completion with `shell_execute` instead of a fixed wait:**
```python
import time, os
out = "/tmp/mmclaw_browser_out.txt"
for _ in range(30):
    time.sleep(1)
    if os.path.exists(out):
        content = open(out).read()
        if "DONE" in content or "ERROR" in content:
            print(content)
            break
else:
    content = open(out).read() if os.path.exists(out) else "(no output)"
    print("TIMEOUT:", content)
```

This returns as soon as the script finishes (usually 1–3s) rather than waiting a fixed amount. Maximum poll time is 30s as a safety cap.

---

## Step 3 — Close the Browser (Graceful Shutdown)

When the user is done, write and run this close script with `shell_async`:

**Write to `/tmp/mmclaw_browser_close.py`:**
```python
import os

ws_file = "/tmp/mmclaw_browser_ws.txt"
if not os.path.exists(ws_file):
    print("No browser server running.")
else:
    os.remove(ws_file)  # signals the daemon to call server.close() and exit
    print("Browser close signal sent. Server will shut down within 1-2 seconds.")
```

```
python /tmp/mmclaw_browser_close.py > /tmp/mmclaw_browser_out.txt 2>&1
```

Never use `kill` or `pkill`. Always shut down via this script.

---

## Common Operations

### Screenshot
Only take a screenshot when the user explicitly asks for one.
```python
page.screenshot(path="/tmp/browser_screenshot.png", full_page=True)
print("screenshot saved: /tmp/browser_screenshot.png")
```
After saving, use `file_upload` to send the file to the user.

### Extract page text
```python
print(page.inner_text("body"))
```

### Extract specific elements
```python
# First match
print(page.locator("h1").first.inner_text())

# All matches
for el in page.locator("ul.results li").all():
    print(el.inner_text())
```

### Click an element
```python
page.locator("button#submit").click()
page.wait_for_load_state("networkidle")
print("after click URL:", page.url)
```

### Fill a form
```python
page.locator("input[name='username']").fill("myuser")
page.locator("input[name='password']").fill("mypassword")
page.locator("button[type='submit']").click()
page.wait_for_load_state("networkidle")
print("logged in, URL:", page.url)
```

### Wait for an element
```python
page.wait_for_selector(".results", timeout=10000)
```

### Evaluate JavaScript
```python
import json as _json
links = page.evaluate("[...document.querySelectorAll('a')].map(a => a.href)")
print(_json.dumps(links, indent=2))
```

### Scrape structured data
```python
import json as _json
page.wait_for_selector(".product-card")
products = page.evaluate("""
    [...document.querySelectorAll('.product-card')].map(el => ({
        name:  el.querySelector('.name')?.innerText,
        price: el.querySelector('.price')?.innerText,
        url:   el.querySelector('a')?.href,
    }))
""")
print(_json.dumps(products, indent=2))
```

---

## Error Handling

| Error | Action |
|-------|--------|
| `ImportError: playwright` | Stop. Tell user: `pip install "playwright==1.58.0"` |
| `Executable doesn't exist` | Stop. Tell user: `playwright install chromium` |
| WS file missing when connecting | Server not started — run Step 1 first |
| `Connection refused` on connect | Server crashed — check `/tmp/mmclaw_browser_daemon.log`, restart |
| `TimeoutError` on selector | Element may not exist — try a broader selector |
| `TimeoutError` on navigation | Site is slow or URL is wrong — inform the user |
| Output file empty after wait | Wait more, read again; if still empty report the error |

On any error, print URL and title for debugging:
```python
try:
    print("URL:", page.url)
    print("Title:", page.title())
except Exception:
    pass
```

---

## Notes

- The WS endpoint file `/tmp/mmclaw_browser_ws.txt` is the source of truth for whether a server is running.
- `browser.disconnect()` detaches the script from the server — it does **not** close the browser or lose page state.
- `browser.close()` (in the close script) shuts down the server and all pages cleanly.
- Never use `kill` or `pkill` on the browser or daemon process.
- Use `full_page=True` in `screenshot()` to capture scrollable content.
- Only take screenshots when the user explicitly asks. Do not screenshot proactively.
- Never print passwords or secrets to output.
- For JS-heavy pages, use `wait_until="networkidle"` in `goto()` and `wait_for_selector()` before extracting content.
