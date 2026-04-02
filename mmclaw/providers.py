import json
import random
import string
import urllib.request
import urllib.error
import base64
import io
import time


def _gemini_cli_activity_id() -> str:
    """Generate a short random per-request activity ID, mirroring Gemini CLI behaviour."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

GEMINI_CLI_CLIENT_ID     = base64.b64decode("NjgxMjU1ODA5Mzk1LW9vOGZ0Mm9wcmRybnA5ZTNhcWY2YXYz").decode() + base64.b64decode("aG1kaWIxMzVqLmFwcHMuZ29vZ2xldXNlcmNvbnRlbnQuY29t").decode()
GEMINI_CLI_CLIENT_SECRET = base64.b64decode("R09DU1BYLTR1SGdNUG0tMW8=").decode() + base64.b64decode("N1NrLWdlVjZDdTVjbFhGc3hs").decode()
GEMINI_CLI_ENDPOINT      = "https://cloudcode-pa.googleapis.com"
GEMINI_CLI_HEADERS       = {
    "User-Agent":      "google-cloud-sdk vscode_cloudshelleditor/0.1",
    "X-Goog-Api-Client": "gl-node/22.17.0",
    "Client-Metadata": json.dumps({"ideType": "GEMINI_CLI", "platform": "PLATFORM_UNSPECIFIED", "pluginType": "GEMINI"}),
}

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
        
        self.api_key = engine_config.get("api_key", "")
        self.base_url = engine_config.get("base_url", "").rstrip('/')
        self.model = engine_config["model"]
        self.debug = config.get("debug", False)
        self.account_id = engine_config.get("account_id")
        self.stream = config.get("stream", True)
        self._gemini_cli_model_idx = 0
        
        # Correct URL for Codex backend-api
        if self.engine_type == "codex":
            self.base_url = "https://chatgpt.com/backend-api/codex"
        elif self.engine_type == "gemini-cli":
            self.base_url = GEMINI_CLI_ENDPOINT

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

    def _refresh_gemini_cli_token(self):
        """Refreshes the OAuth token for Gemini CLI provider."""
        try:
            from .config import ConfigManager
            import urllib.parse
            engine_config = self.config["engines"]["gemini-cli"]
            refresh_token = engine_config.get("refresh_token")
            if not refresh_token:
                return False
            print("[*] Gemini CLI: Refreshing access token...")
            data = urllib.parse.urlencode({
                "grant_type":    "refresh_token",
                "refresh_token": refresh_token,
                "client_id":     GEMINI_CLI_CLIENT_ID,
                "client_secret": GEMINI_CLI_CLIENT_SECRET,
            }).encode()
            req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urllib.request.urlopen(req, timeout=30) as resp:
                token_data = json.loads(resp.read().decode())
                new_token = token_data["access_token"]
                engine_config["api_key"] = new_token
                engine_config["expiry_date"] = int((time.time() + token_data.get("expires_in", 3600)) * 1000)
                if "refresh_token" in token_data:
                    engine_config["refresh_token"] = token_data["refresh_token"]
                self.api_key = new_token
                ConfigManager.save(self.config)
                print("[✓] Gemini CLI: Token refreshed.")
                return True
        except Exception as e:
            print(f"[!] Gemini CLI Refresh Error: {e}")
            return False

    def _get_gemini_cli_project_id(self):
        """Discovers and caches the GCP project ID via loadCodeAssist, onboarding free tier if needed."""
        from .config import ConfigManager
        engine_config = self.config["engines"]["gemini-cli"]
        if engine_config.get("project_id"):
            return engine_config["project_id"]
        try:
            metadata = {"ideType": "IDE_UNSPECIFIED", "platform": "PLATFORM_UNSPECIFIED", "pluginType": "GEMINI"}
            body = json.dumps({"metadata": metadata}).encode()
            req = urllib.request.Request(
                f"{GEMINI_CLI_ENDPOINT}/v1internal:loadCodeAssist",
                data=body,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            # cloudaicompanionProject can be a string or {"id": "..."}
            raw = data.get("cloudaicompanionProject")
            if isinstance(raw, str):
                project_id = raw.strip()
            elif isinstance(raw, dict):
                project_id = (raw.get("id") or "").strip()
            else:
                project_id = ""
            # No managed project yet — onboard as free tier
            if not project_id:
                project_id = self._onboard_gemini_cli_free_tier()
            if project_id:
                engine_config["project_id"] = project_id
                ConfigManager.save(self.config)
            return project_id
        except Exception as e:
            print(f"[!] Gemini CLI: failed to discover project ID: {e}")
            return ""

    def _onboard_gemini_cli_free_tier(self):
        """Onboards the user on the free tier and returns the managed project ID."""
        try:
            print("[*] Gemini CLI: onboarding free tier...")
            metadata = {"ideType": "IDE_UNSPECIFIED", "platform": "PLATFORM_UNSPECIFIED", "pluginType": "GEMINI"}
            body = json.dumps({"tierId": "free-tier", "metadata": metadata}).encode()
            req = urllib.request.Request(
                f"{GEMINI_CLI_ENDPOINT}/v1internal:onboardUser",
                data=body,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode())
            for _ in range(10):
                if payload.get("done"):
                    break
                op_name = payload.get("name")
                if not op_name:
                    break
                time.sleep(5)
                req = urllib.request.Request(
                    f"{GEMINI_CLI_ENDPOINT}/v1internal/{op_name}",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    method="GET"
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    payload = json.loads(resp.read().decode())
            project_id = ((payload.get("response") or {}).get("cloudaicompanionProject") or {}).get("id", "").strip()
            if project_id:
                print(f"[✓] Gemini CLI: onboarded project {project_id}")
            return project_id
        except Exception as e:
            print(f"[!] Gemini CLI: onboard error: {e}")
            return ""

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
                if 400 <= e.code < 500 and e.code != 429:
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
        elif self.engine_type == "gemini-cli":
            engine_config = self.config["engines"]["gemini-cli"]
            # Proactively refresh if within 5 min of expiry
            if time.time() * 1000 >= engine_config.get("expiry_date", 0) - 5 * 60 * 1000:
                self._refresh_gemini_cli_token()

            project_id = self._get_gemini_cli_project_id()

            # Convert messages to Gemini format
            system_instruction = None
            contents = []
            for msg in messages:
                role, content = msg["role"], msg["content"]
                if role == "system":
                    text = content if isinstance(content, str) else " ".join(i.get("text", "") for i in content if isinstance(i, dict))
                    system_instruction = {"parts": [{"text": text}]}
                    continue
                gemini_role = "model" if role == "assistant" else "user"
                if isinstance(content, str):
                    parts = [{"text": content}]
                elif isinstance(content, list):
                    parts = [{"text": i["text"]} for i in content if i.get("type") == "text"]
                else:
                    parts = [{"text": str(content)}]
                contents.append({"role": gemini_role, "parts": parts})

            model_list = engine_config.get("model_list") or [self.model]
            current_model = model_list[self._gemini_cli_model_idx % len(model_list)]
            self._gemini_cli_model_idx += 1

            def _build_request_body(model):
                body = {"project": project_id, "model": model, "request": {"contents": contents}, "userAgent": "mmclaw"}
                if system_instruction:
                    body["request"]["systemInstruction"] = system_instruction
                return body

            request_body = _build_request_body(current_model)

            if self.debug:
                print(f"\n[LLM Request (gemini-cli)] model={current_model}\n{json.dumps(request_body, indent=2)}\n")

            def _do_request(body=None):
                if body is None:
                    body = request_body
                headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "Accept": "text/event-stream", "x-activity-request-id": _gemini_cli_activity_id(), **GEMINI_CLI_HEADERS}
                req = urllib.request.Request(
                    f"{GEMINI_CLI_ENDPOINT}/v1internal:streamGenerateContent?alt=sse",
                    data=json.dumps(body).encode("utf-8"),
                    headers=headers, method="POST"
                )
                with urllib.request.urlopen(req, timeout=120) as response:
                    full_content = ""
                    thought_content = ""
                    chunk_count = 0
                    data_line_count = 0
                    for line in response:
                        line = line.decode("utf-8").strip()
                        if not line.startswith("data:"):
                            continue
                        data_line_count += 1
                        data_str = line[5:].strip()
                        if not data_str:
                            continue
                        try:
                            chunk = json.loads(data_str)
                            chunk_count += 1
                            # Cloud Code Assist may wrap in "response" or return candidates directly
                            candidates = (
                                chunk.get("candidates")
                                or chunk.get("response", {}).get("candidates")
                                or []
                            )
                            if not candidates:
                                if self.debug:
                                    print(f"[gemini-cli] chunk #{chunk_count} has no candidates, keys={list(chunk.keys())}, raw={json.dumps(chunk)[:200]}")
                                continue
                            candidate = candidates[0]
                            finish_reason = candidate.get("finishReason")
                            parts = (candidate.get("content") or {}).get("parts") or []
                            if not parts and finish_reason and self.debug:
                                print(f"[gemini-cli] chunk #{chunk_count} finishReason={finish_reason}, no parts")
                            for part in parts:
                                if "text" not in part:
                                    continue
                                if part.get("thought"):
                                    thought_content += part["text"]
                                else:
                                    full_content += part["text"]
                        except Exception as ex:
                            if self.debug:
                                print(f"[gemini-cli] parse error: {ex}, raw={data_str[:200]}")
                            continue
                    if self.debug:
                        print(f"[gemini-cli] stream done: data_lines={data_line_count}, chunks={chunk_count}, content_len={len(full_content)}, thought_len={len(thought_content)}")
                        if not full_content and not thought_content:
                            print(f"[gemini-cli] WARNING: empty response!")
                    # Fall back to thought content if model only returned thinking parts
                    return {"role": "assistant", "content": full_content or thought_content}

            try:
                msg = _do_request()
                if self.debug:
                    print(f"\n[LLM Response]\n{json.dumps(msg, indent=2)}\n")
                return msg
            except urllib.error.HTTPError as e:
                error_body = ""
                try: error_body = e.read().decode("utf-8")
                except: pass
                if self.debug:
                    print(f"[gemini-cli] HTTPError {e.code}: {error_body[:500]}")
                if e.code == 401 and self._refresh_gemini_cli_token():
                    if self.debug:
                        print(f"[gemini-cli] token refreshed, retrying...")
                    return _do_request()
                if e.code == 429 or "RESOURCE_EXHAUSTED" in error_body:
                    fallback_models = engine_config.get("fallback_models") or []
                    if fallback_models:
                        subset = random.sample(fallback_models, min(2, len(fallback_models)))
                        if self.debug:
                            print(f"[gemini-cli] quota exceeded for {current_model}, trying fallbacks: {subset}")
                        for fb in subset:
                            try:
                                return _do_request(_build_request_body(fb))
                            except urllib.error.HTTPError as fe:
                                fb_body = ""
                                try: fb_body = fe.read().decode("utf-8")
                                except: pass
                                if self.debug:
                                    print(f"[gemini-cli] fallback {fb} also failed ({fe.code}): {fb_body[:200]}")
                                if fe.code != 429 and "RESOURCE_EXHAUSTED" not in fb_body:
                                    raise
                raise
            except Exception as e:
                import traceback
                if self.debug:
                    print(f"[gemini-cli] Exception: {e}\n{traceback.format_exc()}")
                raise
        else:
            return {"role": "assistant", "content": f"Unsupported Engine: {self.engine_type}"}