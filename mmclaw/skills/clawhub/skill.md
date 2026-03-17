---
name: clawhub
description: Browse, search, and install skills from the CrawHub skill marketplace.
metadata:
  { "mmclaw": { "emoji": "🏪", "os": ["darwin", "linux", "windows"] } }
---
# CrawHub Skill Marketplace

Browse and install community skills from CrawHub.

## When to Use
✅ **USE this skill when:**
- User wants to find or install a new skill
- User asks what skills are available
- User wants to update or reinstall an existing skill

## URLs

### Browse all skills (sorted by downloads)
```
https://clawhub.ai/skills?sort=downloads&nonSuspicious=true
```

### Search by keyword
```
https://clawhub.ai/skills?nonSuspicious=true&q=KEYWORD
```
When the user provides a skill name, construct the search URL with their keyword and show it as the primary option. Also show the browse URL as a fallback if the search doesn't return the right result.

> ⚠️ Do NOT curl/fetch CrawHub pages unless the user explicitly asks — the site has rate limits.

## Getting the Download URL (for Telegram/WhatsApp users)

Since users on mobile connectors can't run terminal commands directly:

1. Construct the search URL with the user's keyword and send it as the primary link. Also mention the browse URL as a fallback if the result isn't what they want.
2. Ask them to open the search URL, find the skill, and click into it
3. On the skill page: **right-click the "Download Zip" button → "Copy Link"**
4. Ask them to paste the copied link back into the chat

Then install it:
```bash
mmclaw skill install <pasted-url>
```

If you get `already exists. Use --force to replace it.`, ask the user:
> "Skill X already exists. Replace it?"
- User says yes → run `mmclaw skill install --force <pasted-url>`
- User says no → abort

## Local Commands

```bash
# List installed skills
mmclaw skill list

# Install from URL — always try without --force first
mmclaw skill install <url>

# Install from local directory
mmclaw skill install /path/to/skill-dir

# Uninstall
mmclaw skill uninstall <skill-name>
```
