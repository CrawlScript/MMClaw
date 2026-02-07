import os
import argparse
import urllib.request
import json
from .config import ConfigManager
from .kernel import PipClaw
from .connectors import TelegramConnector, TerminalConnector, WhatsAppConnector

def run_setup(existing_config=None):
    print("\n--- 🐈 PipClaw Setup Wizard ---")
    config = existing_config.copy() if existing_config else ConfigManager.DEFAULT_CONFIG.copy()

    def ask(prompt, key, default_val):
        current = config.get(key, default_val)
        if existing_config:
            user_input = input(f"{prompt} [{current}]: ").strip()
            return user_input if user_input else current
        else:
            user_input = input(f"{prompt}: ").strip()
            return user_input if user_input else default_val

    # 1. LLM Configuration
    print("\n[1/3] LLM Engine Setup")
    
    PROVIDERS = [
        {"name": "OpenAI", "url": "https://api.openai.com/v1", "models": ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini"]},
        {"name": "DeepSeek", "url": "https://api.deepseek.com", "models": ["deepseek-chat", "deepseek-reasoner"]},
        {"name": "OpenRouter", "url": "https://openrouter.ai/api/v1", "models": ["anthropic/claude-3.5-sonnet", "google/gemini-flash-1.5"]},
        {"name": "OpenAI-Compatible SDK (Custom URL)", "url": None, "models": []}
    ]

    print("Select Provider:")
    for i, p in enumerate(PROVIDERS, 1):
        print(f"{i}. {p['name']}")
    
    current_engine = str(config.get("engine_type", "1"))
    p_choice = input(f"Choice (1-{len(PROVIDERS)}) [Current: {current_engine}]: ").strip()
    
    if not p_choice and existing_config:
        p_choice = current_engine
    
    idx = int(p_choice) - 1 if p_choice.isdigit() and 1 <= int(p_choice) <= len(PROVIDERS) else 0
    provider = PROVIDERS[idx]
    config["engine_type"] = idx + 1
    
    if provider["url"]:
        config["base_url"] = provider["url"]
        print(f"[*] Base URL set to: {config['base_url']}")
    else:
        config["base_url"] = ask("Enter Base URL", "base_url", "http://localhost:11434/v1")

    config["api_key"] = ask(f"Enter {provider['name']} API Key", "api_key", "sk-xxx")

    # Dynamic Model Fetching
    models = provider["models"]
    if config["api_key"] and config["api_key"] != "sk-xxx":
        print(f"[*] Fetching live models from {provider['name']}...")
        try:
            req = urllib.request.Request(
                f"{config['base_url']}/models", 
                headers={"Authorization": f"Bearer {config['api_key']}"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                fetched = [m["id"] for m in data.get("data", [])]
                if fetched:
                    # Filter and sort to keep the list clean. 
                    # We prioritize short/standard names for popular providers.
                    if "openai.com" in config["base_url"]:
                        fetched = [m for m in fetched if m.startswith(("gpt-", "o1-"))]
                    
                    # Merge fetched models with our static list, ensuring no duplicates
                    models = list(set(fetched + models))
                    
                    # Sort logic: Featured models first, then alphabetical
                    FEATURED = ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini", "deepseek-chat", "deepseek-reasoner"]
                    
                    def sort_key(name):
                        try:
                            # If it's a featured model, give it priority (0 to len-1)
                            return (FEATURED.index(name), name)
                        except ValueError:
                            # Others come after featured models
                            return (len(FEATURED), name)
                    
                    models.sort(key=sort_key)
                    print(f"[✓] Successfully fetched {len(fetched)} models.")
        except Exception:
            print("[!] Could not fetch live models, using default list.")

    if models:
        print(f"\nSelect {provider['name']} Model:")
        for i, m in enumerate(models, 1):
            print(f"{i}. {m}")
        
        print(f"{len(models)+1}. Enter Manually")
        m_choice = input(f"Choice (1-{len(models)+1}) [Current: {config.get('model')}]: ").strip()
        
        if m_choice.isdigit():
            idx_m = int(m_choice)
            if 1 <= idx_m <= len(models):
                config["model"] = models[idx_m-1]
            elif idx_m == len(models) + 1:
                config["model"] = input("Enter Model Name manually: ").strip()
        elif not m_choice and existing_config:
            pass # Keep current
        else:
            config["model"] = models[0]
    else:
        config["model"] = ask("Enter Model Name", "model", "llama3")

    # 2. Mode Selection
    print("\n[2/3] Interaction Mode")
    print(f"Current preferred mode: {config.get('preferred_mode', 'terminal')}")
    print("1. Terminal Mode")
    print("2. Telegram Mode")
    print("3. WhatsApp Mode (Scan QR Code)")
    
    choice = input("Select mode (1, 2, or 3) [Keep current]: ").strip()

    if choice == "2":
        config["preferred_mode"] = "telegram"
        print("\n--- 🛠 Telegram Setup ---")
        config["telegram_token"] = ask("Bot API Token", "telegram_token", "")
        user_id = ask("Your User ID", "telegram_authorized_user_id", "0")
        config["telegram_authorized_user_id"] = int(user_id) if str(user_id).isdigit() else 0
    elif choice == "3":
        config["preferred_mode"] = "whatsapp"
        print("\n--- 🛠 WhatsApp Setup ---")
        print("[*] No tokens needed. You will scan a QR code in your terminal on run.")
    elif choice == "1":
        config["preferred_mode"] = "terminal"

    # 3. Save
    ConfigManager.save(config)
    return config

def main():
    import sys
    # Force unbuffered output for nohup/logging
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description="PipClaw: Your autonomous AI agent.")
    parser.add_argument("command", nargs="?", help="Command to run (run, config)")
    args = parser.parse_args()

    config = ConfigManager.load()
    
    if args.command == "config":
        config = run_setup(config)
        return
    
    # Empty command or 'run' both trigger the agent
    if args.command not in [None, "run"]:
        parser.print_help()
        return

    if not config:
        config = run_setup()

    # Mode Dispatch
    mode = config.get("preferred_mode")
    if mode == "telegram":
        connector = TelegramConnector(config["telegram_token"], config["telegram_authorized_user_id"])
    elif mode == "whatsapp":
        connector = WhatsAppConnector()
    else:
        connector = TerminalConnector()

    if config["api_key"] == "sk-your-key-here":
        print(f"\n[❌] API Key missing. Please run 'pipclaw config' or edit {ConfigManager.CONFIG_FILE}")
        return
    
    app = PipClaw(config, connector, system_prompt=ConfigManager.get_full_prompt())
    app.run()

if __name__ == "__main__":
    main()