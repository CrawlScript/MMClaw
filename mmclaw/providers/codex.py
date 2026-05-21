import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .base import BaseProvider


class CodexProvider(BaseProvider):
    supports_native_tools = True

    def __init__(self, config):
        super().__init__(config)
        self.base_url = "https://chatgpt.com/backend-api/codex"
        engine_config = config["engines"][self.engine_type]
        self.account_id = engine_config.get("account_id")

    def _refresh_codex_token(self):
        try:
            from ..config import ConfigManager

            engine_config = self.config["engines"]["codex"]
            refresh_token = engine_config.get("refresh_token")
            if not refresh_token:
                return False

            print("[*] Codex: Refreshing Access Token...")
            data = urllib.parse.urlencode({
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
            }).encode()

            req = urllib.request.Request(
                "https://auth.openai.com/oauth/token",
                data=data,
                method="POST",
            )
            req.add_header("Content-Type", "application/x-www-form-urlencoded")

            with urllib.request.urlopen(req) as resp:
                token_data = json.loads(resp.read().decode())

            self.api_key = token_data["access_token"]
            engine_config["api_key"] = self.api_key
            if "refresh_token" in token_data:
                engine_config["refresh_token"] = token_data["refresh_token"]

            ConfigManager.save(self.config)
            print("[✓] Codex: Token refreshed successfully.")
            return True
        except Exception as e:
            print(f"[!] Codex Refresh Error: {e}")
            return False

    def _headers(self):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; codex-cli/1.0)",
        }
        if self.account_id:
            headers["ChatGPT-Account-ID"] = self.account_id
        return headers

    def _to_json_schema(self, value):
        if isinstance(value, dict):
            converted = {k: self._to_json_schema(v) for k, v in value.items()}
            if isinstance(converted.get("type"), str):
                converted["type"] = converted["type"].lower()
            return converted
        if isinstance(value, list):
            return [self._to_json_schema(v) for v in value]
        return value

    def _to_responses_tools(self, tools):
        converted = []
        for tool in tools or []:
            if tool.get("type") == "function" and "function" in tool:
                function = tool.get("function") or {}
                converted.append({
                    "type": "function",
                    "name": function.get("name", ""),
                    "description": function.get("description", ""),
                    "parameters": self._to_json_schema(function.get("parameters") or {"type": "object", "properties": {}}),
                })
            else:
                converted.append(self._to_json_schema(tool))
        return converted

    def _to_responses_content(self, content):
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return str(content)

        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                parts.append({
                    "type": "input_text",
                    "text": item.get("text", ""),
                })
            elif item.get("type") == "image_url":
                image_url = (item.get("image_url") or {}).get("url", "")
                if image_url:
                    parts.append({
                        "type": "input_image",
                        "image_url": image_url,
                    })
        return parts

    def _to_responses_input(self, messages):
        input_items = []
        for msg in messages:
            role = msg.get("role")
            if role == "system":
                continue
            if role == "tool":
                input_items.append({
                    "type": "function_call_output",
                    "call_id": msg.get("tool_call_id") or msg.get("id") or msg.get("name", ""),
                    "output": msg.get("content", ""),
                })
                continue
            if role == "assistant":
                content = msg.get("content") or ""
                if content:
                    input_items.append({"role": "assistant", "content": content})
                for call in msg.get("tool_calls") or []:
                    input_items.append({
                        "type": "function_call",
                        "call_id": call.get("id") or call.get("name", ""),
                        "name": call.get("name", ""),
                        "arguments": json.dumps(call.get("args", {}) or {}, ensure_ascii=False),
                    })
                continue
            input_items.append({
                "role": role or "user",
                "content": self._to_responses_content(msg.get("content", "")),
            })
        return input_items

    def _system_instructions(self, messages):
        return "\n\n".join(
            msg.get("content", "")
            for msg in messages
            if msg.get("role") == "system" and msg.get("content")
        )

    def _parse_stream(self, response):
        content = ""
        calls = {}
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                event = json.loads(data_str)
            except Exception:
                continue

            event_type = event.get("type", "")
            if event_type == "response.output_text.delta":
                content += event.get("delta", "")

            item = event.get("item") or event.get("output_item") or {}
            if isinstance(item, dict) and item.get("type") in {"function_call", "tool_call"}:
                call_id = item.get("call_id") or item.get("id") or str(len(calls))
                calls[str(call_id)] = {
                    "id": str(call_id),
                    "name": item.get("name") or "",
                    "arguments": item.get("arguments") or "",
                }

            if "function_call" in event_type or "tool_call" in event_type:
                call_id = (
                    event.get("call_id")
                    or event.get("item_id")
                    or event.get("output_index")
                    or event.get("id")
                    or str(len(calls))
                )
                current = calls.setdefault(str(call_id), {"id": str(call_id), "name": "", "arguments": ""})
                if event.get("name"):
                    current["name"] = event["name"]
                if event.get("arguments"):
                    current["arguments"] = event["arguments"]
                if event.get("delta"):
                    current["arguments"] += event["delta"]

            if event_type == "response.output_item.done":
                done_item = event.get("item") or {}
                if done_item.get("type") in {"function_call", "tool_call"}:
                    call_id = done_item.get("call_id") or done_item.get("id") or str(len(calls))
                    calls[str(call_id)] = {
                        "id": str(call_id),
                        "name": done_item.get("name") or "",
                        "arguments": done_item.get("arguments") or "",
                    }

        tool_calls = []
        for call in calls.values():
            if not call.get("name"):
                continue
            args_raw = call.get("arguments") or "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except Exception:
                args = {"_raw_arguments": args_raw}
            tool_calls.append({
                "id": call.get("id", ""),
                "name": call.get("name", ""),
                "args": args or {},
            })

        msg = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        return msg

    def ask(self, messages, tools=None, retry=1):
        last_err = None
        for attempt in range(retry + 1):
            try:
                return self.ask_once(messages, tools=tools)
            except urllib.error.HTTPError as e:
                if 400 <= e.code < 500 and e.code not in (401, 429):
                    raise
                last_err = e
            except Exception as e:
                last_err = e
            if attempt < retry:
                print(f"[!] Request failed ({last_err}), retrying...")
                time.sleep(2)
        raise last_err

    def ask_once(self, messages, tools=None):
        payload = {
            "model": self.model,
            "instructions": self._system_instructions(messages),
            "input": self._to_responses_input(messages),
            "store": False,
            "stream": True,
        }
        if tools:
            payload["tools"] = self._to_responses_tools(tools)
            payload["tool_choice"] = "auto"
            payload["parallel_tool_calls"] = True

        url = f"{self.base_url}/responses"

        if self.debug:
            print(f"\n[LLM Request (codex)]\n{json.dumps(payload, indent=2)}\n")

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                msg = self._parse_stream(response)
            if self.debug:
                print(f"\n[LLM Response]\n{json.dumps(msg, indent=2)}\n")
            return msg
        except urllib.error.HTTPError as e:
            if e.code == 401 and self._refresh_codex_token():
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=self._headers(),
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=60) as response:
                    return self._parse_stream(response)

            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass
            print(f"[!] Engine Error: {e}")
            if error_body:
                print(f"    Response Body: {error_body}")
            return {"role": "assistant", "content": f"Engine Error: {e}"}
        except Exception as e:
            print(f"[!] Engine Error: {e}")
            return {"role": "assistant", "content": f"Engine Error: {e}"}

    def tool_result_messages(self, tool_calls, results):
        messages = []
        for call, result in zip(tool_calls, results):
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id") or call.get("name", ""),
                "name": call.get("name", ""),
                "content": result,
            })
        return messages
