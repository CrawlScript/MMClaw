import os
import argparse
import urllib.request
import json
from .config import ConfigManager
from .kernel import MMClaw
from .connectors import TelegramConnector, TerminalConnector, WhatsAppConnector, FeishuConnector

def run_setup(existing_config=None):
    
    need_auth = False
    
    print("\n--- 🐈 MMClaw Setup Wizard ---")
    config = existing_config.copy() if existing_config else ConfigManager.DEFAULT_CONFIG.copy()
    
    # Ensure nested dicts exist
    if "engines" not in config:
        config["engines"] = ConfigManager.DEFAULT_CONFIG["engines"].copy()
    if "connectors" not in config:
        config["connectors"] = ConfigManager.DEFAULT_CONFIG["connectors"].copy()

    def ask(prompt, key, default_val, nested_engine=None, nested_connector=None):
        if nested_engine:
            current = config["engines"][nested_engine].get(key, default_val)
        elif nested_connector:
            current = config["connectors"][nested_connector].get(key, default_val)
        else:
            current = config.get(key, default_val)
            
        if existing_config:
            user_input = input(f"{prompt} [{current}]: ").strip()
            return user_input if user_input else current
        else:
            user_input = input(f"{prompt}: ").strip()
            return user_input if user_input else default_val

    # 1. LLM Configuration
    if not existing_config or input("\n[1/3] Configure LLM Engine? (y/N): ").strip().lower() == 'y':
        print("\n[1/3] LLM Engine Setup")
        
        PROVIDERS = [
            {"id": "openai", "name": "OpenAI", "url": "https://api.openai.com/v1", "models": ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini"]},
            {"id": "google", "name": "Google Gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai", "models": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-exp"]},
            {"id": "deepseek", "name": "DeepSeek", "url": "https://api.deepseek.com", "models": ["deepseek-chat", "deepseek-reasoner"]},
            {"id": "openrouter", "name": "OpenRouter", "url": "https://openrouter.ai/api/v1", "models": ["anthropic/claude-3.5-sonnet", "google/gemini-flash-1.5"]},
            {"id": "openai_compatible", "name": "OpenAI-Compatible SDK (Custom URL)", "url": None, "models": []}
        ]

        print("Select Provider:")
        for i, p in enumerate(PROVIDERS, 1):
            print(f"{i}. {p['name']}")
        
        # Handle both legacy int and new string engine_type
        current_engine_id = config.get("engine_type", "openai")
        
        # Try to find the index for display purposes
        current_idx = 1
        if isinstance(current_engine_id, int):
            if 1 <= current_engine_id <= len(PROVIDERS):
                current_idx = current_engine_id
        else:
            for i, p in enumerate(PROVIDERS, 1):
                if p["id"] == current_engine_id:
                    current_idx = i
                    break

        p_choice = input(f"Choice (1-{len(PROVIDERS)}) [Current: {current_idx}]: ").strip()
        
        idx = int(p_choice) - 1 if p_choice.isdigit() and 1 <= int(p_choice) <= len(PROVIDERS) else (current_idx - 1)
        provider = PROVIDERS[idx]
        engine_id = provider["id"]
        config["engine_type"] = engine_id
        
        # Provider-specific config (nested)
        if engine_id not in config["engines"]:
            config["engines"][engine_id] = {}

        if provider["url"]:
            config["engines"][engine_id]["base_url"] = provider["url"]
            print(f"[*] Base URL set to: {config['engines'][engine_id]['base_url']}")
        else:
            config["engines"][engine_id]["base_url"] = ask("Enter Base URL", "base_url", "http://localhost:11434/v1", nested_engine=engine_id)

        config["engines"][engine_id]["api_key"] = ask(f"Enter {provider['name']} API Key", "api_key", "sk-xxx", nested_engine=engine_id)

        # Dynamic Model Fetching
        engine_config = config["engines"][engine_id]
        models = provider["models"]
        if engine_config["api_key"] and engine_config["api_key"] != "sk-xxx":
            print(f"[*] Fetching live models from {provider['name']}...")
            try:
                req = urllib.request.Request(
                    f"{engine_config['base_url']}/models", 
                    headers={"Authorization": f"Bearer {engine_config['api_key']}"}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    fetched = [m["id"] for m in data.get("data", [])]
                    if fetched:
                        # Filter and sort to keep the list clean. 
                        # We prioritize short/standard names for popular providers.
                        if "openai.com" in engine_config["base_url"]:
                            fetched = [m for m in fetched if m.startswith(("gpt-", "o1-"))]
                        
                        # Merge fetched models with our static list, ensuring no duplicates
                        models = list(set(fetched + models))
                        
                        # Sort logic: Featured models first, then alphabetical
                        FEATURED = ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini", "deepseek-chat", "deepseek-reasoner", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-exp"]
                        
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
            current_model = engine_config.get('model', models[0])
            m_choice = input(f"Choice (1-{len(models)+1}) [Current: {current_model}]: ").strip()
            
            if m_choice.isdigit():
                idx_m = int(m_choice)
                if 1 <= idx_m <= len(models):
                    engine_config["model"] = models[idx_m-1]
                elif idx_m == len(models) + 1:
                    engine_config["model"] = input("Enter Model Name manually: ").strip()
            elif not m_choice and existing_config:
                pass # Keep current
            else:
                engine_config["model"] = models[0]
        else:
            engine_config["model"] = ask("Enter Model Name", "model", "llama3", nested_engine=engine_id)

    # 2. Mode Selection
    if not existing_config or input("\n[2/3] Configure Connector (Interaction Mode)? (y/N): ").strip().lower() == 'y':
        print("\n[2/3] Interaction Mode")
        print(f"Current preferred mode: {config.get('connector_type', 'terminal')}")
        print("1. Terminal Mode")
        print("2. Telegram Mode")
        print("3. WhatsApp Mode (Scan QR Code)")
        print("4. Feishu (飞书) Mode")
        
        choice = input("Select mode (1, 2, 3, or 4) [Keep current]: ").strip()

        if choice == "4":
            config["connector_type"] = "feishu"
            print("\n--- 🛠 Feishu (飞书) Setup ---")
            
            print("[*] 第一步：请登录飞书开放平台 (https://open.feishu.cn/app) 并创建一个“企业自建应用”。")
            input("    完成后请按回车键 continue...")
            print("[*] 第二步：在“添加应用能力”中，点击机器人下方的“添加”按钮。")
            input("    完成后请按回车键 continue...")
            
            print("[*] 第三步：获取并输入以下信息：")
            config["connectors"]["feishu"]["app_id"] = ask("App ID", "app_id", "", nested_connector="feishu")
            config["connectors"]["feishu"]["app_secret"] = ask("App Secret", "app_secret", "", nested_connector="feishu")
            
            print("[*] 第四步：左侧菜单栏选择“权限管理”，点击“批量导入/导出权限”，复制并粘贴以下 JSON：")
            print("\n{\n  \"scopes\": {\n    \"tenant\": [\n      \"contact:user.base:readonly\",\n      \"im:chat\",\n      \"im:chat:read\",\n      \"im:chat:update\",\n      \"im:message\",\n      \"im:message.group_at_msg:readonly\",\n      \"im:message.p2p_msg:readonly\",\n      \"im:message:send_as_bot\",\n      \"im:resource\"\n    ],\n    \"user\": []\n  }\n}\n")
            print("    点击“下一步，确认新增权限”，然后点击“申请开通”，最后点击“确认”。")
            input("    完成后请按回车键 continue...")
            print("\n[*] 第五步：在飞书平台左侧菜单选择“事件与回调”。")
            print("    为了能够开启“长连接”，请在另一个终端运行以下命令（已自动填充您的 ID 和 Secret）：")
            print(f"\n    python3 -c \"import lark_oapi as lark; h=lark.EventDispatcherHandler.builder('','').build(); c=lark.ws.Client(app_id='{config['connectors']['feishu']['app_id']}', app_secret='{config['connectors']['feishu']['app_secret']}', event_handler=h); c.start()\"\n")
            print("    运行后，返回网页，左侧菜单栏选择“事件与回调”，在“事件配置-订阅方式”中选择“使用长连接接收事件”，然后点击“保存”。")
            input("    完成后（且已关闭上述临时终端）请按回车键 continue...")
            print("[*] 第六步：在“事件与回调”页面，点击“添加事件”，搜索并添加“接收消息 (im.message.receive_v1)”。")
            input("    完成后请按回车键 continue...")
            print("[*] 第七步：左侧菜单选择“版本管理与发布”，点击“创建版本”，输入相关信息，保存后确认发布。")
            input("    完成后请按回车键 continue...")

            if config["connectors"]["feishu"].get("authorized_id"):
                reset = input(f"\n[*] 身份已绑定 ({config['connectors']['feishu']['authorized_id']})。是否重置并进行新的 6 位验证码验证？ (y/N): ").strip().lower()
                if reset == 'y':
                    config["connectors"]["feishu"]["authorized_id"] = None
                    print("[✓] 身份已重置。")
                    need_auth = True
            else:
                need_auth = True

        elif choice == "2":
            config["connector_type"] = "telegram"
            print("\n--- 🛠 Telegram Setup ---")
            config["connectors"]["telegram"]["token"] = ask("Bot API Token", "token", "", nested_connector="telegram")
            user_id = ask("Your User ID", "authorized_user_id", "0", nested_connector="telegram")
            config["connectors"]["telegram"]["authorized_user_id"] = int(user_id) if str(user_id).isdigit() else 0
        elif choice == "3":
            config["connector_type"] = "whatsapp"
            print("\n--- 🛠 WhatsApp Setup ---")
            wa_auth_dir = os.path.join(os.path.expanduser("~"), ".mmclaw", "wa_auth")
            
            if os.path.exists(wa_auth_dir):
                if input("[*] Found existing WhatsApp session. Use this session? (Y/n): ").strip().lower() == 'n':
                    import shutil
                    shutil.rmtree(wa_auth_dir)
                    config["connectors"]["whatsapp"]["authorized_id"] = None
                    print("[✓] Session and identity cleared.")
                    need_auth = True
            else:
                # If session is gone, we must re-verify identity
                config["connectors"]["whatsapp"]["authorized_id"] = None
                need_auth = True

        elif choice == "1":
            config["connector_type"] = "terminal"

    # 3. Save
    ConfigManager.save(config)
    return config, need_auth

def main():
    import sys
    # Force unbuffered output for nohup/logging
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description="MMClaw: Your autonomous multimodal AI agent.")
    parser.add_argument("command", nargs="?", help="Command to run (run, config)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output (show raw LLM and Tool data)")
    args = parser.parse_args()

    config = ConfigManager.load()
    
    if args.command == "config":
        config, need_auth = run_setup(config)

        if not need_auth:
            return

    # Empty command or 'run' both trigger the agent
    elif args.command not in [None, "run"]:
        parser.print_help()
        return

    if not config:
        config, _ = run_setup()

    config["debug"] = args.debug  # Store debug state in config dict for easy passing

    # Mode Dispatch
    mode = config.get("connector_type")
    connectors_config = config.get("connectors", {})
    
    if mode == "telegram":
        tg_config = connectors_config.get("telegram", {})
        connector = TelegramConnector(tg_config.get("token"), tg_config.get("authorized_user_id", 0))
    elif mode == "whatsapp":
        connector = WhatsAppConnector(config=config)
    elif mode == "feishu":
        fs_config = connectors_config.get("feishu", {})
        connector = FeishuConnector(fs_config.get("app_id"), fs_config.get("app_secret"), config=config)
    else:
        connector = TerminalConnector()

    engine_type = config.get("engine_type", "openai")
    active_engine = config.get("engines", {}).get(engine_type, {})
    api_key = active_engine.get("api_key")

    if not api_key or "your-key-here" in api_key:
        print(f"\n[❌] API Key missing for {engine_type}. Please run 'mmclaw config' or edit {ConfigManager.CONFIG_FILE}")
        return
    
    app = MMClaw(config, connector, system_prompt=ConfigManager.get_full_prompt(mode=mode))

    if args.command == "config":
        app.run(stop_on_auth=True)
    else:
        app.run()

if __name__ == "__main__":
    main()
