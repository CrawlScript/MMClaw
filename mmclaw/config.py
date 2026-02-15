import json
import os
import shutil
from pathlib import Path

class SkillManager(object):
    HOME_SKILLS_DIR = Path.home() / ".mmclaw" / "skills"
    PKG_SKILLS_DIR = Path(__file__).parent / "skills"

    @classmethod
    def sync_skills(cls):
        """Copy skills from package to ~/.mmclaw/skills if not exists."""
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
        "You are MMClaw, an autonomous AI agent. "
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
        "- file_upload(path)\n"
        "- wait(seconds)\n"
        "- reset_session() Use this when the user asks for a 'new session', 'fresh start', or to 'clear history'."
    )

    DEFAULT_CONFIG = {
        "engine_type": "openai",
        "engines": {
            "openai": {
                "model": "gpt-4o",
                "api_key": "sk-your-key-here",
                "base_url": "https://api.openai.com/v1"
            },
            "deepseek": {
                "model": "deepseek-chat",
                "api_key": "sk-your-key-here",
                "base_url": "https://api.deepseek.com"
            },
            "openrouter": {
                "model": "anthropic/claude-3.5-sonnet",
                "api_key": "sk-your-key-here",
                "base_url": "https://openrouter.ai/api/v1"
            },
            "openai_compatible": {
                "model": "llama3",
                "api_key": "sk-your-key-here",
                "base_url": "http://localhost:11434/v1"
            },
            "google": {
                "model": "gemini-1.5-pro",
                "api_key": "your-key-here",
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"
            }
        },
        "preferred_mode": "terminal",
        "connectors": {
            "telegram": {
                "token": "",
                "authorized_user_id": 0
            },
            "whatsapp": {
                "authorized_id": None
            },
            "feishu": {
                "app_id": "",
                "app_secret": "",
                "authorized_id": None
            }
        }
    }
    CONFIG_DIR = Path.home() / ".mmclaw"
    CONFIG_FILE = CONFIG_DIR / "mmclaw.json"

    @classmethod
    def load(cls):
        if not cls.CONFIG_DIR.exists():
            cls.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        
        if not cls.CONFIG_FILE.exists():
            return None
            
        try:
            config = json.load(open(cls.CONFIG_FILE, "r", encoding="utf-8"))
            needs_save = False

            # Migration: Engines
            if "engines" not in config:
                print("[*] Migrating legacy engine configuration...")
                new_engines = {}
                legacy_map = {1: "openai", 2: "deepseek", 3: "openrouter", 4: "openai_compatible"}
                
                e_type = config.get("engine_type", "openai")
                if isinstance(e_type, int):
                    e_type = legacy_map.get(e_type, "openai")
                
                active_engine_config = {
                    "model": config.get("model", cls.DEFAULT_CONFIG["engines"]["openai"]["model"]),
                    "api_key": config.get("api_key", "sk-xxx"),
                    "base_url": config.get("base_url", "https://api.openai.com/v1")
                }
                
                for k, v in cls.DEFAULT_CONFIG["engines"].items():
                    new_engines[k] = v.copy()
                new_engines[e_type] = active_engine_config
                
                config["engines"] = new_engines
                config["engine_type"] = e_type
                
                for key in ["model", "api_key", "base_url"]:
                    if key in config: del config[key]
                needs_save = True

            # Migration: Fix Google Base URL (add /openai if missing)
            if "engines" in config and "google" in config["engines"]:
                g_config = config["engines"]["google"]
                if g_config.get("base_url") == "https://generativelanguage.googleapis.com/v1beta":
                    print("[*] Updating Google Gemini base_url to OpenAI-compatible endpoint...")
                    g_config["base_url"] = "https://generativelanguage.googleapis.com/v1beta/openai"
                    needs_save = True

            # Migration: Connectors
            if "connectors" not in config:
                print("[*] Migrating legacy connector configuration...")
                config["connectors"] = {
                    "telegram": {
                        "token": config.get("telegram_token", ""),
                        "authorized_user_id": config.get("telegram_authorized_user_id", 0)
                    },
                    "whatsapp": {
                        "authorized_id": config.get("whatsapp_authorized_id")
                    },
                    "feishu": {
                        "app_id": config.get("feishu_app_id", ""),
                        "app_secret": config.get("feishu_app_secret", ""),
                        "authorized_id": config.get("feishu_authorized_id")
                    }
                }
                # Clean up legacy flat keys
                legacy_keys = [
                    "telegram_token", "telegram_authorized_user_id",
                    "whatsapp_authorized_id",
                    "feishu_app_id", "feishu_app_secret", "feishu_authorized_id"
                ]
                for key in legacy_keys:
                    if key in config: del config[key]
                needs_save = True

            if needs_save:
                cls.save(config)
                
            return config
        except Exception as e:
            print(f"[!] Error loading config: {e}")
            return None

    @classmethod
    def save(cls, config):
        with open(cls.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        print(f"[*] Config saved to {cls.CONFIG_FILE}")

    @classmethod
    def get_full_prompt(cls, mode="terminal"):
        """Combine base prompt with synchronized skills and interface context."""
        SkillManager.sync_skills()
        
        interface_context = f"\n\n[INTERFACE CONTEXT]\nYou are currently responding via: {mode.upper()}\n"
        if mode == "telegram":
            interface_context += (
                "Formatting Guidelines: Use standard Markdown. You can use bold, italics, and code blocks. "
                "Telegram supports rich media, so feel free to be expressive.\n"
            )
        elif mode == "whatsapp":
            interface_context += (
                "Formatting Guidelines: Use WhatsApp-specific formatting: *bold*, _italic_, ~strikethrough~, "
                "and ```monospace```. Keep messages relatively concise as they are read on mobile.\n"
            )
        else:
            interface_context += (
                "Formatting Guidelines: Use plain text for the terminal. Use simple ASCII characters "
                "for lists (e.g., - or *) and tables. Avoid complex markdown that doesn't render in a shell.\n"
            )

        return cls.BASE_SYSTEM_PROMPT + interface_context + SkillManager.get_skills_prompt()