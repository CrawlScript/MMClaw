import json
import os
import shutil
from pathlib import Path
import platform
from .tools import ShellTool
from .memory import MAX_MEMORY_ENTRY_CHARS, MAX_TOTAL_MEMORY_CHARS

def _find_file_icase(directory: Path, name: str):
    """Return path to `name` inside `directory`, matching case-insensitively.
    Returns the exact-case path if it exists, otherwise the first case-insensitive match,
    or None if not found."""
    exact = directory / name
    if exact.exists():
        return exact
    name_lower = name.lower()
    try:
        for entry in directory.iterdir():
            if entry.name.lower() == name_lower:
                return entry
    except Exception:
        pass
    return None


def set_workspace(path: Path):
    """Override the default workspace directory. Must be called before any config/skill access."""
    path = path.expanduser().resolve()
    SkillManager.HOME_DIR = path
    SkillManager.HOME_SKILLS_DIR = path / "skills"
    SkillManager.HOME_KG_DIR = path / "skill-kg"
    SkillManager.HOME_KG_MAIN = path / "skill-kg" / "skill-kg-main.md"
    SkillManager.HOME_KG_USER = path / "skill-kg" / "skill-kg-user.md"
    ConfigManager.CONFIG_DIR = path
    ConfigManager.CONFIG_FILE = path / "mmclaw.json"
    # Patch other modules (late imports are safe — all modules are loaded before main() calls this)
    from .memory import FileMemory
    FileMemory.SESSIONS_DIR = str(path / "memory" / "sessions")
    FileMemory.GLOBAL_MEMORY_FILE = str(path / "memory" / "global" / "memory.jsonl")
    from .kernel import HeartbeatManager, CronManager
    HeartbeatManager.HEARTBEAT_DIR = path / "heartbeat"
    HeartbeatManager.CONFIG_FILE = path / "heartbeat" / "heartbeat-config.json"
    HeartbeatManager.LOG_FILE = path / "heartbeat" / "heartbeat-log.jsonl"
    HeartbeatManager.SKILLS_DIR = path / "skills"
    CronManager.CRON_DIR  = path / "cron"
    CronManager.JOBS_FILE = path / "cron" / "cron-jobs.jsonl"
    from .watcher import WatcherManager
    WatcherManager.SKILLS_DIR = path / "skills"
    from .tools import BrowserTool
    BrowserTool.DEFAULT_DATA_DIR = str(path / "browser_data")


class SkillManager(object):
    HOME_DIR = Path.home() / ".mmclaw"
    HOME_SKILLS_DIR = Path.home() / ".mmclaw" / "skills"
    PKG_SKILLS_DIR = Path(__file__).parent / "skills"
    PKG_KG_DIR = Path(__file__).parent / "skill-kg"
    HOME_KG_DIR = Path.home() / ".mmclaw" / "skill-kg"
    HOME_KG_MAIN = Path.home() / ".mmclaw" / "skill-kg" / "skill-kg-main.md"
    HOME_KG_USER = Path.home() / ".mmclaw" / "skill-kg" / "skill-kg-user.md"

    _cache_prompt = None
    _cache_mtime = 0

    @classmethod
    def sync_skills(cls):
        """Copy skill directories and KG files from package to ~/.mmclaw/."""
        cls.HOME_DIR.mkdir(parents=True, exist_ok=True)
        if cls.HOME_SKILLS_DIR.exists() is False:
            cls.HOME_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        if cls.PKG_SKILLS_DIR.exists():
            for skill_dir in cls.PKG_SKILLS_DIR.iterdir():
                if not skill_dir.is_dir():
                    continue
                dest = cls.HOME_SKILLS_DIR / skill_dir.name
                shutil.copytree(skill_dir, dest, dirs_exist_ok=True)

        # Sync KG dir (always overwrite main, never touch user file)
        cls.HOME_KG_DIR.mkdir(parents=True, exist_ok=True)
        if cls.PKG_KG_DIR.exists():
            shutil.copy2(cls.PKG_KG_DIR / "skill-kg-main.md", cls.HOME_KG_MAIN)

        # Create user KG file only if it doesn't exist yet
        if not cls.HOME_KG_USER.exists():
            cls.HOME_KG_USER.write_text(
                "# MM-SkillKG — User Custom Relations\n"
                "# Add your own relations here. This file is never overwritten by mmclaw updates.\n"
                "# Format: entity_a, [relation], entity_b  # optional comment\n\n",
                encoding="utf-8"
            )

    @classmethod
    def _parse_kg_file(cls, path):
        """Parse a .md KG file into a list of (a, relation, b, comment) tuples."""
        triples = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                comment = ""
                if "#" in line:
                    line, _, comment = line.partition("#")
                    comment = comment.strip()
                parts = [p.strip() for p in line.split(",")]
                if len(parts) != 3:
                    continue
                a, rel, b = parts
                rel = rel.strip("[]")
                if a and rel and b:
                    triples.append((a, rel, b, comment))
        except Exception:
            pass
        return triples

    @classmethod
    def get_skill_kg_prompt(cls):
        """Load and merge main + user KG files into a prompt section."""
        triples = cls._parse_kg_file(cls.HOME_KG_MAIN) + cls._parse_kg_file(cls.HOME_KG_USER)
        if not triples:
            return ""
        lines = [f"- {a} [{rel}] {b}" + (f"  # {c}" if c else "") for a, rel, b, c in triples]
        return (
            "\n\n[SKILL KNOWLEDGE GRAPH]\n"
            "These are known relations between skills and concepts. "
            "Use them to reason about dependencies and safety before activating a skill.\n\n"
        ) + "\n".join(lines) + "\n"

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
                    skill_file = _find_file_icase(skill_dir, "skill.md")
                    if skill_file:
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
            skill_file = _find_file_icase(skill_dir, "skill.md")
            if not skill_file:
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
        "}\n"
        "IMPORTANT: \"content\" MUST be a plain string. Never nest JSON objects or arrays inside \"content\".\n\n"
        "Available Tools:\n"
        f"- shell_execute(command): Executes a command and returns the output. Times out after {ShellTool.TIMEOUT}s. Use this for tasks that finish quickly.\n"
        "- shell_async(command): Starts a long-running command (like a server or listener) in the background. Does not return output. "
        "IMPORTANT: Do NOT append ' &' to the command; the tool handles backgrounding automatically.\n"
        "- file_read(path)\n"
        "- file_write(path, content)\n"
        "- file_upload(path)\n"
        "- wait(seconds)\n"
        "- reset_session() Use this when the user asks for a 'new session', 'fresh start', or to 'clear history'.\n"
        "- upgrade() Upgrades MMClaw to the latest version via pip and restarts the process. Use when the user asks to upgrade or update MMClaw.\n"
        f"- memory_add(memory): Saves a fact to global memory (persisted across all sessions). Max {MAX_MEMORY_ENTRY_CHARS} chars per entry, {MAX_TOTAL_MEMORY_CHARS} chars total. Keep each memory as short as possible while preserving the key information — prefer dense, keyword-style facts over full sentences.\n"
        "- memory_list(): Lists all global memories with their indices.\n"
        "- memory_delete(indices): Deletes one or more global memories by index. Pass a single int or a list of ints (e.g. [0, 2]). Indices are based on memory_list output. Always pass all indices to delete in one call to avoid index shifting.\n\n"
        "IMPORTANT: For long-running or blocking commands (e.g. starting a server, running ngrok, or any process "
        "that does not exit on its own), you MUST use 'shell_async'. "
        "Using 'shell_execute' for these will cause the agent to hang.\n\n"
        "IMPORTANT: When creating files and no destination path is specified by the user, always write to the "
        "system temp directory. The agent's working directory is an internal path with no meaning to the user.\n\n"
        "[HEARTBEAT MESSAGES]\n"
        "If a message starts with [HEARTBEAT: skill_name], it is a scheduled system trigger — not from the user. "
        "Follow the instructions inside the message. "
        "Only set a non-empty \"content\" in the FINAL response if there is something worth reporting to the user. "
        "If nothing to report, set \"content\" to \"\". Do not mention the heartbeat mechanism to the user.\n"
        "If a message starts with [HEARTBEAT_DISCOVER: skill_name], a new skill with a heartbeat was found. "
        "Read the instructions, choose a sensible interval_seconds (minimum 10), update the heartbeat-config.json file. "
        "Set \"content\" to \"\" in every response. Do NOT send any message to the user.\n"
        "[CRON JOBS]\n"
        "If a message starts with [CRON: job_name], it is a scheduled cron trigger — not from the user. "
        "Follow the instructions inside the message. "
        "Only set a non-empty \"content\" in the FINAL response when there is a meaningful conclusion to report — skip intermediate steps. "
        "When you do output content, prefix it with ⏰ so the user knows it is a scheduled task.\n"
        "Cron tools:\n"
        "- cron_create(name, cron, prompt): Create a cron job. 'name' is a short identifier. "
        "'cron' supports two formats: "
        "5-field (minute-level): 'minute hour day month weekday' (e.g. '*/30 * * * *' for every 30 min, '0 9 * * 1-5' for weekdays at 9am); "
        "6-field (second-level): 'second minute hour day month weekday' (e.g. '*/10 * * * * *' for every 10 seconds). "
        "Convert the user's natural language schedule to the appropriate cron expression. "
        "'prompt' is the instruction to execute each time the job fires.\n"
        "- cron_delete(indices): Delete one or more cron jobs by index. Pass a single int or a list of ints (e.g. [0, 2]). Indices are based on cron_list output. Always pass all indices in one call to avoid index shifting.\n"
        "- cron_list(): List all active cron jobs with their indices.\n\n"
        "If a message starts with [WATCHER: skill_name], it is an event notification from a background watcher — not from the user. "
        "If you have not already read the full instructions for that skill during this session, you MUST use file_read() to read the skill's path (found in the SKILLS SECTION) before taking any action. "
        "IMPORTANT: If the notification provides information that should be shown to the user (like an incoming message or alert), you MUST show that information in your FIRST response via the \"content\" field. "
        "Only use a brief acknowledgment if the notification contains no data to display. "
        "On subsequent tool-call iterations, only set \"content\" if there is something new worth reporting."
    )

    DEFAULT_CONFIG = {
        "engine_type": "openai",
        "browser": {
            "enabled": False,
            "data_dir": "~/.mmclaw/browser_data",
        },
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

            # Migration: openai_compatible (old format) → openai_compatible_default
            if "engines" in config and "openai_compatible" in config["engines"]:
                oc = config["engines"]["openai_compatible"]
                if oc.get("api_key"):
                    print("[*] Migrating 'openai_compatible' → 'openai_compatible_default'...")
                    config["engines"]["openai_compatible_default"] = oc
                    if config.get("engine_type") == "openai_compatible":
                        config["engine_type"] = "openai_compatible_default"
                else:
                    print("[*] Removing empty 'openai_compatible' engine...")
                    if config.get("engine_type") == "openai_compatible":
                        config["engine_type"] = "openai"
                del config["engines"]["openai_compatible"]
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
    def get_full_prompt(cls, mode="terminal", config=None):
        """Combine base prompt with skills and interface context.

        Note: sync_skills should be called once at startup, not here,
        to allow for fast frequent refreshes of the prompt index.
        """
        if config is None:
            config = cls.load() or {}

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
        elif mode == "stateless":
            interface_context += (
                "You are running in non-interactive (stateless) mode triggered by a CLI prompt. "
                "IMPORTANT: Do NOT ask the user for clarification or confirmation. Make reasonable assumptions and proceed autonomously to complete the task fully.\n"
                "Formatting Guidelines: Use plain text for console output. This does not restrict file content or task output.\n"
            )
        else:
            interface_context += (
                "Formatting Guidelines: Use plain text for the terminal. Use simple ASCII characters "
                "for lists (e.g., - or *) and tables. Avoid complex markdown that doesn't render in a shell.\n"
            )

        engine_type = config.get("engine_type", "openai")
        active_engine = config.get("engines", {}).get(engine_type, {})
        model_name = active_engine.get("model", "unknown")
        engine_context = (
            f"\n\n[LLM ENGINE]\n"
            f"Provider: {engine_type}\n"
            f"Model: {model_name}\n"
            "Use this to answer if the user asks which model, provider, or engine you are running on.\n"
        )

        browser_enabled = config.get("browser", {}).get("enabled", False)
        browser_context = (
            "\n\n[BROWSER]\n"
            "Status: ENABLED — use the browser tools below for all browser tasks. Do not use the browser skill or shell scripts for browser operations.\n"
            "Browser Tools:\n"
            "- browser_start(): Start the browser. Must be called before any other browser tool.\n"
            "- browser_stop(): Close the browser gracefully.\n"
            "- browser_navigate(url): Navigate to a URL. Returns page title and URL.\n"
            "- browser_click(selector): Click an element by CSS selector. Returns new title and URL.\n"
            "- browser_fill(selector, text): Type text into an input field.\n"
            "- browser_get_text(selector?): Get text from the page. Omit selector for full body text.\n"
            "- browser_screenshot(path?): Take a screenshot. Only call this when the user explicitly asks for a screenshot. Never call it proactively.\n"
            if browser_enabled else
            "\n\n[BROWSER]\n"
            "Status: DISABLED — the browser_start/navigate/click/fill/get_text/screenshot/stop tools are unavailable. Do NOT use the browser skill.\n"
            "IMPORTANT: Browser being disabled does NOT prevent:\n"
            "- Fetching and analyzing URL content: use Python with requests + beautifulsoup4 (bs4) for parsing/analysis; for simple plain-text retrieval curl -sL <url> is also fine\n"
            "- Web search: the web-search skill uses its own search API and does NOT require the browser — use it normally\n"
            "Only refuse browser-specific interactive tasks (login flows, clicking UI elements, screenshots).\n"
        )

        os_context = (
            f"\n\n[SYSTEM ENVIRONMENT]\n"
            f"Operating System: {platform.platform()}\n"
            "IMPORTANT: When generating shell commands, always use syntax compatible with the above OS.\n"
            "IMPORTANT: When running Python scripts, use 'python' — never 'python3' or '/usr/bin/python'.\n"
        )

        workspace_context = (
            f"\n\n[MMCLAW_WORKSPACE]\n"
            f"Your MMClaw workspace directory is: {cls.CONFIG_DIR}\n"
            "Use this path for all file operations, skill scripts, and config files. "
            "Do NOT use ~/.mmclaw or any other hardcoded path.\n"
            "In shell commands, reference it as $MMCLAW_WORKSPACE (Linux/macOS) "
            "or %MMCLAW_WORKSPACE% / $env:MMCLAW_WORKSPACE (Windows cmd/PowerShell).\n"
        )

        # print("================\n" + os_context)

        return cls.BASE_SYSTEM_PROMPT + os_context + workspace_context + engine_context + browser_context + interface_context + SkillManager.get_skills_prompt() + SkillManager.get_skill_kg_prompt()
