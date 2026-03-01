import os
import json
import subprocess
import threading
import time
import asyncio
import telebot
import shutil
import random
import base64
import io
import tempfile
from contextlib import contextmanager
from .config import ConfigManager
from .providers import prepare_image_content

class TerminalConnector(object):
    def __init__(self):
        self._typing = False
        self._input_ready = threading.Event()
        self._input_ready.set()
        self._print_lock = threading.Lock()

    def listen(self, callback):
        print("\n--- MMClaw Kernel Active (Terminal Mode) ---")
        while True:
            try:
                self._input_ready.wait()
                text = input("👤 You: ").strip()
                if text.lower() in ["exit", "quit"]: break
                if text:
                    self._input_ready.clear()
                    callback(text)
            except KeyboardInterrupt: break

    def start_typing(self):
        self._typing = True
        def _animate():
            chars = ["|", "/", "-", "\\"]
            i = 0
            while self._typing:
                with self._print_lock:
                    print(f"\r    ⚡ MMClaw: {chars[i % len(chars)]} thinking...", end="", flush=True)
                i += 1
                time.sleep(0.15)
        threading.Thread(target=_animate, daemon=True).start()

    def stop_typing(self):
        self._typing = False
        time.sleep(0.2)  # Let animation thread finish its current iteration
        with self._print_lock:
            print("\r\033[K", end="", flush=True)
        self._input_ready.set()

    def send(self, message):
        with self._print_lock:
            print(f"\r\033[K    ⚡ MMClaw: {message}", flush=True)

    def send_file(self, path):
        full_path = os.path.expanduser(path)
        with self._print_lock:
            print(f"\r\033[K    ⚡ MMClaw: [FILE SENT] {os.path.abspath(full_path)}", flush=True)

class FeishuConnector(object):
    def __init__(self, app_id, app_secret, config=None):
        try:
            import lark_oapi as lark
        except ImportError:
            raise ImportError("lark-oapi is required for Feishu mode. Install it with: pip install lark-oapi")
            
        self.lark = lark
        self.app_id = app_id
        self.app_secret = app_secret
        self.callback = None
        self.last_message_id = None
        self.config = config if config else ConfigManager.load()
        # Nested connector config
        self.fs_config = self.config.get("connectors", {}).get("feishu", {})
        self.authorized_id = self.fs_config.get("authorized_id")
        
        self.verify_code = str(random.randint(100000, 999999))
        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()
        self.ws_client = None
        self.stop_on_auth = False
    

    def _handle_message(self, data) -> None:
        from lark_oapi.api.im.v1 import GetMessageResourceRequest
        try:
            sender_id = data.event.sender.sender_id.open_id
            msg_type = data.event.message.message_type
            msg_dict = json.loads(data.event.message.content)
            
            # Always store last message_id for reply attempt
            self.last_message_id = data.event.message.message_id


            if not self.authorized_id:
                text = msg_dict.get("text", "").strip()
                if text == self.verify_code:
                    self.authorized_id = sender_id
                    # Save to nested config
                    if "connectors" not in self.config: self.config["connectors"] = {}
                    if "feishu" not in self.config["connectors"]: self.config["connectors"]["feishu"] = {}
                    self.config["connectors"]["feishu"]["authorized_id"] = sender_id
                    
                    ConfigManager.save(self.config)
                    print(f"\n[⭐] AUTH SUCCESS! MMClaw is now locked to Feishu User: {sender_id}")
                    self.send("⚡ Verification Successful! I am now your personal agent.")
                    
                    if self.stop_on_auth:
                        os._exit(0) # Brutal but effective for a CLI wizard setup
                    return
                else:
                    return

            if sender_id != self.authorized_id:
                return
            
            if msg_type == "text":
                text = msg_dict.get("text", "").strip()
                if text and self.callback:
                    print(f"📩 Feishu: {text}")
                    self.callback(text)
            elif msg_type == "image":
                image_key = msg_dict.get("image_key")
                try:
                    request = GetMessageResourceRequest.builder() \
                        .message_id(self.last_message_id) \
                        .file_key(image_key) \
                        .type("image") \
                        .build()
                    response = self.client.im.v1.message_resource.get(request)
                    if not response.success():
                        print(f"[!] Feishu Image Download Error: {response.code}, {response.msg}")
                        return

                    downloaded_file = response.file.read()
                    content = prepare_image_content(downloaded_file, "这张图片里有什么？")
                    print(f"📩 Feishu: [Photo] (Compressed)")
                    if self.callback:
                        self.callback(content)
                except Exception as e:
                    print(f"[!] Feishu Photo Error: {e}")
                    self.send(f"Error processing image: {e}")
            elif msg_type == "file":
                file_key = msg_dict.get("file_key")
                file_name = msg_dict.get("file_name", "file")
                try:
                    request = GetMessageResourceRequest.builder() \
                        .message_id(self.last_message_id) \
                        .file_key(file_key) \
                        .type("file") \
                        .build()
                    response = self.client.im.v1.message_resource.get(request)
                    if not response.success():
                        print(f"[!] Feishu File Download Error: {response.code}, {response.msg}")
                        return

                    file_bytes = response.file.read()
                    tmp_dir = tempfile.mkdtemp(prefix="mmclaw_")
                    file_path = os.path.join(tmp_dir, file_name)
                    with open(file_path, 'wb') as f:
                        f.write(file_bytes)

                    content = f"[Uploaded file: {file_path}]"
                    print(f"📩 Feishu: [File] {file_name}")
                    if self.callback:
                        self.callback(content)
                except Exception as e:
                    print(f"[!] Feishu File Error: {e}")
                    self.send(f"Error processing file: {e}")
        except Exception as e:
            print(f"[!] Feishu Parse Error: {e}")
        return None

    def listen(self, callback, stop_on_auth=False):
        self.callback = callback
        self.stop_on_auth = stop_on_auth
        print(f"\n--- MMClaw Kernel Active (Feishu Mode) ---")
        
        if not self.authorized_id:
            print(f"[🔐] 需要进行飞书身份验证")
            print(f"[*] 请将以下 6 位验证码发送给飞书机器人: {self.verify_code}")
        elif stop_on_auth:
            print(f"\n[✅] 飞书身份已验证: {self.authorized_id}")
            return

        event_handler = self.lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(self._handle_message) \
            .build()

        self.ws_client = self.lark.ws.Client(
            app_id=self.app_id,
            app_secret=self.app_secret,
            event_handler=event_handler,
            log_level=self.lark.LogLevel.INFO
        )
        self.ws_client.start()

    def start_typing(self): pass
    def stop_typing(self): pass

    def send(self, message):
        from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
        if not self.last_message_id:
            return

        limit = 4000
        chunks = [message[i:i+limit] for i in range(0, len(message), limit)]
        for chunk in chunks:
            reply_body = json.dumps({"text": chunk})
            request = ReplyMessageRequest.builder() \
                .message_id(self.last_message_id) \
                .request_body(ReplyMessageRequestBody.builder() \
                    .content(reply_body) \
                    .msg_type("text") \
                    .build()) \
                .build()
            response = self.client.im.v1.message.reply(request)
            if not response.success():
                print(f"[!] Feishu Reply Error: {response.code}, {response.msg}")
                break

    def send_file(self, path):
        from lark_oapi.api.im.v1 import CreateFileRequest, CreateFileRequestBody, ReplyMessageRequest, ReplyMessageRequestBody
        if not self.last_message_id: 
            return
        
        full_path = os.path.expanduser(path)
        if not os.path.exists(full_path):
            self.send(f"❌ File not found: {path}")
            return

        file_name = os.path.basename(full_path)
        
        try:
            # 1. Upload file
            with open(full_path, "rb") as f:
                request = CreateFileRequest.builder() \
                    .request_body(CreateFileRequestBody.builder() \
                        .file_type("stream") \
                        .file_name(file_name) \
                        .file(f) \
                        .build()) \
                    .build()
                response = self.client.im.v1.file.create(request)
                
            if not response.success():
                print(f"[!] Feishu Upload Error: {response.code}, {response.msg}")
                self.send(f"❌ Error uploading file: {response.msg}")
                return
                
            file_key = response.data.file_key
            
            # 2. Send file message (as a reply)
            reply_body = json.dumps({"file_key": file_key})
            request = ReplyMessageRequest.builder() \
                .message_id(self.last_message_id) \
                .request_body(ReplyMessageRequestBody.builder() \
                    .content(reply_body) \
                    .msg_type("file") \
                    .build()) \
                .build()
                
            response = self.client.im.v1.message.reply(request)
            if not response.success():
                print(f"[!] Feishu Send File Error: {response.code}, {response.msg}")
        except Exception as e:
            print(f"[!] Feishu File Process Error: {e}")
            self.send(f"❌ Error processing file: {str(e)}")

class TelegramConnector(object):
    def __init__(self, token, telegram_authorized_user_id):
        self.bot = telebot.TeleBot(token)
        self.telegram_authorized_user_id = int(telegram_authorized_user_id)
        self.chat_id = None
        self._typing = False

    def start_typing(self):
        self._typing = True
        def _type_loop():
            while self._typing:
                try:
                    self.bot.send_chat_action(self.chat_id, 'typing')
                except Exception:
                    pass
                threading.Event().wait(1)
        threading.Thread(target=_type_loop, daemon=True).start()

    def stop_typing(self):
        self._typing = False

    def listen(self, callback):
        print(f"\n--- MMClaw Kernel Active (Telegram Mode) ---")
        print(f"[*] Listening for messages from User ID: {self.telegram_authorized_user_id}")

        @self.bot.message_handler(func=lambda message: message.from_user.id == self.telegram_authorized_user_id,
                                  content_types=['text', 'photo', 'document'])
        def handle_message(message):
            self.chat_id = message.chat.id
            text = message.text or message.caption or ""

            if message.content_type == 'photo':
                try:
                    file_id = message.photo[-1].file_id
                    file_info = self.bot.get_file(file_id)
                    downloaded_file = self.bot.download_file(file_info.file_path)

                    content = prepare_image_content(downloaded_file, text if text else "What is in this image?")
                    print(f"📩 Telegram: [Photo] {text} (Compressed)")
                    callback(content)
                except Exception as e:
                    print(f"[!] Telegram Photo Error: {e}")
                    self.send(f"Error processing image: {e}")
            elif message.content_type == 'document':
                try:
                    doc = message.document
                    file_info = self.bot.get_file(doc.file_id)
                    downloaded_file = self.bot.download_file(file_info.file_path)

                    tmp_dir = tempfile.mkdtemp(prefix="mmclaw_")
                    file_path = os.path.join(tmp_dir, doc.file_name)
                    with open(file_path, 'wb') as f:
                        f.write(downloaded_file)

                    content = f"[Uploaded file: {file_path}]"
                    if text:
                        content += f"\n{text}"
                    print(f"📩 Telegram: [Document] {doc.file_name}{' | ' + text if text else ''}")
                    callback(content)
                except Exception as e:
                    print(f"[!] Telegram Document Error: {e}")
                    self.send(f"Error processing file: {e}")
            else:
                if text:
                    print(f"📩 Telegram: {text}")
                    callback(text)

        @self.bot.message_handler(func=lambda message: message.from_user.id != self.telegram_authorized_user_id,
                                  content_types=['text', 'photo', 'audio', 'video', 'document', 'sticker', 'voice'])
        def unauthorized(message):
            self.bot.reply_to(message, "🚫 Unauthorized. I only respond to my master.")

        self.bot.infinity_polling()

    def send(self, message):
        limit = 4000
        chunks = [message[i:i+limit] for i in range(0, len(message), limit)]
        for chunk in chunks:
            try:
                self.bot.send_message(self.telegram_authorized_user_id, f"⚡ {chunk}")
            except Exception as e:
                print(f"[!] Telegram Send Error: {e}")
                break

    def send_file(self, path):
        path = os.path.expanduser(path)
        try:
            with open(path, 'rb') as f:
                self.bot.send_document(self.telegram_authorized_user_id, f)
        except Exception as e:
            self.send(f"Error sending file: {str(e)}")

class WhatsAppConnector(object):
    def __init__(self, config=None):
        self.process = None
        self.callback = None
        self.active_recipient = None
        self.config = config if config else ConfigManager.load()
        # Nested connector config
        self.wa_config = self.config.get("connectors", {}).get("whatsapp", {})
        self.authorized_id = self.wa_config.get("authorized_id")
        
        self.verify_code = str(random.randint(100000, 999999))
        self.last_sent_text = None
        self.bridge_path = os.path.join(os.path.dirname(__file__), "bridge.js")
        self.is_windows = os.name == 'nt'
        self._deps_checked = False
        self._typing = False
        self._stdin_lock = threading.Lock()
        self._stop_typing_event = threading.Event()
        self._ack_event = threading.Event()
        self._ack_error = None

    def _ensure_node(self):
        if not shutil.which("node"):
            print("[❌] Node.js not found. Please install Node.js to use WhatsApp mode.")
            return False
        return True

    def _get_node_env(self):
        """Prepare environment to find global node_modules."""
        env = os.environ.copy()
        try:
            npm_root = subprocess.check_output(["npm", "root", "-g"], encoding='utf-8', stderr=subprocess.DEVNULL, shell=self.is_windows).strip()
            existing_path = env.get("NODE_PATH", "")
            env["NODE_PATH"] = f"{npm_root}{os.pathsep}{existing_path}" if existing_path else npm_root
        except:
            pass
        return env

    def _ensure_deps(self):
        if self._deps_checked:
            return
        
        deps = ["@whiskeysockets/baileys", "qrcode-terminal", "pino"]
        missing = []

        print("[*] Verifying WhatsApp bridge dependencies...")
        env = self._get_node_env()
        
        for dep in deps:
            # Check if we can require the dependency using node
            # This is much faster than 'npm list'
            check = subprocess.run(
                ["node", "-e", f"require('{dep}')"],
                env=env,
                capture_output=True,
                shell=self.is_windows
            )
            
            if check.returncode != 0:
                missing.append(dep)

        if not missing:
            self._deps_checked = True
            return

        print(f"[!] Missing: {', '.join(missing)}")
        print(f"[*] Installing dependencies: {', '.join(missing)}...")

        try:
            # Attempt global install
            print("[*] Running: npm install -g " + " ".join(missing))
            subprocess.run(["npm", "install", "-g"] + missing, check=True, shell=self.is_windows)
        except subprocess.CalledProcessError:
            print("[!] Global install failed. Attempting local install...")
            print("[*] Running: npm install " + " ".join(missing))
            subprocess.run(["npm", "install"] + missing, check=True, shell=self.is_windows)
        
        self._deps_checked = True

    def listen(self, callback, stop_on_auth=False):
        if not self._ensure_node(): return
        self._ensure_deps()
        self.callback = callback
        self.stop_on_auth = stop_on_auth

        if stop_on_auth and self.authorized_id:
            print(f"\n[✅] WhatsApp identity already verified: {self.authorized_id}")
            return
        
        env = self._get_node_env()
        self.process = subprocess.Popen(
            ["node", self.bridge_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
            env=env, encoding='utf-8', bufsize=1, shell=self.is_windows
        )

        def output_reader():
            for line in iter(self.process.stdout.readline, ""):
                if line.startswith("JSON_EVENT:"):
                    try:
                        event = json.loads(line[11:])
                        if event["type"] == "message":
                            sender = event["from"]
                            text = event["text"].strip()
                            from_me = event.get("fromMe", False)

                            if not self.authorized_id:
                                if text == self.verify_code:
                                    self.authorized_id = sender
                                    # Save to nested config
                                    if "connectors" not in self.config: self.config["connectors"] = {}
                                    if "whatsapp" not in self.config["connectors"]: self.config["connectors"]["whatsapp"] = {}
                                    self.config["connectors"]["whatsapp"]["authorized_id"] = sender
                                    
                                    ConfigManager.save(self.config)
                                    print(f"\n[⭐] AUTH SUCCESS! MMClaw is now locked to: {sender}")

                                    if stop_on_auth:
                                        # Fire-and-forget: bypass ACK wait since we're exiting immediately
                                        try:
                                            payload = {"to": sender, "text": "⚡ Verification Successful! I am now your personal agent."}
                                            self._write_stdin(f"SEND:{json.dumps(payload)}\n")
                                        except Exception:
                                            pass
                                        self.process.terminate()
                                        os._exit(0)
                                    else:
                                        # Dispatch to thread — output_reader must keep running to handle ACKs
                                        threading.Thread(target=self.send, args=("⚡ Verification Successful! I am now your personal agent.",), daemon=True).start()
                                    continue
                                else:
                                    continue

                            if sender != self.authorized_id:
                                continue

                            if from_me and text == self.last_sent_text:
                                continue

                            print(f"📩 WhatsApp: {text}")
                            self.active_recipient = sender
                            if self.callback:
                                threading.Thread(target=self.callback, args=(text,), daemon=True).start()

                        elif event["type"] == "image":
                            sender = event["from"]
                            b64_data = event["base64"]
                            caption = event.get("caption", "").strip()
                            from_me = event.get("fromMe", False)

                            if not self.authorized_id or sender != self.authorized_id:
                                continue

                            # We allow from_me for images because the bot currently only sends 
                            # documents (not imageMessages), so there is no risk of a loop.
                            # This allows users to talk to the bot from the same account.

                            try:
                                # Decode base64 to bytes
                                image_bytes = base64.b64decode(b64_data)
                                content = prepare_image_content(image_bytes, caption if caption else "What is in this image?")
                                print(f"📩 WhatsApp: [Photo] {caption} (Compressed)")
                                self.active_recipient = sender
                                if self.callback:
                                    threading.Thread(target=self.callback, args=(content,), daemon=True).start()
                            except Exception as e:
                                print(f"[!] WhatsApp Image Error: {e}")

                        elif event["type"] == "file":
                            sender = event["from"]
                            b64_data = event["base64"]
                            filename = event.get("filename", "file")
                            caption = event.get("caption", "").strip()
                            from_me = event.get("fromMe", False)

                            if not self.authorized_id or sender != self.authorized_id:
                                continue

                            try:
                                file_bytes = base64.b64decode(b64_data)
                                tmp_dir = tempfile.mkdtemp(prefix="mmclaw_")
                                file_path = os.path.join(tmp_dir, filename)
                                with open(file_path, 'wb') as f:
                                    f.write(file_bytes)

                                content = f"[Uploaded file: {file_path}]"
                                if caption:
                                    content += f"\n{caption}"
                                print(f"📩 WhatsApp: [Document] {filename}{' | ' + caption if caption else ''}")
                                self.active_recipient = sender
                                if self.callback:
                                    threading.Thread(target=self.callback, args=(content,), daemon=True).start()
                            except Exception as e:
                                print(f"[!] WhatsApp Document Error: {e}")

                        elif event["type"] == "connected":
                            if not self.authorized_id:
                                print(f"\n[✅] WhatsApp Bridge Connected!")
                                print(f"[🔐] WHATSAPP VERIFICATION REQUIRED")
                                print(f"[*] PLEASE SEND THIS CODE TO YOURSELF ON WHATSAPP: {self.verify_code}")
                            else:
                                print(f"\n[✅] WhatsApp Active")
                                if stop_on_auth:
                                    self.process.terminate()
                                    return

                        elif event["type"] in ("msg_sent", "file_sent"):
                            self._ack_error = None
                            self._ack_event.set()

                        elif event["type"] in ("msg_error", "file_error"):
                            self._ack_error = event.get("error", "unknown error")
                            self._ack_event.set()

                    except Exception as e:
                        print(f"[!] Bridge Parse Error: {e}")
                else:
                    print(line, end="")

        threading.Thread(target=output_reader, daemon=True).start()
        self.process.wait()

    def _write_stdin(self, data):
        with self._stdin_lock:
            self.process.stdin.write(data)
            self.process.stdin.flush()

    def _send_presence(self, action):
        recipient = self.active_recipient or self.authorized_id
        if not self.process or not recipient: return
        try:
            payload = {"to": recipient, "action": action}
            self._write_stdin(f"TYPING:{json.dumps(payload)}\n")
        except Exception:
            pass

    def start_typing(self):
        self._typing = True
        self._stop_typing_event.clear()
        def _type_loop():
            while self._typing:
                self._send_presence("composing")
                self._stop_typing_event.wait(1)
        threading.Thread(target=_type_loop, daemon=True).start()

    def stop_typing(self):
        self._typing = False
        self._stop_typing_event.set()
        self._send_presence("paused")

    @contextmanager
    def _wa_send(self, timeout=60):
        self._ack_event.clear()
        self._ack_error = None
        yield
        if not self._ack_event.wait(timeout=timeout):
            raise TimeoutError("WhatsApp send timed out")
        if self._ack_error:
            raise RuntimeError(f"WhatsApp send failed: {self._ack_error}")

    def send(self, message):
        if not self.process or not (self.active_recipient or self.authorized_id): return
        recipient = self.active_recipient or self.authorized_id
        limit = 4000
        chunks = [message[i:i+limit] for i in range(0, len(message), limit)]
        for chunk in chunks:
            self.last_sent_text = chunk
            payload = {"to": recipient, "text": chunk}
            try:
                with self._wa_send():
                    self._write_stdin(f"SEND:{json.dumps(payload)}\n")
            except Exception as e:
                print(f"[!] WhatsApp send error: {e}")
                break

    def send_file(self, path):
        if not self.process or not (self.active_recipient or self.authorized_id): return
        recipient = self.active_recipient or self.authorized_id
        full_path = os.path.abspath(os.path.expanduser(path))
        payload = {"to": recipient, "path": full_path}
        try:
            with self._wa_send(timeout=120):
                self._write_stdin(f"SEND_FILE:{json.dumps(payload)}\n")
        except Exception as e:
            print(f"[!] WhatsApp send_file error: {e}")

class QQBotConnector(object):
    def __init__(self, app_id, app_secret, config=None):
        try:
            import botpy
        except ImportError:
            raise ImportError("botpy 未安装，请运行: pip install qq-botpy")

        self.app_id = app_id
        self.app_secret = app_secret
        self.config = config if config else ConfigManager.load()
        self.callback = None
        self._client = None
        self._loop = None
        self._api = None
        self._last_message = None   # ('c2c', message_obj)
        self._msg_seq = {}          # Per-user message sequence counter

    def listen(self, callback):
        import botpy
        self.callback = callback
        connector = self

        class MMClawBot(botpy.Client):
            async def on_ready(self):
                connector._loop = asyncio.get_event_loop()
                connector._api = self.api
                print("\n[✅] QQ Bot is online! Send a direct message to the bot to start.")

            async def on_c2c_message_create(self, message):
                """Triggered when a user sends a direct message to the bot."""
                import urllib.request
                connector._last_message = ("c2c", message)
                text = message.content.strip()

                attachments = getattr(message, "attachments", None)
                if attachments:
                    for att in attachments:
                        if getattr(att, "content_type", "").startswith("image/"):
                            try:
                                with urllib.request.urlopen(att.url, timeout=15) as resp:
                                    image_bytes = resp.read()
                                content = prepare_image_content(image_bytes, text if text else "这张图片里有什么？")
                                print(f"📩 QQ: [Photo] {text} (Compressed)")
                                if connector.callback:
                                    threading.Thread(target=connector.callback, args=(content,), daemon=True).start()
                            except Exception as e:
                                print(f"[!] QQ Bot Photo Error: {e}")
                            return

                if text and connector.callback:
                    print(f"📩 QQ: {text}")
                    threading.Thread(target=connector.callback, args=(text,), daemon=True).start()

        print("\n--- MMClaw Kernel Active (QQ Bot Mode) ---")
        intents = botpy.Intents(public_messages=True)
        connector._client = MMClawBot(intents=intents, bot_log=False)
        connector._client.run(appid=self.app_id, secret=self.app_secret)

    def start_typing(self): pass
    def stop_typing(self): pass

    async def _send_async(self, text):
        if not self._last_message or not self._api:
            return
        _, msg = self._last_message
        openid = msg.author.user_openid
        self._msg_seq[openid] = self._msg_seq.get(openid, 0) + 1
        try:
            await self._api.post_c2c_message(
                openid=openid,
                msg_type=0,
                content=text,
                msg_id=msg.id,
                msg_seq=self._msg_seq[openid]
            )
        except Exception as e:
            print(f"[!] QQ Bot Reply Error: {e}")

    def send(self, message):
        if not self._loop or not self._last_message:
            return
        limit = 4000
        chunks = [message[i:i+limit] for i in range(0, len(message), limit)]
        for chunk in chunks:
            future = asyncio.run_coroutine_threadsafe(self._send_async(chunk), self._loop)
            try:
                future.result(timeout=30)
            except Exception as e:
                print(f"[!] QQ Bot Send Error: {e}")
                break

    def send_file(self, path):
        self.send("❌ QQ Bot 暂不支持发送文件。")
