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


class StatelessArgConnector(object):
    """Delivers a single CLI prompt (-p), runs the full agent loop without history, then exits."""
    def __init__(self, prompt):
        self._prompt = prompt
        self._done = threading.Event()
        self.file_saver = None

    def listen(self, callback, stop_on_auth=False):
        callback(self._prompt)
        self._done.wait(timeout=600)

    def start_typing(self): pass

    def stop_typing(self):
        self._done.set()

    def send(self, message):
        print(message, flush=True)

    def send_file(self, path):
        full_path = os.path.abspath(os.path.expanduser(path))
        print(f"[FILE] {full_path}", flush=True)


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
                    file_path = self.file_saver(file_name, file_bytes)

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

    def start_typing(self):
        self.send("⏳")

    def stop_typing(self):
        self.send("✅")

    def send(self, message):
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
        if not self.authorized_id:
            return

        limit = 4000
        chunks = [message[i:i+limit] for i in range(0, len(message), limit)]
        for chunk in chunks:
            content = json.dumps({"text": f"⚡ {chunk}"})
            request = CreateMessageRequest.builder() \
                .receive_id_type("open_id") \
                .request_body(CreateMessageRequestBody.builder() \
                    .receive_id(self.authorized_id) \
                    .content(content) \
                    .msg_type("text") \
                    .build()) \
                .build()
            response = self.client.im.v1.message.create(request)
            if not response.success():
                print(f"[!] Feishu Send Error: {response.code}, {response.msg}")
                break

    def send_file(self, path):
        from lark_oapi.api.im.v1 import CreateFileRequest, CreateFileRequestBody, CreateMessageRequest, CreateMessageRequestBody
        if not self.authorized_id: 
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
            
            # 2. Send file message (direct message)
            content = json.dumps({"file_key": file_key})
            request = CreateMessageRequest.builder() \
                .receive_id_type("open_id") \
                .request_body(CreateMessageRequestBody.builder() \
                    .receive_id(self.authorized_id) \
                    .content(content) \
                    .msg_type("file") \
                    .build()) \
                .build()
                
            response = self.client.im.v1.message.create(request)
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

                    file_path = self.file_saver(doc.file_name, downloaded_file)

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

        try:
            self.bot.set_my_commands([
                telebot.types.BotCommand("/new",  "Start a new session"),
                telebot.types.BotCommand("/stop", "Cancel the current job"),
            ])
        except Exception as e:
            print(f"[!] Telegram: failed to register commands: {e}")

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
                                file_path = self.file_saver(filename, file_bytes)

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
            payload = {"to": recipient, "text": f"⚡ {chunk}"}
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

class WeChatConnector(object):
    """WeChat (Weixin iLink Bot) connector via QR login + long-poll getUpdates."""

    DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
    CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
    BOT_TYPE = "3"
    LONG_POLL_TIMEOUT_S = 38   # slightly longer than server's 35 s hold
    MAX_CONSECUTIVE_FAILURES = 3
    CHANNEL_VERSION = "1.0.3"
    # UploadMediaType
    _MEDIA_IMAGE = 1
    _MEDIA_VIDEO = 2
    _MEDIA_FILE  = 3
    # MessageItemType
    _ITEM_TEXT  = 1
    _ITEM_IMAGE = 2
    _ITEM_FILE  = 4
    _ITEM_VIDEO = 5

    def __init__(self, config=None):
        self.config = config if config else ConfigManager.load()
        self.wc_config = self.config.get("connectors", {}).get("wechat", {})
        self.token = self.wc_config.get("token")
        self.base_url = self.wc_config.get("base_url", self.DEFAULT_BASE_URL).rstrip("/")
        self.authorized_id = self.wc_config.get("authorized_id")
        self._get_updates_buf = self.wc_config.get("get_updates_buf", "")
        self.callback = None
        self._typing = False
        self._stop_event = threading.Event()
        self._context_tokens = {}   # from_user_id -> context_token (in-memory)
        self.file_saver = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _random_wechat_uin(self):
        import struct
        uint32 = struct.unpack(">I", os.urandom(4))[0]
        return base64.b64encode(str(uint32).encode()).decode()

    def _build_headers(self):
        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "X-WECHAT-UIN": self._random_wechat_uin(),
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _api_post(self, endpoint, body_dict, timeout=15):
        import requests
        url = f"{self.base_url}/{endpoint}"
        resp = requests.post(url, json=body_dict, headers=self._build_headers(), timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def _save_wc_config(self):
        if "connectors" not in self.config:
            self.config["connectors"] = {}
        if "wechat" not in self.config["connectors"]:
            self.config["connectors"]["wechat"] = {}
        self.config["connectors"]["wechat"].update(self.wc_config)
        ConfigManager.save(self.config)

    # ------------------------------------------------------------------
    # QR login
    # ------------------------------------------------------------------

    def _login_qr(self):
        """Interactive QR login. Blocks until confirmed, expired limit, or timeout."""
        import requests as req
        base = self.base_url
        qr_url_endpoint = f"{base}/ilink/bot/get_bot_qrcode?bot_type={self.BOT_TYPE}"

        def _fetch_qr():
            r = req.get(qr_url_endpoint, timeout=15)
            r.raise_for_status()
            d = r.json()
            return d["qrcode"], d["qrcode_img_content"]

        print("\n[🔐] WeChat QR login required")
        try:
            qrcode, qrcode_url = _fetch_qr()
        except Exception as e:
            print(f"[❌] Failed to fetch WeChat QR code: {e}")
            return False

        def _display_qr(url):
            import qrcode as qr_lib
            qr = qr_lib.QRCode(border=1)
            qr.add_data(url)
            qr.make(fit=True)
            print()
            qr.print_ascii(invert=True)
            print(f"[*] 如二维码显示异常，请用浏览器打开链接扫码: {url}")

        _display_qr(qrcode_url)

        deadline = time.time() + 480
        refresh_count = 0
        max_refreshes = 3
        scanned_printed = False

        while time.time() < deadline:
            try:
                from urllib.parse import quote as _quote
                status_url = f"{base}/ilink/bot/get_qrcode_status?qrcode={_quote(qrcode)}"
                r = req.get(status_url, headers={"iLink-App-ClientVersion": "1"},
                            timeout=self.LONG_POLL_TIMEOUT_S)
                r.raise_for_status()
                d = r.json()
                status = d.get("status", "wait")

                if status == "wait":
                    pass
                elif status == "scaned":
                    if not scanned_printed:
                        print("\n[👀] QR scanned — please confirm in WeChat...")
                        scanned_printed = True
                elif status == "expired":
                    refresh_count += 1
                    if refresh_count > max_refreshes:
                        print("\n[❌] QR code expired too many times. Login aborted.")
                        return False
                    print(f"\n[⏳] QR expired, refreshing ({refresh_count}/{max_refreshes})...")
                    try:
                        qrcode, qrcode_url = _fetch_qr()
                        scanned_printed = False
                        _display_qr(qrcode_url)
                    except Exception as e:
                        print(f"[❌] Failed to refresh QR code: {e}")
                        return False
                elif status == "confirmed":
                    if not d.get("ilink_bot_id"):
                        print("[❌] Login confirmed but ilink_bot_id missing.")
                        return False
                    self.token = d.get("bot_token", "")
                    self.base_url = (d.get("baseurl") or base).rstrip("/")
                    self.authorized_id = d.get("ilink_user_id", "")
                    account_id = d.get("ilink_bot_id", "")
                    self.wc_config["token"] = self.token
                    self.wc_config["base_url"] = self.base_url
                    self.wc_config["authorized_id"] = self.authorized_id
                    self.wc_config["account_id"] = account_id
                    self._save_wc_config()
                    print(f"\n[✅] WeChat login successful! Bot: {account_id}, User: {self.authorized_id}")
                    return True
            except req.exceptions.Timeout:
                pass   # normal for long-poll
            except Exception as e:
                print(f"[!] WeChat QR poll error: {e}")
                time.sleep(2)

        print("\n[❌] WeChat login timed out.")
        return False

    # ------------------------------------------------------------------
    # CDN download helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_aes_key(aes_key_b64):
        """Mirror of parseAesKey in pic-decrypt.ts.
        Accepts base64(raw 16 bytes) or base64(hex string of 16 bytes)."""
        import re
        decoded = base64.b64decode(aes_key_b64)
        if len(decoded) == 16:
            return decoded
        if len(decoded) == 32 and re.fullmatch(b"[0-9a-fA-F]{32}", decoded):
            return bytes.fromhex(decoded.decode("ascii"))
        raise ValueError(f"aes_key must decode to 16 raw bytes or 32-char hex string, "
                         f"got {len(decoded)} bytes")

    @staticmethod
    def _decrypt_aes_ecb(ciphertext, key):
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as crypto_padding
        dec = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
        padded = dec.update(ciphertext) + dec.finalize()
        unpadder = crypto_padding.PKCS7(128).unpadder()
        return unpadder.update(padded) + unpadder.finalize()

    def _download_and_decrypt_cdn(self, encrypt_query_param, aes_key_b64):
        import requests as req
        from urllib.parse import quote
        cdn_base = self.wc_config.get("cdn_base_url", self.CDN_BASE_URL)
        url = f"{cdn_base}/download?encrypted_query_param={quote(encrypt_query_param)}"
        r = req.get(url, timeout=60)
        r.raise_for_status()
        key = self._parse_aes_key(aes_key_b64)
        return self._decrypt_aes_ecb(r.content, key)

    # ------------------------------------------------------------------
    # Inbound message handling
    # ------------------------------------------------------------------

    def _handle_message(self, msg):
        from_user_id = msg.get("from_user_id", "")
        context_token = msg.get("context_token")
        if context_token:
            self._context_tokens[from_user_id] = context_token

        if self.authorized_id and from_user_id != self.authorized_id:
            return

        for item in msg.get("item_list", []):
            item_type = item.get("type", 0)
            if item_type == 1:   # TEXT
                text = item.get("text_item", {}).get("text", "").strip()
                ref_msg = item.get("ref_msg")
                if ref_msg:
                    parts = []
                    if ref_msg.get("title"):
                        parts.append(ref_msg["title"])
                    ref_item = ref_msg.get("message_item")
                    if ref_item and ref_item.get("type") == 1:
                        ref_text = ref_item.get("text_item", {}).get("text", "").strip()
                        if ref_text:
                            parts.append(ref_text)
                    if parts:
                        text = f"[引用: {' | '.join(parts)}]\n{text}"
                if text and self.callback:
                    print(f"📩 WeChat: {text}")
                    threading.Thread(target=self.callback, args=(text,), daemon=True).start()
                return
            elif item_type == 3:  # VOICE — use transcribed text if available
                voice_text = item.get("voice_item", {}).get("text", "").strip()
                if voice_text and self.callback:
                    print(f"📩 WeChat: [Voice] {voice_text}")
                    threading.Thread(target=self.callback, args=(voice_text,), daemon=True).start()
                return
            elif item_type == 2:  # IMAGE
                media = item.get("image_item", {}).get("media", {})
                eqp = media.get("encrypt_query_param")
                aes_key = media.get("aes_key") or item.get("image_item", {}).get("aeskey")
                print("📩 WeChat: [Image]")
                if eqp and aes_key and self.callback:
                    def _send_image(eqp=eqp, aes_key=aes_key):
                        try:
                            image_bytes = self._download_and_decrypt_cdn(eqp, aes_key)
                            content = prepare_image_content(image_bytes, "这张图片里有什么？")
                            self.callback(content)
                        except Exception as e:
                            print(f"[!] WeChat image download error: {e}")
                            self.callback("[Image received]")
                    threading.Thread(target=_send_image, daemon=True).start()
                elif self.callback:
                    threading.Thread(target=self.callback,
                                     args=("[Image received]",), daemon=True).start()
                return
            elif item_type == 4:  # FILE
                file_item = item.get("file_item", {})
                file_name = file_item.get("file_name", "file")
                media = file_item.get("media", {})
                eqp = media.get("encrypt_query_param")
                aes_key = media.get("aes_key")
                print(f"📩 WeChat: [File: {file_name}]")
                if eqp and aes_key and self.file_saver and self.callback:
                    def _send_file(file_name=file_name, eqp=eqp, aes_key=aes_key):
                        try:
                            file_bytes = self._download_and_decrypt_cdn(eqp, aes_key)
                            file_path = self.file_saver(file_name, file_bytes)
                            self.callback(f"[Uploaded file: {file_path}]")
                        except Exception as e:
                            print(f"[!] WeChat file download error: {e}")
                            self.callback(f"[File received: {file_name}]")
                    threading.Thread(target=_send_file, daemon=True).start()
                elif self.callback:
                    threading.Thread(target=self.callback,
                                     args=(f"[File received: {file_name}]",), daemon=True).start()
                return

    # ------------------------------------------------------------------
    # Connector interface
    # ------------------------------------------------------------------

    def listen(self, callback, stop_on_auth=False):
        self.callback = callback
        print("\n--- MMClaw Kernel Active (WeChat Mode) ---")

        if not self.token:
            if not self._login_qr():
                return
        elif stop_on_auth:
            print(f"\n[✅] WeChat identity already verified: {self.authorized_id}")
            return

        if stop_on_auth:
            return

        print(f"[*] Listening for WeChat messages from: {self.authorized_id or '(any)'}")

        def _poll_loop():
            consecutive_failures = 0
            next_timeout_s = self.LONG_POLL_TIMEOUT_S
            while not self._stop_event.is_set():
                try:
                    body = {
                        "get_updates_buf": self._get_updates_buf,
                        "base_info": {"channel_version": self.CHANNEL_VERSION},
                    }
                    data = self._api_post("ilink/bot/getupdates", body,
                                          timeout=next_timeout_s + 5)

                    ret = data.get("ret", 0)
                    errcode = data.get("errcode", 0)
                    if ret != 0 or errcode != 0:
                        if errcode == -14 or ret == -14:
                            print("[!] WeChat session expired (errcode -14), pausing 1 hour...")
                            consecutive_failures = 0
                            self._stop_event.wait(3600)
                            continue
                        consecutive_failures += 1
                        print(f"[!] WeChat getUpdates error: ret={ret} errcode={errcode} "
                              f"errmsg={data.get('errmsg', '')}")
                        delay = 30 if consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES else 2
                        if consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                            consecutive_failures = 0
                        self._stop_event.wait(delay)
                        continue

                    consecutive_failures = 0
                    server_timeout_ms = data.get("longpolling_timeout_ms", 0)
                    if server_timeout_ms and server_timeout_ms > 0:
                        next_timeout_s = server_timeout_ms / 1000
                    new_buf = data.get("get_updates_buf", "")
                    if new_buf and new_buf != self._get_updates_buf:
                        self._get_updates_buf = new_buf
                        self.wc_config["get_updates_buf"] = new_buf
                        self._save_wc_config()

                    for msg in data.get("msgs", []):
                        self._handle_message(msg)

                except Exception as e:
                    # requests.Timeout is also caught here — that's normal for long-poll
                    import requests
                    if isinstance(e, requests.exceptions.Timeout):
                        continue
                    consecutive_failures += 1
                    print(f"[!] WeChat poll error: {e}")
                    delay = 30 if consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES else 2
                    if consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                        consecutive_failures = 0
                    self._stop_event.wait(delay)

        threading.Thread(target=_poll_loop, daemon=True).start()
        self._stop_event.wait()

    def start_typing(self):
        self._typing = True
        user_id = self.authorized_id
        if not user_id:
            return

        def _type_loop():
            ticket = None
            while self._typing:
                try:
                    if not ticket:
                        cfg_data = self._api_post(
                            "ilink/bot/getconfig",
                            {"ilink_user_id": user_id,
                             "context_token": self._context_tokens.get(user_id, ""),
                             "base_info": {"channel_version": self.CHANNEL_VERSION}},
                            timeout=10,
                        )
                        ticket = cfg_data.get("typing_ticket")
                    if ticket:
                        self._api_post(
                            "ilink/bot/sendtyping",
                            {"ilink_user_id": user_id, "typing_ticket": ticket,
                             "status": 1,
                             "base_info": {"channel_version": self.CHANNEL_VERSION}},
                            timeout=10,
                        )
                except Exception:
                    ticket = None
                self._stop_event.wait(4)

        threading.Thread(target=_type_loop, daemon=True).start()

    def stop_typing(self):
        self._typing = False
        user_id = self.authorized_id
        if not user_id or not self.token:
            return
        try:
            cfg_data = self._api_post(
                "ilink/bot/getconfig",
                {"ilink_user_id": user_id,
                 "context_token": self._context_tokens.get(user_id, ""),
                 "base_info": {"channel_version": self.CHANNEL_VERSION}},
                timeout=10,
            )
            ticket = cfg_data.get("typing_ticket")
            if ticket:
                self._api_post(
                    "ilink/bot/sendtyping",
                    {"ilink_user_id": user_id, "typing_ticket": ticket,
                     "status": 2,
                     "base_info": {"channel_version": self.CHANNEL_VERSION}},
                    timeout=10,
                )
        except Exception:
            pass

    def send(self, message):
        if not self.authorized_id or not self.token:
            return
        import uuid
        limit = 4000
        for chunk in [message[i:i+limit] for i in range(0, len(message), limit)]:
            try:
                msg_obj = {
                    "from_user_id": "",
                    "to_user_id": self.authorized_id,
                    "client_id": str(uuid.uuid4()),
                    "message_type": 2,   # BOT
                    "message_state": 2,  # FINISH
                    "item_list": [{"type": 1, "text_item": {"text": f"⚡ {chunk}"}}],
                }
                context_token = self._context_tokens.get(self.authorized_id)
                if context_token:
                    msg_obj["context_token"] = context_token
                self._api_post(
                    "ilink/bot/sendmessage",
                    {"msg": msg_obj, "base_info": {"channel_version": self.CHANNEL_VERSION}},
                    timeout=15,
                )
            except Exception as e:
                print(f"[!] WeChat send error: {e}")
                break

    # ------------------------------------------------------------------
    # CDN upload helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _aes_ecb_padded_size(plaintext_size):
        import math
        return math.ceil((plaintext_size + 1) / 16) * 16

    @staticmethod
    def _encrypt_aes_ecb(plaintext, key):
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as crypto_padding
        padder = crypto_padding.PKCS7(128).padder()
        padded = padder.update(plaintext) + padder.finalize()
        enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
        return enc.update(padded) + enc.finalize()

    def _upload_to_cdn(self, file_path, to_user_id, media_type):
        """Encrypt file and upload to WeChat CDN. Returns upload info dict."""
        import hashlib
        import requests as req
        from urllib.parse import quote

        with open(file_path, "rb") as f:
            plaintext = f.read()

        rawsize = len(plaintext)
        rawfilemd5 = hashlib.md5(plaintext).hexdigest()
        aeskey = os.urandom(16)
        filekey = os.urandom(16).hex()
        filesize = self._aes_ecb_padded_size(rawsize)

        upload_resp = self._api_post("ilink/bot/getuploadurl", {
            "filekey": filekey,
            "media_type": media_type,
            "to_user_id": to_user_id,
            "rawsize": rawsize,
            "rawfilemd5": rawfilemd5,
            "filesize": filesize,
            "no_need_thumb": True,
            "aeskey": aeskey.hex(),
            "base_info": {"channel_version": self.CHANNEL_VERSION},
        })

        upload_param = upload_resp.get("upload_param")
        if not upload_param:
            raise RuntimeError(f"getuploadurl returned no upload_param: {upload_resp}")

        ciphertext = self._encrypt_aes_ecb(plaintext, aeskey)
        cdn_base = self.wc_config.get("cdn_base_url", self.CDN_BASE_URL)
        cdn_url = (f"{cdn_base}/upload"
                   f"?encrypted_query_param={quote(upload_param)}"
                   f"&filekey={quote(filekey)}")

        download_param = None
        for attempt in range(1, 4):
            r = req.post(cdn_url, data=ciphertext,
                         headers={"Content-Type": "application/octet-stream"},
                         timeout=120)
            if 400 <= r.status_code < 500:
                raise RuntimeError(f"CDN upload client error {r.status_code}: "
                                   f"{r.headers.get('x-error-message', r.text)}")
            if r.status_code != 200:
                if attempt < 3:
                    continue
                raise RuntimeError(f"CDN upload failed after 3 attempts: {r.status_code}")
            download_param = r.headers.get("x-encrypted-param")
            if download_param:
                break
            if attempt == 3:
                raise RuntimeError("CDN upload response missing x-encrypted-param header")

        return {
            "download_encrypted_query_param": download_param,
            "aeskey": aeskey,
            "file_size": rawsize,
            "file_size_ciphertext": filesize,
            "filekey": filekey,
        }

    def _send_media_message(self, to_user_id, context_token, item):
        import uuid
        msg_obj = {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": str(uuid.uuid4()),
            "message_type": 2,
            "message_state": 2,
            "item_list": [item],
        }
        if context_token:
            msg_obj["context_token"] = context_token
        self._api_post(
            "ilink/bot/sendmessage",
            {"msg": msg_obj, "base_info": {"channel_version": self.CHANNEL_VERSION}},
            timeout=15,
        )

    def send_file(self, path):
        if not self.authorized_id or not self.token:
            return
        import mimetypes
        full_path = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(full_path):
            self.send(f"[File not found: {path}]")
            return

        mime = mimetypes.guess_type(full_path)[0] or "application/octet-stream"
        context_token = self._context_tokens.get(self.authorized_id)

        def _aes_key_b64(raw_key):
            # WeChat expects base64(hex_string_of_key) — NOT base64(raw_bytes).
            # parseAesKey on the client side: if decoded length == 32 and all hex chars,
            # it re-parses as hex to recover the 16-byte key. See pic-decrypt.ts.
            return base64.b64encode(raw_key.hex().encode("ascii")).decode()

        try:
            if mime.startswith("image/"):
                info = self._upload_to_cdn(full_path, self.authorized_id, self._MEDIA_IMAGE)
                item = {
                    "type": self._ITEM_IMAGE,
                    "image_item": {
                        "media": {
                            "encrypt_query_param": info["download_encrypted_query_param"],
                            "aes_key": _aes_key_b64(info["aeskey"]),
                            "encrypt_type": 1,
                        },
                        "mid_size": info["file_size_ciphertext"],
                    },
                }
            elif mime.startswith("video/"):
                info = self._upload_to_cdn(full_path, self.authorized_id, self._MEDIA_VIDEO)
                item = {
                    "type": self._ITEM_VIDEO,
                    "video_item": {
                        "media": {
                            "encrypt_query_param": info["download_encrypted_query_param"],
                            "aes_key": _aes_key_b64(info["aeskey"]),
                            "encrypt_type": 1,
                        },
                        "video_size": info["file_size_ciphertext"],
                    },
                }
            else:
                info = self._upload_to_cdn(full_path, self.authorized_id, self._MEDIA_FILE)
                item = {
                    "type": self._ITEM_FILE,
                    "file_item": {
                        "media": {
                            "encrypt_query_param": info["download_encrypted_query_param"],
                            "aes_key": _aes_key_b64(info["aeskey"]),
                            "encrypt_type": 1,
                        },
                        "file_name": os.path.basename(full_path),
                        "len": str(info["file_size"]),
                    },
                }
            self._send_media_message(self.authorized_id, context_token, item)
        except Exception as e:
            print(f"[!] WeChat send_file error: {e}")
            self.send(f"[File upload failed: {e}]")


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

    def start_typing(self):
        self.send("⏳")

    def stop_typing(self):
        self.send("✅")

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
            future = asyncio.run_coroutine_threadsafe(self._send_async(f"⚡ {chunk}"), self._loop)
            try:
                future.result(timeout=30)
            except Exception as e:
                print(f"[!] QQ Bot Send Error: {e}")
                break

    def send_file(self, path):
        self.send("❌ QQ Bot 暂不支持发送文件。")
