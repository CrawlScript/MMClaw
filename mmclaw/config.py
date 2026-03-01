import json
import os
import shutil
from pathlib import Path
import platform

class SkillManager(object):
    HOME_SKILLS_DIR = Path.home() / ".mmclaw" / "skills"
    PKG_SKILLS_DIR = Path(__file__).parent / "skills"
    
    _cache_prompt = None
    _cache_mtime = 0

    @classmethod
    def sync_skills(cls):
        """Copy skill directories from package to ~/.mmclaw/skills."""
        if not cls.HOME_SKILLS_DIR.exists():
            cls.HOME_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

        if cls.PKG_SKILLS_DIR.exists():
            for skill_dir in cls.PKG_SKILLS_DIR.iterdir():
                if not skill_dir.is_dir():
                    continue
                dest = cls.HOME_SKILLS_DIR / skill_dir.name
                # Only copy if it doesn't exist to avoid overwriting user changes or causing unnecessary mtime updates
                if not dest.exists():
                    shutil.copytree(skill_dir, dest)

    @classmethod
    def _parse_frontmatter(cls, text):
        """Return (meta_dict, body) parsed from YAML-style frontmatter."""
        if not text.startswith("---"):
            return {}, text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}, text
        meta = {}
        for line in parts[1].splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                meta[key.strip()] = val.strip()
        return meta, parts[2].strip()

    @classmethod
    def get_skills_prompt(cls, force=False):
        """Build a lightweight skills index for the system prompt.
        
        Uses mtime caching and partial reads to avoid redundant filesystem scans.
        """
        if not cls.HOME_SKILLS_DIR.exists():
            return ""

        try:
            # Detect additions, removals, and changes to any skill.md
            current_mtime = cls.HOME_SKILLS_DIR.stat().st_mtime
            for skill_dir in cls.HOME_SKILLS_DIR.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "skill.md"
                    if skill_file.exists():
                        current_mtime = max(current_mtime, skill_file.stat().st_mtime)
            
            if not force and cls._cache_prompt is not None and current_mtime <= cls._cache_mtime:
                return cls._cache_prompt
        except Exception:
            current_mtime = 0

        # Only print if this isn't the first time loading (bootup)
        if cls._cache_prompt is not None:
            print("[*] Skill update detected.")

        entries = []
        # Sort by directory name for stable prompt (LLM KV cache friendly)
        for skill_dir in sorted(cls.HOME_SKILLS_DIR.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "skill.md"
            if not skill_file.exists():
                continue
            try:
                # Read only first 2KB for frontmatter to save IO
                with open(skill_file, "r", encoding="utf-8") as f:
                    head = f.read(2048)
                meta, _ = cls._parse_frontmatter(head)
            except Exception:
                continue
            
            # Defensive: only include skills that are "ready" (have a name)
            name = meta.get("name")
            if not name:
                continue
            
            description = meta.get("description", "")
            entries.append(f"- name: {name}\n  description: {description}\n  path: {skill_file}")

        if not entries:
            cls._cache_prompt = ""
            cls._cache_mtime = current_mtime
            return ""

        skills_text = (
            "\n\n[SKILLS SECTION]\n"
            "The following skills are available. Do NOT execute a skill unless the user's request requires it.\n"
            "To get full instructions for a skill, call file_read(<path>) before using it.\n\n"
            "Available Skills:\n"
        ) + "\n".join(entries) + "\n"
        
        cls._cache_prompt = skills_text
        cls._cache_mtime = current_mtime
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
        "- shell_execute(command): Executes a command and returns the output. Use this for tasks that finish quickly.\n"
        "- shell_async(command): Starts a long-running command (like a server or listener) in the background. Does not return output. "
        "IMPORTANT: Do NOT append ' &' to the command; the tool handles backgrounding automatically.\n"
        "- file_read(path)\n"
        "- file_write(path, content)\n"
        "- file_upload(path)\n"
        "- wait(seconds)\n"
        "- reset_session() Use this when the user asks for a 'new session', 'fresh start', or to 'clear history'.\n\n"
        "IMPORTANT: For long-running or blocking commands (e.g. starting a server, running ngrok, or any process "
        "that does not exit on its own), you MUST use 'shell_async'. "
        "Using 'shell_execute' for these will cause the agent to hang.\n\n"
        "IMPORTANT: When creating files and no destination path is specified by the user, always write to the "
        "system temp directory. The agent's working directory is an internal path with no meaning to the user."
    )

    DEFAULT_CONFIG = {
        "engine_type": "openai",
        "engines": {
            "openai": {
                "model": "gpt-4o",
                "api_key": None,
                "base_url": "https://api.openai.com/v1"
            },
            "codex": {
                "model": "gpt-5.2",
                "api_key": None,
                "base_url": "https://api.openai.com/v1"
            },
            "deepseek": {
                "model": "deepseek-chat",
                "api_key": None,
                "base_url": "https://api.deepseek.com"
            },
            "openrouter": {
                "model": "anthropic/claude-3.5-sonnet",
                "api_key": None,
                "base_url": "https://openrouter.ai/api/v1"
            },
            "kimi": {
                "model": "kimi-k2.5",
                "api_key": None,
                "base_url": "https://api.moonshot.cn/v1"
            },
            "openai_compatible": {
                "model": "llama3",
                "api_key": None,
                "base_url": "http://localhost:11434/v1"
            },
            "google": {
                "model": "gemini-1.5-pro",
                "api_key": None,
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"
            }
        },
        "connector_type": "terminal",
        "connectors": {
            "telegram": {
                "token": None,
                "authorized_user_id": 0
            },
            "whatsapp": {
                "authorized_id": None
            },
            "feishu": {
                "app_id": None,
                "app_secret": None,
                "authorized_id": None
            },
            "qqbot": {
                "app_id": None,
                "app_secret": None
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

            # Migration: preferred_mode -> connector_type
            if "preferred_mode" in config:
                print("[*] Migrating 'preferred_mode' to 'connector_type'...")
                config["connector_type"] = config.pop("preferred_mode")
                needs_save = True

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
        """Combine base prompt with skills and interface context.
        
        Note: sync_skills should be called once at startup, not here, 
        to allow for fast frequent refreshes of the prompt index.
        """
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

        os_context = (
            f"\n\n[SYSTEM ENVIRONMENT]\n"
            f"Operating System: {platform.platform()}\n"
            "IMPORTANT: When generating shell commands, always use syntax compatible with the above OS.\n"
        )

        # print("================\n" + os_context)

        return cls.BASE_SYSTEM_PROMPT + os_context + interface_context + SkillManager.get_skills_prompt()
