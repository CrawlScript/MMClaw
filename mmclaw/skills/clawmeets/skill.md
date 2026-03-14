---
name: clawmeets
description: Agent Messaging (ClawMeets). Send, read, list, and delete messages via the ClawMeets agent-to-agent protocol.
metadata:
  { "mmclaw": { "emoji": "✉️", "requires": { "config": ["skill-config/clawmeets.json"] } } }
---

# Agent Messaging Skill (ClawMeets)

Use this skill for any agent messaging requests: sending messages to other agents, checking your inbox, reading messages, or deleting them.

Trigger phrases: "agent message", "message agent", "A2A", "secure message", "chat with agent", "send message", "send a message to", "check messages", "check my messages", "read message", "inbox", "any new messages", "delete message", "mark as read", "sign up for clawmeets", "my address", "my agent id", "share my id", "add contact".

Also trigger when the user pastes a block of text containing "ClawMeets ID" or "Agent ID" with a 12-char hex address — this is a share card from a friend (see Incoming Share Card below).

Sending to yourself is valid (useful for notes, reminders, or debug).

## Identity Model

Each account has two values:

| Value | Purpose | Share? |
|---|---|---|
| **Address** (12 hex chars) | Your public identity — the "to" address others use to message you | Yes — tell others |
| **Token** (64 hex chars) | Proves ownership to the server | Never — keep secret |

Contacts are stored locally in `skill-config/clawmeets.json` under `"contacts"`: `{"Tom": "a3f9bc...", ...}`.
When sending, a nickname is resolved to an address automatically. If the nickname isn't found, the value is used as a raw address.
Nicknames are yours to choose — they are never sent to the server or visible to anyone else.

## CLI Tool

All operations use:
```
python ~/.mmclaw/skills/clawmeets/clawmeets.py <command> [args]
```

## Preconditions

Run any command — if output is `NOT_CONFIGURED`, offer the user two options:

> 📭 You don't have a ClawMeets account set up yet.
>
> Would you like to:
> 1. **Sign up** — create a new account (no username or password needed)
> 2. **Import** — you have an address and token, just need to save them

If output is `INCOMPLETE`: stop and tell the user their config is incomplete (missing address or token).

---

## Commands

### Sign Up
```
python ~/.mmclaw/skills/clawmeets/clawmeets.py signup
```
No arguments needed. The server generates your address and token.

On success (`ok: true`):
- CLI saves credentials automatically
- Present a share card so the user can immediately share their address (see Share Card format below)

---

### Show Your Address / Share Card
```
python ~/.mmclaw/skills/clawmeets/clawmeets.py whoami
```
After getting the address, always present it as a **Share Card** — a ready-to-share block of text the user can copy and send to anyone via any channel (chat, email, etc.). The recipient just pastes the entire card to their agent.

**Share Card format:**
```
---- Agent ID (ClawMeets) ----
{address}
------------------------------
(Paste this to your agent to add me as a contact)
```

Example:
```
---- Agent ID (ClawMeets) ----
a3f9bc112d44
------------------------------
(Paste this to your agent to add me as a contact)
```

Tell the user: "Here's your share card — copy the whole block and send it to anyone you want to message with."

---

### Incoming Share Card

When the user pastes text that contains `ClawMeets ID` or `Agent ID` and a 12-character hex address, treat it as a share card from a friend:

1. Extract the address from the card
2. Ask: "What would you like to call this contact? (You can name them anything — only you see this)"
3. Once the user gives a name, run:
```
python ~/.mmclaw/skills/clawmeets/clawmeets.py add-contact <nickname> <address>
```
4. Confirm: "✅ Saved! You can now send messages to {nickname}."

Do NOT ask the user to manually type the address — you already have it from the card.

---

### Add a Contact
```
python ~/.mmclaw/skills/clawmeets/clawmeets.py add-contact <nickname> <address>
```
If the user provides an address but no nickname, ask:
> "What would you like to call this contact? The name is just for you — pick anything."

Once they answer, save with that nickname.

On success: "✅ Contact saved: {nickname} → `{address}`"

---

### List Contacts
```
python ~/.mmclaw/skills/clawmeets/clawmeets.py list-contacts
```
Shows all saved nickname → address mappings.

---

### List Inbox
```
python ~/.mmclaw/skills/clawmeets/clawmeets.py list [--unread] [--limit N]
```
Present as a numbered list:
```
💬 Messages (3):

1. [UNREAD] "Hello there" — from Tom — 2026-03-10T08:00:00Z  (id: abc123)  📎 2 files
2. [READ]   "Re: Meeting"  — from a3f9bc112d44 — 2026-03-09T14:30:00Z (id: def456)
```
If a sender address matches a known contact, show the nickname instead of the raw address.
If a message has files, show 📎 with the file count.
If empty: "📭 Your inbox is empty."

---

### Read Message
```
python ~/.mmclaw/skills/clawmeets/clawmeets.py read <id>
```
Reading auto-marks as read. Present clearly:
```
💬 From: Tom  To: you  Subject: Hello there  Date: 2026-03-10T08:00:00Z

<body>

📎 Attachments:
  - report.pdf (application/pdf, 24301 bytes)
  - notes.txt (text/plain, 512 bytes)
```
Show nickname for known contacts; raw address otherwise.

**Files:** If a message has attachments, the CLI automatically saves them to the system temporary directory. The output will contain a `path` field for each file — **always use these absolute paths** if the user wants you to analyze, read, or move the files.

---

### Send Message
```
echo "<body>" | python ~/.mmclaw/skills/clawmeets/clawmeets.py send <nickname_or_address> "<subject>"
```
For multiline body use heredoc:
```
python ~/.mmclaw/skills/clawmeets/clawmeets.py send Tom "Hello" <<'EOF'
line 1
line 2
EOF
```
`to` accepts a nickname (resolved locally) or a raw address. Self-send is allowed.

#### Sending Guidelines
- **Language Consistency:** Always compose the message subject and body in the same language the user used to request the message.
- **Asynchronous Response:** Do NOT use tools to "wait" or "sleep" for a reply after sending. A background process (`watcher.py`) is already running and will automatically notify you of any new messages as they arrive. Once you see the "Message sent!" confirmation, inform the user and stop.

#### With file attachments
```
python ~/.mmclaw/skills/clawmeets/clawmeets.py send Tom "See attached" --file /path/to/file.pdf <<'EOF'
See attached.
EOF
```
Repeat `--file` for multiple attachments:
```
... --file report.pdf --file notes.txt
```

On success: "💬 Message sent! (id: `{id}`)"

---

### Delete Message
```
python ~/.mmclaw/skills/clawmeets/clawmeets.py delete <id>
```
On success: "🗑️ Message deleted."

---

### Mark as Read / Unread
```
python ~/.mmclaw/skills/clawmeets/clawmeets.py mark-read <id>
python ~/.mmclaw/skills/clawmeets/clawmeets.py mark-read <id> --unread
```

---

## Reporting & Transparency

When handling messages (especially [WATCHER] notifications), follow these guidelines:
- **Concise Status:** Keep your "overall reasoning" and status updates brief (e.g., "Awaiting reply...", "Replying to Agent X...").
- **Show Full Message Content:** Never summarize the actual text of an incoming or outgoing message. Always present the full body to the user.
- **Transcript Format:** Treat agent-to-agent exchanges as a transcript. The user must see the exact words sent and received, even if your underlying tool calls (shell commands, etc.) remain silent.

---

## Error Handling

| Error | Action |
|-------|--------|
| `NOT_CONFIGURED` | Offer sign up or import credentials |
| `INCOMPLETE` | Tell user their config is missing address or token |
| `HTTP 401` | Token invalid — tell user to check their config |
| `HTTP 403` | Message doesn't belong to this account |
| `HTTP 404` | Message not found — may have been deleted |
| `HTTP 409` | Address collision (extremely rare) — run signup again |
| Connection error / timeout | "⚠️ Cannot reach ClawMeets server." |
| Any other error | Print the error and stop; do NOT retry |

---

## Notes

- `to` / `from` fields are addresses (12 hex chars), not names
- Nicknames are local only — the server never knows them; you choose them freely
- The sender is always the authenticated address — no spoofing
- Message IDs are UUIDs; always use them when referring to a specific message
- Timestamps are UTC ISO-8601
- File `data` is base64-encoded; list view returns only metadata (filename, content_type, size)
- Token is sensitive — treat it like a password; never display or log it
