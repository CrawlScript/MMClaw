import json
import os
import shutil
from pathlib import Path

class SkillManager(object):
    HOME_SKILLS_DIR = Path.home() / ".pipclaw" / "skills"
    PKG_SKILLS_DIR = Path(__file__).parent / "skills"

    @classmethod
    def sync_skills(cls):
        """Copy skills from package to ~/.pipclaw/skills if not exists."""
        if not cls.HOME_SKILLS_DIR.exists():
            cls.HOME_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        
        if cls.PKG_SKILLS_DIR.exists():
            for skill_file in cls.PKG_SKILLS_DIR.glob("*.md"):
                dest = cls.HOME_SKILLS_DIR / skill_file.name
                if not dest.exists():
                    shutil.copy(skill_file, dest)

    @classmethod
    def get_skills_prompt(cls):
        """Read all skills and format them for the system prompt."""
        if not cls.HOME_SKILLS_DIR.exists():
            return ""
        
        skills_text = "\n\nAvailable Skills:\n"
        for skill_file in cls.HOME_SKILLS_DIR.glob("*.md"):
            try:
                content = skill_file.read_text(encoding="utf-8")
                # We strip the frontmatter for the prompt to save tokens
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        content = parts[2].strip()
                skills_text += f"\n--- Skill: {skill_file.stem} ---\n{content}\n"
            except Exception:
                continue
        return skills_text

class ConfigManager(object):
    BASE_SYSTEM_PROMPT = (
        "You are PipClaw, an autonomous AI agent. "
        "You MUST always respond with a SINGLE valid JSON object. "
        "Do not include any text outside the JSON block.\n\n"
        "IMPORTANT: When you use 'tools', you MUST STOP your response immediately after the JSON block. "
        "Do not simulate the tool output. Wait for the system to provide the result.\n\n"
        "Structure:\n"
        "{\n"
        "  \"thought\": \"your reasoning\",\n"
        "  \"tools\": [\n"
        "    {\"name\": \"tool_name\", \"args\": {\"arg1\": \"val1\"}}\n"
        "  ],\n"
        "  \"content\": \"message to user\"\n"
        "}\n\n"
        "Available Tools:\n"
        "- shell_execute(command)\n"
        "- file_read(path)\n"
        "- file_write(path, content)\n"
        "- file_upload(path)"
    )

    DEFAULT_CONFIG = {
        "engine_type": "deepseek",
        "model": "deepseek-chat",
        "api_key": "sk-your-key-here",
        "base_url": "https://api.deepseek.com",
        "telegram_token": "your-bot-token-here",
        "telegram_authorized_user_id": 0,
        "whatsapp_authorized_id": None,
        "preferred_mode": "terminal"
    }
    CONFIG_DIR = Path.home() / ".pipclaw"
    CONFIG_FILE = CONFIG_DIR / "pipclaw.json"

    @classmethod
    def load(cls):
        if not cls.CONFIG_DIR.exists():
            cls.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return json.load(open(cls.CONFIG_FILE, "r", encoding="utf-8")) if cls.CONFIG_FILE.exists() else None

    @classmethod
    def save(cls, config):
        with open(cls.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        print(f"[*] Config saved to {cls.CONFIG_FILE}")

    @classmethod
    def get_full_prompt(cls):
        """Combine base prompt with synchronized skills."""
        SkillManager.sync_skills()
        return cls.BASE_SYSTEM_PROMPT + SkillManager.get_skills_prompt()