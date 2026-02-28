---
name: skill-creator
description: Create or update MMClaw skills. Use this when the user wants to add new capabilities, automate a specific tool, or define complex multi-step workflows for the agent.
metadata:
  { "mmclaw": { "emoji": "🛠️", "os": ["linux", "darwin", "win32"], "requires": { "bins": [] } } }
---

# Skill Creator (MMClaw)

Use this skill to autonomously design, write, and deploy new skills to MMClaw. A skill is a directory containing a `skill.md` file that teaches the agent how to use a specific tool or perform a task.

Trigger phrases: "create a skill", "add a new skill", "make a skill for", "teach you how to use", "update the X skill".

## 1. Directory & File Structure

Skills MUST follow this exact structure to be detected:

- **Root Path**: `~/.mmclaw/skills/`
- **Skill Directory**: `~/.mmclaw/skills/<skill-name>/`
- **Main File**: `~/.mmclaw/skills/<skill-name>/skill.md`

### Naming Rules:
- **Directory Name**: Use lowercase kebab-case (e.g., `google-search`, `docker-manager`).
- **File Name**: Always `skill.md`.

## 2. Header Format (CRITICAL)

The `skill.md` file MUST start with a YAML-style frontmatter block. The formatting of the `metadata` line is extremely strict (single-line JSON).

### Header Example:
```markdown
---
name: my-skill-name
description: A concise one-sentence summary of what this skill does for the agent's index.
metadata:
  { "mmclaw": { "emoji": "🚀", "os": ["linux", "darwin", "win32"], "requires": { "bins": ["required-binary"] } } }
---
```

### Field Definitions:
- **name**: Must match the directory name.
- **description**: This is what the agent sees in its global "Available Skills" list. Make it clear and action-oriented.
- **metadata**:
  - **emoji**: A single representative emoji.
  - **os**: List of compatible operating systems (`linux`, `darwin`, `win32`).
  - **requires.bins**: List of CLI binaries that must be installed for this skill to work.

## 3. Content Structure

After the header, the `skill.md` should be a well-structured Markdown document containing:

1.  **Overview**: When and why to use the skill.
2.  **Trigger Phrases**: Common ways the user might ask for this skill.
3.  **Core Invocation**: Example shell commands (use `shell_execute` or `shell_async`).
4.  **Parameters/Args**: Explanation of available options.
5.  **Examples**: Realistic use cases.
6.  **Troubleshooting/Notes**: Edge cases or common errors.

## 4. Workflow for Creating a Skill

1.  **Research**: If the skill is for a CLI tool, run `--help` or check docs to understand its syntax.
2.  **Create Directory**: `mkdir -p ~/.mmclaw/skills/<name>`
3.  **Write `skill.md`**: Create the file with the correct header and detailed instructions.
4.  **Verify**: Ensure the file is saved.
5.  **Reload**: Call `shell_execute("ls ~/.mmclaw/skills")` or simply wait for the next turn; MMClaw will automatically detect the update and print `[*] Skill update detected.`

## 5. Implementation Tips

- **Be Specific**: Give the LLM exact commands to copy-paste.
- **Use Placeholders**: Use `<variable>` or `[optional]` for dynamic parts of commands.
- **Async vs Sync**: Instruct the agent to use `shell_async` for long-running processes (servers, watchers) and `shell_execute` for quick tasks.
- **Environment**: Always remind the agent to check the OS context before generating commands.
