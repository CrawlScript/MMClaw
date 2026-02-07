import os
import json
import subprocess
import threading
import telebot
import shutil
import random
from .config import ConfigManager

class TerminalConnector(object):
    def listen(self, callback):
        print("\n--- PipClaw Kernel Active (Terminal Mode) ---")
        while True:
            try:
                text = input("👤 You: ").strip()
                if text.lower() in ["exit", "quit"]: break
                if text: callback(text) 
            except KeyboardInterrupt: break

    def send(self, message):
        print(f"\r🐈 PipClaw: {message}\n👤 You: ", end="", flush=True)

    def send_file(self, path):
        full_path = os.path.expanduser(path)
        print(f"\r🐈 PipClaw: [FILE SENT] {os.path.abspath(full_path)}\n👤 You: ", end="", flush=True)

class TelegramConnector(object):
    def __init__(self, token, authorized_user_id):
        self.bot = telebot.TeleBot(token)
        self.authorized_user_id = int(authorized_user_id)
        
    def listen(self, callback):
        print(f"\n--- PipClaw Kernel Active (Telegram Mode) ---")
        print(f"[*] Listening for messages from User ID: {self.authorized_user_id}")
        
        @self.bot.message_handler(func=lambda message: message.from_user.id == self.authorized_user_id)
        def handle_message(message):
            callback(message.text)
            
        @self.bot.message_handler(func=lambda message: message.from_user.id != self.authorized_user_id)
        def unauthorized(message):
            self.bot.reply_to(message, "🚫 Unauthorized. I only respond to my master.")

        self.bot.infinity_polling()

    def send(self, message):
        try:
            self.bot.send_message(self.authorized_user_id, f"🐈 {message}")
        except Exception as e:
            print(f"[!] Telegram Send Error: {e}")

    def send_file(self, path):
        path = os.path.expanduser(path)
        try:
            with open(path, 'rb') as f:
                self.bot.send_document(self.authorized_user_id, f)
        except Exception as e:
            self.send(f"Error sending file: {str(e)}")

class WhatsAppConnector(object):
    def __init__(self):
        self.process = None
        self.callback = None
        self.active_recipient = None
        self.config = ConfigManager.load()
        self.authorized_id = self.config.get("whatsapp_authorized_id")
        self.verify_code = str(random.randint(100000, 999999))
        self.last_sent_text = None
        self.bridge_path = os.path.join(os.path.dirname(__file__), "bridge.js")

    def _ensure_node(self):
        if not shutil.which("node"):
            print("[❌] Node.js not found. Please install Node.js to use WhatsApp mode.")
            return False
        return True

    def _get_node_env(self):
        """Prepare environment to find global node_modules."""
        env = os.environ.copy()
        try:
            npm_root = subprocess.check_output(["npm", "root", "-g"], text=True, stderr=subprocess.DEVNULL).strip()
            existing_path = env.get("NODE_PATH", "")
            env["NODE_PATH"] = f"{npm_root}{os.pathsep}{existing_path}" if existing_path else npm_root
        except:
            pass
        return env

    def _ensure_deps(self):
        # Check global first using npm list -g
        check_global = subprocess.run(["npm", "list", "-g", "@whiskeysockets/baileys", "--depth=0"], capture_output=True)
        if check_global.returncode == 0:
            return

        # Check local using npm list
        check_local = subprocess.run(["npm", "list", "@whiskeysockets/baileys", "--depth=0"], capture_output=True)
        if check_local.returncode == 0:
            return

        print("[*] Installing WhatsApp bridge dependencies globally...")
        try:
            # Attempt global install as requested
            subprocess.run(["npm", "install", "-g", "@whiskeysockets/baileys", "qrcode-terminal", "pino"], check=True)
        except subprocess.CalledProcessError:
            print("[!] Global install failed. Attempting local install...")
            subprocess.run(["npm", "install", "@whiskeysockets/baileys", "qrcode-terminal", "pino"], check=True)

    def listen(self, callback):
        if not self._ensure_node(): return
        self._ensure_deps()
        self.callback = callback
        
        env = self._get_node_env()
        self.process = subprocess.Popen(
            ["node", self.bridge_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
            env=env, text=True, bufsize=1
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
                                    self.config["whatsapp_authorized_id"] = sender
                                    ConfigManager.save(self.config)
                                    print(f"\n[⭐] AUTH SUCCESS! PipClaw is now locked to: {sender}")
                                    self.send("🐈 Verification Successful! I am now your personal agent.")
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
                                self.callback(text)

                        elif event["type"] == "connected":
                            if not self.authorized_id:
                                print(f"\n[🔐] WHATSAPP VERIFICATION REQUIRED")
                                print(f"[*] PLEASE SEND THIS CODE TO YOURSELF ON WHATSAPP: {self.verify_code}")
                            else:
                                print(f"\n[✅] WhatsApp Active")

                    except Exception as e:
                        print(f"[!] Bridge Parse Error: {e}")
                else:
                    print(line, end="")

        threading.Thread(target=output_reader, daemon=True).start()
        self.process.wait()

    def send(self, message):
        if not self.process or not (self.active_recipient or self.authorized_id): return
        recipient = self.active_recipient or self.authorized_id
        self.last_sent_text = message
        payload = {"to": recipient, "text": message}
        self.process.stdin.write(f"SEND:{json.dumps(payload)}\n")
        self.process.stdin.flush()

    def send_file(self, path):
        self.send(f"📦 [File]: {os.path.abspath(os.path.expanduser(path))}")