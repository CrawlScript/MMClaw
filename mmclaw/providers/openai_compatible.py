import json
import time
import urllib.error
import urllib.request

from .base import BaseProvider


class OpenAICompatibleProvider(BaseProvider):
    supports_native_tools = True

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; codex-cli/1.0)",
        }

    def _to_openai_schema(self, value):
        if isinstance(value, dict):
            converted = {k: self._to_openai_schema(v) for k, v in value.items()}
            if isinstance(converted.get("type"), str):
                converted["type"] = converted["type"].lower()
            return converted
        if isinstance(value, list):
            return [self._to_openai_schema(v) for v in value]
        return value

    def _to_openai_tools(self, tools):
        converted_tools = []
        for tool in tools or []:
            converted_tools.append(self._to_openai_schema(tool))
        return converted_tools

    def _to_provider_messages(self, messages):
        provider_messages = []
        for msg in messages:
            role = msg.get("role")
            if role == "assistant":
                out = {"role": "assistant", "content": msg.get("content") or ""}
                tool_calls = []
                for call in msg.get("tool_calls") or []:
                    tool_calls.append({
                        "id": call.get("id") or call.get("name") or "call_0",
                        "type": "function",
                        "function": {
                            "name": call.get("name", ""),
                            "arguments": json.dumps(call.get("args", {}) or {}, ensure_ascii=False),
                        },
                    })
                if tool_calls:
                    out["tool_calls"] = tool_calls
                provider_messages.append(out)
            elif role == "tool":
                provider_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id") or msg.get("id") or msg.get("name", ""),
                    "content": msg.get("content", ""),
                })
            else:
                provider_messages.append(msg)
        return provider_messages

    def _normalize_message(self, message):
        content = message.get("content") or ""
        normalized = {"role": "assistant", "content": content}
        tool_calls = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            args_raw = function.get("arguments") or "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except Exception:
                args = {"_raw_arguments": args_raw}
            tool_calls.append({
                "id": call.get("id") or function.get("name") or "",
                "name": function.get("name") or "",
                "args": args or {},
            })
        if tool_calls:
            normalized["tool_calls"] = tool_calls
        return normalized

    def _ask_blocking(self, url, payload):
        payload = {**payload, "stream": False}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
            return self._normalize_message(data["choices"][0]["message"])

    def _ask_stream(self, url, payload):
        payload = {**payload, "stream": True}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        content = ""
        calls_by_index = {}
        with urllib.request.urlopen(req, timeout=60) as response:
            for line in response:
                line = line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data["choices"][0].get("delta") or {}
                    if delta.get("content"):
                        content += delta["content"]
                    for call_delta in delta.get("tool_calls") or []:
                        idx = call_delta.get("index", 0)
                        current = calls_by_index.setdefault(idx, {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        })
                        if call_delta.get("id"):
                            current["id"] += call_delta["id"]
                        function_delta = call_delta.get("function") or {}
                        if function_delta.get("name"):
                            current["function"]["name"] += function_delta["name"]
                        if function_delta.get("arguments"):
                            current["function"]["arguments"] += function_delta["arguments"]
                except Exception:
                    continue

        message = {"role": "assistant", "content": content}
        if calls_by_index:
            message["tool_calls"] = [calls_by_index[i] for i in sorted(calls_by_index)]
        return self._normalize_message(message)

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
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": self._to_provider_messages(messages),
        }
        if tools:
            payload["tools"] = self._to_openai_tools(tools)
            payload["tool_choice"] = "auto"
        if self.engine_type in ("minimax_io", "minimax_cn"):
            payload["reasoning_split"] = True

        if self.debug:
            print(f"\n[LLM Request ({self.engine_type})]\n{json.dumps(payload, indent=2)}\n")

        try:
            msg = self._ask_stream(url, payload) if self.stream else self._ask_blocking(url, payload)
            if self.debug:
                print(f"\n[LLM Response]\n{json.dumps(msg, indent=2)}\n")
            return msg
        except Exception as e:
            print(f"[!] Engine Error: {e}")
            error_msg = f"Engine Error: {e}"
            if isinstance(e, urllib.error.HTTPError):
                try:
                    error_body = e.read().decode("utf-8")
                    print(f"    Response Body: {error_body}")
                    if "vision" in error_body.lower() or "image" in error_body.lower():
                        error_msg = (
                            f"❌ The current model ({self.model}) does not support images. "
                            "Please use 'mmclaw config' to choose a vision-capable model like 'gpt-4o-mini' or 'claude-3.5-sonnet'."
                        )
                except Exception:
                    pass
            return {"role": "assistant", "content": error_msg}

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
