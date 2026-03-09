---
name: file-server-guard
description: Scan a directory for sensitive files before serving it over HTTP. Always run this before using the file-server skill.
metadata:
  { "mmclaw": { "emoji": "🛡️", "os": ["linux", "darwin", "win32"], "requires": { "bins": ["python"] } } }
---

# file-server-guard Skill (MMClaw)

This skill scans a target directory for sensitive files before it is exposed over HTTP. It is a mandatory prerequisite for the `file-server` skill.

## When to use

Always run this before starting a file server. Never skip it.

## Usage

Run the following Python script via `shell_execute`, replacing `<DIRECTORY>` with the target directory path:

```python
import os, fnmatch

SENSITIVE_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx",
    "id_rsa", "id_rsa.*", "id_ed25519", "id_ed25519.*",
    "*.ppk", "credentials", "credentials.*", "secrets.*",
    "*.secret", "token.*", "*.token", "config.json",
    "*.sqlite", "*.db", "shadow", "passwd",
    "*.ovpn", "*.crt", "*.cer",
]

directory = os.path.expanduser("<DIRECTORY>")
found = []

for root, dirs, files in os.walk(directory):
    # Skip hidden dirs like .git
    dirs[:] = [d for d in dirs if not d.startswith(".git")]
    for filename in files:
        for pattern in SENSITIVE_PATTERNS:
            if fnmatch.fnmatch(filename, pattern) or fnmatch.fnmatch(filename.lower(), pattern):
                rel = os.path.relpath(os.path.join(root, filename), directory)
                found.append(rel)
                break

if found:
    print("WARNING: Sensitive files detected in directory:")
    for f in found:
        print(f"  - {f}")
    print("\nDo NOT serve this directory without removing or excluding these files.")
    print("STATUS: UNSAFE")
else:
    print("No sensitive files detected.")
    print("STATUS: SAFE")
```

## After running

- If output contains `STATUS: UNSAFE`: **stop immediately**. Report the full list of flagged files to the user. Ask the user to either remove the sensitive files, or choose a different directory. Do NOT start the file server.
- If output contains `STATUS: SAFE`: inform the user the directory is clean and proceed with the `file-server` skill.

## Notes

- The scan is recursive — it checks all subdirectories
- `.git` directories are skipped (git internals, not user data)
- The patterns cover common credential, key, and config file formats
- The user can always override and proceed at their own risk, but you must explicitly warn them first
