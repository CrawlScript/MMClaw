import os
import argparse
from pathlib import Path
import urllib.request
import urllib.parse
import json
import base64
import time
from .config import ConfigManager
from .kernel import MMClaw
from .connectors import TelegramConnector, TerminalConnector, WhatsAppConnector, FeishuConnector, QQBotConnector, WeChatConnector, StatelessArgConnector

def run_setup(existing_config=None):
    
    need_auth = False
    
    print("\n--- ⚡ MMClaw Setup Wizard ---")
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

        BUILTIN_PROVIDERS = [
            {"id": "openai", "name": "OpenAI", "url": "https://api.openai.com/v1", "models": ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini"]},
            {"id": "codex", "name": "OpenAI Codex (OAuth)", "url": "https://api.openai.com/v1", "models": ["gpt-5.4", "gpt-5.3-codex", "gpt-5.3-codex-spark", "gpt-5.2-codex", "gpt-5.2", "gpt-5.1-codex-max", "gpt-5.1", "gpt-5.1-codex", "gpt-5-codex", "gpt-5-codex-mini", "gpt-5"]},
            {"id": "google", "name": "Google Gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai", "models": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-exp"]},
            {"id": "deepseek", "name": "DeepSeek", "url": "https://api.deepseek.com", "models": ["deepseek-chat", "deepseek-reasoner"]},
            {"id": "openrouter", "name": "OpenRouter", "url": "https://openrouter.ai/api/v1", "models": ["anthropic/claude-3.5-sonnet", "google/gemini-flash-1.5"]},
            {"id": "kimi", "name": "Kimi (Moonshot AI)", "url": "https://api.moonshot.cn/v1", "models": ["kimi-k2.5"]},
            {"id": "minimax", "name": "MiniMax", "url": None, "urls": [{"label": "Global", "url": "https://api.minimax.io/v1"}, {"label": "China", "url": "https://api.minimaxi.com/v1"}], "models": ["MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5", "MiniMax-M2.5-highspeed", "MiniMax-M2.1", "MiniMax-M2.1-highspeed", "MiniMax-M2"]},
        ]

        while True:
            # Build list dynamically each render
            custom_providers = []
            for key, ecfg in config["engines"].items():
                if key.startswith("openai_compatible_"):
                    alias = key[len("openai_compatible_"):]
                    custom_providers.append({"id": key, "name": f"[Custom] {alias}", "url": ecfg.get("base_url", ""), "models": []})

            PROVIDERS = BUILTIN_PROVIDERS + custom_providers + [
                {"id": "__add_new__", "name": "[Add New OpenAI-Compatible Provider]", "url": None, "models": []}
            ]

            print("Select Provider:")
            for i, p in enumerate(PROVIDERS, 1):
                if p["id"].startswith("openai_compatible_"):
                    print(f"{i}. {p['name']} ({p['url']})")
                else:
                    print(f"{i}. {p['name']}")

            current_engine_id = config.get("engine_type", "openai")
            current_idx = 1
            for i, p in enumerate(PROVIDERS, 1):
                if p["id"] == current_engine_id:
                    current_idx = i
                    break

            p_choice = input(f"Choice (1-{len(PROVIDERS)}) [Current: {current_idx}]: ").strip()
            idx = int(p_choice) - 1 if p_choice.isdigit() and 1 <= int(p_choice) <= len(PROVIDERS) else (current_idx - 1)
            provider = PROVIDERS[idx]
            engine_id = provider["id"]

            if engine_id == "__add_new__":
                alias = input("Enter provider ID  →  openai_compatible_: ").strip()
                if not alias:
                    print("[!] Alias cannot be empty.")
                    continue
                engine_id = f"openai_compatible_{alias}"
                if engine_id not in config["engines"]:
                    config["engines"][engine_id] = {}
                config["engine_type"] = engine_id
                provider = {"id": engine_id, "name": alias, "url": None, "models": []}
            elif engine_id.startswith("openai_compatible_"):
                alias = engine_id[len("openai_compatible_"):]
                print(f"\n[Custom: {alias} — {provider['url']}]")
                print("1. Use / Reconfigure")
                print("2. Delete")
                sub = input("Choice [1]: ").strip()
                if sub == "2":
                    del config["engines"][engine_id]
                    if config.get("engine_type") == engine_id:
                        config["engine_type"] = "openai"
                        print("[*] Active engine reset to 'openai'.")
                    print(f"[✓] Provider '{alias}' deleted.")
                    continue
                config["engine_type"] = engine_id
                provider = {"id": engine_id, "name": alias, "url": None, "models": []}
            else:
                config["engine_type"] = engine_id

            if engine_id not in config["engines"]:
                config["engines"][engine_id] = {}

            if provider.get("urls"):
                print(f"\nSelect {provider['name']} Region:")
                for i, u in enumerate(provider["urls"], 1):
                    print(f"{i}. {u['label']} ({u['url']})")
                current_url = config["engines"][engine_id].get("base_url", "")
                current_r = 1
                for i, u in enumerate(provider["urls"], 1):
                    if u["url"] == current_url:
                        current_r = i
                        break
                r = input(f"Choice (1-{len(provider['urls'])}) [Current: {current_r}]: ").strip()
                idx_r = (int(r) - 1) if r.isdigit() and 1 <= int(r) <= len(provider["urls"]) else (current_r - 1)
                provider = {**provider, "url": provider["urls"][idx_r]["url"]}

            if engine_id == "codex":
                CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
                BASE_URL  = "https://auth.openai.com/api/accounts"
                UA_HEADER = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

                do_oauth = True
                if config["engines"].get("codex", {}).get("api_key"):
                    if input("Existing Codex session found. Reuse it? (Y/n): ").strip().lower() != 'n':
                        do_oauth = False
                        print("[✓] Reusing existing session.")

                if do_oauth:
                    print(f"[*] Requesting device code...")
                    try:
                        data = json.dumps({"client_id": CLIENT_ID}).encode()
                        req = urllib.request.Request(f"{BASE_URL}/deviceauth/usercode", data=data, headers={**UA_HEADER, "Content-Type": "application/json"}, method="POST")
                        with urllib.request.urlopen(req) as resp:
                            res_data = json.loads(resp.read().decode())
                    except Exception as e:
                        print(f"[❌] Device code request failed: {e}")
                        return config, False

                    device_auth_id = res_data["device_auth_id"]
                    user_code      = res_data["user_code"]
                    interval       = int(res_data.get("interval", 5))

                    print("\n--- 🔐 OpenAI Codex (Device Code) Remote Setup ---")
                    print("[*] Finish signing in via your browser")
                    print("[*] 1. Open this link in your browser and sign in:")
                    print(f"\n    https://auth.openai.com/codex/device\n")
                    print("[*] 2. Enter this one-time code after you are signed in:")
                    print(f"\n    {user_code}\n")
                    print("    ⚠️  Device codes are a common phishing target. Never share this code.")
                    print("    (Press Ctrl+C to cancel)\n")

                    print("[*] Waiting for authorization...")
                    while True:
                        time.sleep(interval)
                        try:
                            data = json.dumps({"device_auth_id": device_auth_id, "user_code": user_code}).encode()
                            req = urllib.request.Request(f"{BASE_URL}/deviceauth/token", data=data, headers={**UA_HEADER, "Content-Type": "application/json"}, method="POST")

                            try:
                                with urllib.request.urlopen(req) as resp:
                                    login_data = json.loads(resp.read().decode())
                            except urllib.error.HTTPError as e:
                                if e.code in [403, 404]: continue
                                raise

                            print("\n[*] Authorization received! Exchanging for access token...")
                            exchange_data = urllib.parse.urlencode({
                                "grant_type":    "authorization_code",
                                "client_id":     CLIENT_ID,
                                "code":          login_data["authorization_code"],
                                "code_verifier": login_data["code_verifier"],
                                "redirect_uri":  "https://auth.openai.com/deviceauth/callback",
                            }).encode()

                            req = urllib.request.Request("https://auth.openai.com/oauth/token", data=exchange_data, headers={**UA_HEADER, "Content-Type": "application/x-www-form-urlencoded"}, method="POST")
                            with urllib.request.urlopen(req) as resp:
                                token_data = json.loads(resp.read().decode())

                            config["engines"][engine_id]["api_key"] = token_data["access_token"]
                            if "refresh_token" in token_data:
                                config["engines"][engine_id]["refresh_token"] = token_data["refresh_token"]

                            if "id_token" in token_data:
                                try:
                                    payload_b64 = token_data["id_token"].split('.')[1]
                                    payload_b64 += '=' * (-len(payload_b64) % 4)
                                    payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode())
                                    account_id = payload.get("https://api.openai.com/auth", {}).get("chatgpt_account_id")
                                    if account_id:
                                        config["engines"][engine_id]["account_id"] = account_id
                                        print(f"[*] Account ID linked: {account_id}")
                                except: pass

                            print("\n[✓] OAuth Login Successful!")
                            break
                        except KeyboardInterrupt: return config, False
                        except Exception as e:
                            print(f"\n[❌] Setup failed: {e}")
                            return config, False

                config["engines"][engine_id]["base_url"] = provider["url"]
            else:
                if provider["url"]:
                    config["engines"][engine_id]["base_url"] = provider["url"]
                    print(f"[*] Base URL set to: {config['engines'][engine_id]['base_url']}")
                else:
                    config["engines"][engine_id]["base_url"] = ask("Enter Base URL", "base_url", "http://localhost:11434/v1", nested_engine=engine_id)

                config["engines"][engine_id]["api_key"] = ask(f"Enter {provider['name']} API Key", "api_key", None, nested_engine=engine_id)

            # Dynamic Model Fetching
            engine_config = config["engines"][engine_id]
            models = provider["models"]
            if engine_id != "codex" and engine_config.get("api_key"):
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
                            if "openai.com" in engine_config["base_url"]:
                                fetched = [m for m in fetched if m.startswith(("gpt-", "o1-"))]

                            models = list(set(fetched + models))
                            FEATURED = ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini", "deepseek-chat", "deepseek-reasoner", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-exp", "kimi-k2.5"]
                            def sort_key(name):
                                try: return (FEATURED.index(name), name)
                                except ValueError: return (len(FEATURED), name)
                            models.sort(key=sort_key)
                            print(f"[✓] Successfully fetched {len(fetched)} models.")
                except:
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
                    if 1 <= idx_m <= len(models): engine_config["model"] = models[idx_m-1]
                    elif idx_m == len(models) + 1: engine_config["model"] = input("Enter Model Name manually: ").strip()
                elif not m_choice and existing_config: pass
                else: engine_config["model"] = models[0]
            else:
                engine_config["model"] = ask("Enter Model Name", "model", "llama3", nested_engine=engine_id)

            # Request Mode
            print("\nRequest Mode:")
            print("1. Streaming (default)")
            print("2. Blocking (non-streaming)")
            current_stream = config.get("stream", True)
            mode_choice = input(f"Choice (1 or 2) [Current: {'1' if current_stream else '2'}]: ").strip()
            if mode_choice == "2":
                config["stream"] = False
            elif mode_choice == "1":
                config["stream"] = True
            # else: keep current value

            break  # Exit provider selection loop

    # 2. Mode Selection
    if not existing_config or input("\n[2/3] Configure Connector (Interaction Mode)? (y/N): ").strip().lower() == 'y':
        print("\n[2/3] Interaction Mode")
        print(f"Current preferred mode: {config.get('connector_type', 'terminal')}")
        print("1. Terminal Mode")
        print("2. Telegram Mode")
        print("3. WhatsApp Mode (Scan QR Code)")
        print("4. WeChat (微信) Mode (Scan QR Code)")
        print("5. Feishu (飞书) Mode")
        print("6. QQ Bot (QQ机器人) Mode")
        choice = input("Select mode (1-6) [Keep current]: ").strip()

        if choice == "5":
            config["connector_type"] = "feishu"
            print("\n--- 🛠 Feishu (飞书) Setup ---")

            print('[*] 第一步：请登录飞书开放平台 (https://open.feishu.cn/app) 并创建一个"企业自建应用"。')
            input("    完成后请按回车键 continue...")
            print('[*] 第二步：在"添加应用能力"中，点击机器人下方的"添加"按钮。')
            input("    完成后请按回车键 continue...")

            print("[*] 第三步：在\"凭证与基础信息\"页面，获取并输入以下信息：")
            config["connectors"]["feishu"]["app_id"] = ask("App ID", "app_id", None, nested_connector="feishu")
            config["connectors"]["feishu"]["app_secret"] = ask("App Secret", "app_secret", None, nested_connector="feishu")

            print('[*] 第四步：左侧菜单栏选择"权限管理"，点击"批量导入/导出权限"，复制并粘贴以下 JSON：')
            print("\n{\n  \"scopes\": {\n    \"tenant\": [\n      \"contact:user.base:readonly\",\n      \"im:chat\",\n      \"im:chat:read\",\n      \"im:chat:update\",\n      \"im:message\",\n      \"im:message.group_at_msg:readonly\",\n      \"im:message.p2p_msg:readonly\",\n      \"im:message:send_as_bot\",\n      \"im:resource\"\n    ],\n    \"user\": []\n  }\n}\n")
            print('    点击"下一步，确认新增权限"，然后点击"申请开通"，最后点击"确认"。')
            input("    完成后请按回车键 continue...")
            print('\n[*] 第五步：在飞书平台左侧菜单选择"事件与回调"。')
            print('    为了能够开启"长连接"，请在另一个终端运行以下命令（已自动填充您的 ID 和 Secret）：')
            print(f"\n    python -c \"import lark_oapi as lark; h=lark.EventDispatcherHandler.builder('','').build(); c=lark.ws.Client(app_id='{config['connectors']['feishu']['app_id']}', app_secret='{config['connectors']['feishu']['app_secret']}', event_handler=h); c.start()\"\n")
            print('    运行后，返回网页，左侧菜单栏选择"事件与回调"，在"事件配置-订阅方式"中选择"使用长连接接收事件"，然后点击"保存"。')
            input("    完成后（且已关闭上述临时终端）请按回车键 continue...")
            print('[*] 第六步：在"事件与回调"页面，点击"添加事件"，搜索并添加"接收消息 (im.message.receive_v1)"。')
            input("    完成后请按回车键 continue...")
            print('[*] 第七步：左侧菜单选择"版本管理与发布"，点击"创建版本"，输入相关信息，保存后确认发布。')
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

            print("[*] Step 1: Create your bot via BotFather.")
            print("    - Open Telegram and search for @BotFather (official, blue checkmark).")
            print("    - Send /newbot and follow the prompts to choose a name and username.")
            print("    - BotFather will give you an API token like:  123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
            config["connectors"]["telegram"]["token"] = ask("    Enter Bot API Token", "token", None, nested_connector="telegram")

            print("\n[*] Step 2: Find your numeric User ID.")
            print("    - Search for @userinfobot on Telegram and send it any message.")
            print("    - It will reply with your ID, e.g.:  Id: 123456789")
            print("    - This is used to restrict the bot so only you can send it commands.")
            user_id = ask("    Enter your User ID", "authorized_user_id", "0", nested_connector="telegram")
            config["connectors"]["telegram"]["authorized_user_id"] = int(user_id) if str(user_id).isdigit() else 0

            print("\n[✓] Telegram configured. Start the agent and send your bot a message to begin.")
        elif choice == "3":
            config["connector_type"] = "whatsapp"
            print("\n--- 🛠 WhatsApp Setup ---")
            wa_auth_dir = str(ConfigManager.CONFIG_DIR / "wa_auth")

            if os.path.exists(wa_auth_dir):
                if input("[*] Found existing WhatsApp session. Use this session? (Y/n): ").strip().lower() == 'n':
                    import shutil
                    shutil.rmtree(wa_auth_dir)
                    config["connectors"]["whatsapp"]["authorized_id"] = None
                    print("[✓] Session and identity cleared.")
                    need_auth = True
            else:
                config["connectors"]["whatsapp"]["authorized_id"] = None
                need_auth = True
        elif choice == "6":
            config["connector_type"] = "qqbot"
            print("\n--- 🛠 QQ Bot (QQ机器人) 配置 ---")
            if "qqbot" not in config["connectors"]:
                config["connectors"]["qqbot"] = {}

            print("[*] 第一步：打开 QQ 开放平台 (https://q.qq.com)，注册账号并绑定你的 QQ 号。")
            input("    完成后请按回车键 continue...")
            print("[*] 第二步：在控制台点击\"创建应用\"，选择\"机器人\"类型并完成创建。")
            input("    完成后请按回车键 continue...")
            print("[*] 第三步：进入应用详情，在\"开发管理\"页面复制 AppID 并输入：")
            config["connectors"]["qqbot"]["app_id"] = ask("    输入 AppID", "app_id", None, nested_connector="qqbot")
            print("[*] 第四步：在同一\"开发管理\"页面，点击\"生成机器人密钥\"并输入：")
            config["connectors"]["qqbot"]["app_secret"] = ask("    输入 AppSecret (机器人密钥)", "app_secret", None, nested_connector="qqbot")
            print("[*] 第五步：在\"开发管理\"页面的\"IP白名单\"中，添加运行 MMClaw 的机器 IP 地址。")
            input("    完成后请按回车键 continue...")
            print("[*] 第六步：进入\"沙箱配置\"页面，在\"消息列表配置\"中点击\"添加成员\"，将自己的 QQ 号加入。")
            input("    完成后请按回车键 continue...")
            print("[*] 第七步：进入\"使用范围和人员\"页面，扫码\"添加到 群和消息列表\"，即可将机器人添加到你的消息列表。")
            input("    完成后请按回车键 continue...")
            print("[✓] 配置完成。无需\"发布上架\"，沙箱模式即可使用。")
            print("    启动后，直接私聊机器人即可交互。")
        elif choice == "4":
            config["connector_type"] = "wechat"
            print("\n--- 🛠 WeChat (微信) Setup ---")
            if "wechat" not in config["connectors"]:
                config["connectors"]["wechat"] = {}

            if config["connectors"]["wechat"].get("token"):
                bound = config["connectors"]["wechat"].get("authorized_id", "")
                hint = f" (bound user: {bound})" if bound else ""
                reset = input(f"\n[*] An existing WeChat session was found{hint}. Reset and re-scan QR code? (y/N): ").strip().lower()
                if reset == 'y':
                    config["connectors"]["wechat"]["token"] = None
                    config["connectors"]["wechat"]["authorized_id"] = None
                    config["connectors"]["wechat"]["get_updates_buf"] = ""
                    print("[✓] WeChat session cleared.")
                need_auth = True
            else:
                need_auth = True

            print("[✓] WeChat (微信) configured. A QR code will appear on next startup — scan it with WeChat to log in.")
        elif choice == "1":
            config["connector_type"] = "terminal"

    # 3. Browser Configuration
    if not existing_config or input("\n[3/3] Configure Browser? (y/N): ").strip().lower() == 'y':
        print("\n[3/3] Browser Configuration")
        import subprocess, sys as _sys
        current_enabled = config.get("browser", {}).get("enabled", False)
        enable = input(f"Enable browser automation (Playwright)? (y/N) [Current: {'enabled' if current_enabled else 'disabled'}]: ").strip().lower()
        if "browser" not in config:
            config["browser"] = {}
        if enable == 'y':
            # Step 1: playwright package
            print("[*] Checking playwright package...")
            r = subprocess.run([_sys.executable, "-c", "import playwright; print('OK')"], capture_output=True, timeout=10)
            pw_ok = r.returncode == 0 and b"OK" in r.stdout
            if pw_ok:
                print("[✓] playwright package found.")
            else:
                print("[❌] playwright not installed.")
                print('     Command:  pip install "playwright==1.58.0"')
                if input("     Install now? (Y/n): ").strip().lower() != 'n':
                    print("[*] Installing...")
                    subprocess.run([_sys.executable, "-m", "pip", "install", "playwright==1.58.0"], timeout=120)
                    r = subprocess.run([_sys.executable, "-c", "import playwright; print('OK')"], capture_output=True, timeout=10)
                    pw_ok = r.returncode == 0 and b"OK" in r.stdout
                    print("[✓] playwright installed." if pw_ok else "[❌] Installation failed.")

            # Step 2: Chromium binaries (only if playwright is available)
            chromium_ok = False
            if pw_ok:
                print("[*] Checking Chromium binaries...")
                r2 = subprocess.run([_sys.executable, "-c",
                    "from playwright.sync_api import sync_playwright\n"
                    "with sync_playwright() as pw: pw.chromium.launch(headless=True).close()\n"
                    "print('OK')"], capture_output=True, timeout=30)
                chromium_ok = r2.returncode == 0 and b"OK" in r2.stdout
                if chromium_ok:
                    print("[✓] Chromium ready.")
                else:
                    print("[❌] Chromium binaries not found.")
                    print("     Command:  playwright install chromium")
                    if input("     Install now? (Y/n): ").strip().lower() != 'n':
                        print("[*] Installing Chromium (this may take a while)...")
                        r_inst = subprocess.run([_sys.executable, "-m", "playwright", "install", "chromium"], timeout=300)
                        chromium_ok = r_inst.returncode == 0
                        print("[✓] Chromium ready." if chromium_ok else "[❌] Installation failed.")

            if pw_ok and chromium_ok:
                config["browser"]["enabled"] = True
                print("[✓] Browser enabled.")
            else:
                config["browser"]["enabled"] = False
                print("[!]  Browser will remain disabled. Run 'mmclaw config' again after installing.")

        if config["browser"].get("enabled"):
            data_dir = os.path.expanduser(config["browser"].get("data_dir", "~/.mmclaw/browser_data"))
            print(f"[*] Browser data directory: {data_dir}/chromium/")
            chromium_dir = os.path.join(data_dir, "chromium")
            if os.path.exists(chromium_dir):
                if input("    Reset browser data (clears cookies and login sessions)? (y/N): ").strip().lower() == 'y':
                    import shutil
                    shutil.rmtree(chromium_dir)
                    print("[✓] Browser data cleared.")
            else:
                print("    (No existing browser data found.)")
        else:
            config["browser"]["enabled"] = False
            print("[✓] Browser disabled.")

    ConfigManager.save(config)
    return config, need_auth

def main():
    import sys

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description="MMClaw: Your autonomous multimodal AI agent.")
    parser.add_argument("command", nargs="?", help="Command to run (run, config, skill)")
    parser.add_argument("subcommand", nargs="?", help="Subcommand (e.g. install)")
    parser.add_argument("skill_path", nargs="?", help="Path to skill directory")
    parser.add_argument("-w", "--workspace", help="Workspace directory (default: ~/.mmclaw)")
    parser.add_argument("-p", "--prompt", help="Run a single prompt without history and exit (stateless arg mode)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--force", action="store_true", help="Force install, skip confirmation prompts")
    args = parser.parse_args()

    from .config import set_workspace
    if args.workspace:
        ws_path = Path(args.workspace).expanduser().resolve()
        print(f"[*] Workspace: {ws_path}")
    else:
        ws_path = Path.home() / ".mmclaw"
        print(f"[*] Workspace: default (~/.mmclaw)  |  use -w <path> to specify a different workspace")
    set_workspace(ws_path)
    os.environ["MMCLAW_WORKSPACE"] = str(ws_path)

    from .config import SkillManager
    if args.command in [None, "run", "config"]:
        SkillManager.sync_skills()

    config = ConfigManager.load()
    if args.command == "config":
        config, need_auth = run_setup(config)
        if not need_auth: return
    elif args.command == "skill":
        if args.subcommand == "install":
            if not args.skill_path:
                print("[❌] Usage: mmclaw skill install <path-to-skill-dir-or-url>")
                return
            import shutil, tempfile, zipfile, re
            skill_path = args.skill_path

            def strip_version(name):
                return re.sub(r'[-_](\d+\.)*\d+$', '', name) or name

            def confirm_replace(dest, skill_name):
                if dest.exists():
                    if args.force:
                        shutil.rmtree(dest)
                    else:
                        print(f"[❌] Skill '{skill_name}' already exists. Use --force to replace it.")
                        return False
                return True

            if skill_path.startswith("http://") or skill_path.startswith("https://"):
                print(f"[*] Downloading {skill_path} ...")
                try:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        tmp_zip, headers = urllib.request.urlretrieve(skill_path)
                        cd = headers.get("content-disposition", "")
                        zip_name = next((p.split("=",1)[1].strip().strip('"\'') for p in cd.split(";") if p.strip().lower().startswith("filename=")), "skill.zip")
                        skill_name = strip_version(Path(zip_name).stem)
                        extract_dir = os.path.join(tmpdir, "extracted")
                        os.makedirs(extract_dir)
                        with zipfile.ZipFile(tmp_zip, "r") as zf:
                            zf.extractall(extract_dir)
                        subdirs = [Path(extract_dir) / d for d in os.listdir(extract_dir) if (Path(extract_dir) / d).is_dir() and d != "__MACOSX"]
                        src = subdirs[0] if subdirs else Path(extract_dir)
                        dest = SkillManager.HOME_SKILLS_DIR / skill_name
                        if not confirm_replace(dest, skill_name): return
                        shutil.copytree(src, dest, dirs_exist_ok=True)
                        print(f"[✓] Skill '{skill_name}' installed to {dest}")
                except Exception as e:
                    print(f"[❌] Download/install failed: {e}")
                    return
            else:
                src = Path(skill_path).resolve()
                if not src.is_dir():
                    print(f"[❌] Not a directory: {src}")
                    return
                skill_name = strip_version(src.name)
                dest = SkillManager.HOME_SKILLS_DIR / skill_name
                if not confirm_replace(dest, skill_name): return
                shutil.copytree(src, dest, dirs_exist_ok=True)
                print(f"[✓] Skill '{skill_name}' installed to {dest}")
        elif args.subcommand == "list":
            if not SkillManager.HOME_SKILLS_DIR.exists():
                print("(no skills installed)")
            else:
                skills = sorted(d.name for d in SkillManager.HOME_SKILLS_DIR.iterdir() if d.is_dir())
                if not skills:
                    print("(no skills installed)")
                else:
                    for s in skills:
                        print(s)
        elif args.subcommand == "uninstall":
            if not args.skill_path:
                print("[❌] Usage: mmclaw skill uninstall <skill-name>")
                return
            import shutil
            target = SkillManager.HOME_SKILLS_DIR / args.skill_path
            if not target.exists():
                print(f"[❌] Skill '{args.skill_path}' not found in {SkillManager.HOME_SKILLS_DIR}")
                return
            shutil.rmtree(target)
            print(f"[✓] Skill '{args.skill_path}' uninstalled.")
        else:
            print(f"[❌] Unknown skill subcommand: {args.subcommand!r}")
            print("     Usage: mmclaw skill list")
            print("            mmclaw skill install <path-to-skill-dir-or-url>")
            print("            mmclaw skill uninstall <skill-name>")
        return
    elif args.command not in [None, "run"]:
        parser.print_help()
        return

    if not config: config, _ = run_setup()
    config["debug"] = args.debug

    use_stateless = bool(args.prompt)

    if use_stateless:
        connector = StatelessArgConnector(args.prompt)
        mode = "stateless"
    else:
        mode = config.get("connector_type")
        connectors_config = config.get("connectors", {})
        if mode == "telegram":
            tg = connectors_config.get("telegram", {})
            connector = TelegramConnector(tg.get("token"), tg.get("authorized_user_id", 0))
        elif mode == "whatsapp": connector = WhatsAppConnector(config=config)
        elif mode == "feishu":
            fs = connectors_config.get("feishu", {})
            connector = FeishuConnector(fs.get("app_id"), fs.get("app_secret"), config=config)
        elif mode == "qqbot":
            qq = connectors_config.get("qqbot", {})
            connector = QQBotConnector(qq.get("app_id"), qq.get("app_secret"), config=config)
        elif mode == "wechat":
            connector = WeChatConnector(config=config)
        else: connector = TerminalConnector()

    engine_type = config.get("engine_type", "openai")
    active_engine = config.get("engines", {}).get(engine_type, {})
    if not active_engine.get("api_key"):
        print(f"\n[❌] API Key missing for {engine_type}. Run 'mmclaw config'.")
        return

    ConfigManager.mode = mode
    app = MMClaw(config, connector, system_prompt=ConfigManager.get_full_prompt(config=config), use_stateless_arg_connector=use_stateless)
    app.run(stop_on_auth=(args.command == "config"))

if __name__ == "__main__":
    main()
