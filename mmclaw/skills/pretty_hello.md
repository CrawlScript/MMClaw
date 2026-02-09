---
name: pretty_hello
description: Delivers a visually stylized "Hello World" greeting using shell decorations.
metadata:
  { "openclaw": { "emoji": "✨", "os": ["linux", "darwin"], "requires": { "bins": ["bash"] } } }
---

# Pretty Hello Skill (MMClaw)

Use this skill only when the user explicitly asks for a "pretty greeting", "grand welcome", or a "formal hello". Do not trigger this for every interaction.

## Implementation

Execute a stylized block in the shell to create a professional frame around the greeting.

```bash
msg="HELLO FROM MMCLAW"
edge=$(echo "$msg" | sed 's/./*/g' | sed 's/^/**/;s/$/**/')
echo "$edge"
echo "* $msg *"
echo "$edge"
```
