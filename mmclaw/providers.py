import json
import urllib.request
import urllib.error
import base64
import io
import time

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

def compress_image(image_bytes):
    """Resizes and compresses image to reduce API costs and meet provider limits."""
    if PILImage is None:
        return image_bytes
    
    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        # Convert RGBA to RGB if necessary
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        # Max dimension 1024px while maintaining aspect ratio
        max_size = 1024
        if max(img.size) > max_size:
            ratio = max_size / float(max(img.size))
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, PILImage.LANCZOS)
        
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=80, optimize=True)
        return output.getvalue()
    except Exception as e:
        print(f"[!] Compression Error: {e}")
        return image_bytes

def prepare_image_content(image_bytes, text="What is in this image?"):
    """Compresses an image and returns a list of content blocks for OpenAI-compatible APIs."""
    compressed_file = compress_image(image_bytes)
    base64_image = base64.b64encode(compressed_file).decode('utf-8')
    
    return [
        {"type": "text", "text": text},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
        }
    ]

class Engine(object):
    def __init__(self, config):
        self.config = config # Store for refreshing
        self.engine_type = config["engine_type"] # Raises KeyError if missing
        engine_config = config["engines"][self.engine_type]
        
        self.api_key = engine_config["api_key"]
        self.base_url = engine_config["base_url"].rstrip('/')
        self.model = engine_config["model"]
        self.debug = config.get("debug", False)
        self.account_id = engine_config.get("account_id")
        self.stream = config.get("stream", True)
        
        # Correct URL for Codex backend-api
        if self.engine_type == "codex":
            self.base_url = "https://chatgpt.com/backend-api/codex"

    def _refresh_codex_token(self):
        """Refreshes the OAuth token for Codex provider."""
        try:
            from .config import ConfigManager
            engine_config = self.config["engines"]["codex"]
            refresh_token = engine_config.get("refresh_token")
            if not refresh_token:
                return False
                
            print("[*] Codex: Refreshing Access Token...")
            import urllib.parse
            data = urllib.parse.urlencode({
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
            }).encode()
            
            req = urllib.request.Request(
                "https://auth.openai.com/oauth/token", 
                data=data, 
                method="POST"
            )
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            
            with urllib.request.urlopen(req) as resp:
                token_data = json.loads(resp.read().decode())
                new_access_token = token_data["access_token"]
                
                # Update in memory and save to config
                self.api_key = new_access_token
                self.config["engines"]["codex"]["api_key"] = new_access_token
                if "refresh_token" in token_data:
                    self.config["engines"]["codex"]["refresh_token"] = token_data["refresh_token"]
                
                ConfigManager.save(self.config)
                print("[✓] Codex: Token refreshed successfully.")
                return True
        except Exception as e:
            print(f"[!] Codex Refresh Error: {e}")
            return False

    def _ask_blocking(self, url, payload):
        payload = {**payload, "stream": False}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; codex-cli/1.0)"
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data["choices"][0]["message"]

    def _ask_stream(self, url, payload):
        payload = {**payload, "stream": True}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; codex-cli/1.0)"
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as response:
            full_content = ""
            for line in response:
                line = line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    res_data = json.loads(data_str)
                    content = res_data["choices"][0]["delta"].get("content")
                    if content:
                        full_content += content
                except:
                    continue
            return {"role": "assistant", "content": full_content}

    def ask(self, messages, tools=None, retry=1):
        last_err = None
        for attempt in range(retry + 1):
            try:
                return self.ask_once(messages, tools=tools)
            except urllib.error.HTTPError as e:
                if 400 <= e.code < 500:
                    raise
                last_err = e
            except Exception as e:
                last_err = e
            if attempt < retry:
                print(f"[!] Request failed ({last_err}), retrying...")
                time.sleep(2)
        raise last_err

    def ask_once(self, messages, tools=None):
        if self.engine_type in ["openai", "codex", "google", "deepseek", "openrouter", "kimi_ai", "kimi_cn", "minimax_io", "minimax_cn"] or self.engine_type.startswith("openai_compatible_"):
            if self.engine_type == "codex":
                # Responses API (Codex)
                system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
                user_messages = [m for m in messages if m["role"] != "system"]
                
                input_items = []
                for m in user_messages:
                    input_items.append({
                        "role": m["role"],
                        "content": m["content"]
                    })
                
                payload = {
                    "model": self.model,
                    "instructions": system_msg,
                    "input": input_items,
                    "tools": tools or [],
                    "tool_choice": "auto",
                    "parallel_tool_calls": True,
                    "store": False,
                    "stream": True
                }
                url = f"{self.base_url}/responses"
            else:
                # ChatCompletions API (standard)
                payload = {
                    "model": self.model,
                    "messages": messages,
                }
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"
                url = f"{self.base_url}/chat/completions"

            def make_request(token, current_payload):
                headers = {
                    "Authorization": f"Bearer {token}", 
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (compatible; codex-cli/1.0)"
                }
                
                if self.engine_type == "codex" and self.account_id:
                    headers["ChatGPT-Account-ID"] = self.account_id
                
                return urllib.request.Request(
                    url,
                    data=json.dumps(current_payload).encode("utf-8"),
                    headers=headers,
                    method="POST"
                )
            
            def parse_codex_response(res_data):
                etype = res_data.get("type")
                if etype == "response.output_text.delta":
                    return res_data.get("delta", "")
                
                # Fallback for other content formats
                msg_obj = res_data.get("message", {})
                content = msg_obj.get("content", "")
                if isinstance(content, list):
                    return "".join([i.get("text", "") for i in content if isinstance(i, dict)])
                return content if isinstance(content, str) else ""

            try:
                if self.debug:
                    print(f"\n[LLM Request ({self.engine_type})]\n{json.dumps(payload, indent=2)}\n")
                
                if self.engine_type == "codex":
                    req = make_request(self.api_key, payload)
                    with urllib.request.urlopen(req, timeout=60) as response:
                        full_content = ""
                        for line in response:
                            line = line.decode("utf-8").strip()
                            if not line.startswith("data: "): continue

                            data_str = line[6:]
                            if data_str == "[DONE]": break
                            try:
                                res_data = json.loads(data_str)
                                if res_data.get("type") == "response.completed": break

                                chunk_text = parse_codex_response(res_data)
                                if chunk_text: full_content += chunk_text
                            except: continue
                        msg = {"role": "assistant", "content": full_content}
                else:
                    msg = self._ask_stream(url, payload) if self.stream else self._ask_blocking(url, payload)

                if self.debug:
                    print(f"\n[LLM Response]\n{json.dumps(msg, indent=2)}\n")
                return msg
            except Exception as e:
                # Handle token expiry for codex
                if self.engine_type == "codex" and isinstance(e, urllib.error.HTTPError):
                    if e.code == 401:
                        if self._refresh_codex_token():
                            try:
                                # Retry with new token
                                req = make_request(self.api_key, payload)
                                with urllib.request.urlopen(req, timeout=60) as response:
                                    full_content = ""
                                    for line in response:
                                        line = line.decode("utf-8").strip()
                                        if not line.startswith("data: "): continue
                                        
                                        data_str = line[6:]
                                        if data_str == "[DONE]": break
                                        try:
                                            res_data = json.loads(data_str)
                                            if res_data.get("type") == "response.completed": break
                                            
                                            chunk_text = parse_codex_response(res_data)
                                            if chunk_text: full_content += chunk_text
                                        except: continue
                                    return {"role": "assistant", "content": full_content}
                            except Exception as retry_e:
                                print(f"[!] Retry Error: {retry_e}")
                    
                    # Handle 500 error for Codex
                    elif e.code == 500:
                        print("[!] Codex: 500 Error detected.")
                
                print(f"[!] Engine Error: {e}")
                error_msg = f"Engine Error: {e}"
                if isinstance(e, urllib.error.HTTPError):
                    try:
                        error_body = e.read().decode("utf-8")
                        print(f"    Response Body: {error_body}")
                        # Detect if vision is not supported
                        if "vision" in error_body.lower() or "image" in error_body.lower():
                            error_msg = (
                                f"❌ The current model ({self.model}) does not support images. "
                                "Please use 'mmclaw config' to choose a vision-capable model like 'gpt-4o-mini' or 'claude-3.5-sonnet'."
                            )
                    except:
                        pass
                # For a tutorial, we return a simple error message in message format
                return {"role": "assistant", "content": error_msg}
        else:
            return {"role": "assistant", "content": f"Unsupported Engine: {self.engine_type}"}