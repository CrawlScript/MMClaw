import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .base import BaseProvider


class VertexAIProvider(BaseProvider):
    supports_native_tools = True

    def _to_gemini_content_parts(self, content):
        if isinstance(content, str):
            return [{"text": content}]
        if not isinstance(content, list):
            return [{"text": str(content)}]

        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                parts.append({"text": item.get("text", "")})
            elif item.get("type") == "image_url":
                image_url = (item.get("image_url") or {}).get("url", "")
                if image_url.startswith("data:") and "," in image_url:
                    header, data = image_url.split(",", 1)
                    mime_type = header[5:].split(";", 1)[0] or "image/jpeg"
                    parts.append({
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": data,
                        }
                    })
                elif image_url:
                    parts.append({"fileData": {"fileUri": image_url}})
        return parts

    def _to_gemini_contents(self, messages):
        system_instruction = None
        contents = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                text = content if isinstance(content, str) else str(content)
                system_instruction = {"parts": [{"text": text}]}
                continue

            if role == "tool":
                name = msg.get("name", "")
                response = msg.get("response")
                if response is None:
                    response = {"result": content}
                contents.append({
                    "role": "user",
                    "parts": [{"functionResponse": {"name": name, "response": response}}],
                })
                continue

            parts = []
            if content:
                parts.extend(self._to_gemini_content_parts(content))

            for call in msg.get("tool_calls") or []:
                function_call_part = {
                    "functionCall": {
                        "name": call.get("name", ""),
                        "args": call.get("args", {}) or {},
                    }
                }
                thought_signature = call.get("thoughtSignature") or call.get("thought_signature")
                if thought_signature:
                    function_call_part["thoughtSignature"] = thought_signature
                parts.append(function_call_part)

            if not parts:
                parts = [{"text": ""}]

            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": parts})
        return system_instruction, contents

    def _to_gemini_tools(self, tools):
        declarations = []
        for tool in tools or []:
            if tool.get("type") == "function":
                function = tool.get("function") or {}
                declarations.append({
                    "name": function.get("name", ""),
                    "description": function.get("description", ""),
                    "parameters": function.get("parameters") or {"type": "OBJECT", "properties": {}},
                })
            elif "name" in tool:
                declarations.append({
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters") or {"type": "OBJECT", "properties": {}},
                })
            elif "functionDeclarations" in tool:
                declarations.extend(tool.get("functionDeclarations") or [])

        if not declarations:
            return None
        return [{"functionDeclarations": declarations}]

    def _extract_parts(self, payload):
        candidates = payload.get("candidates") or []
        if not candidates:
            return []
        return (candidates[0].get("content") or {}).get("parts") or []

    def _parts_to_message(self, parts):
        content = ""
        tool_calls = []
        for part in parts:
            if "text" in part:
                content += part["text"]
            elif "functionCall" in part:
                call = part["functionCall"] or {}
                tool_call = {
                    "id": call.get("name", ""),
                    "name": call.get("name", ""),
                    "args": call.get("args", {}) or {},
                }
                thought_signature = part.get("thoughtSignature") or part.get("thought_signature")
                if thought_signature:
                    tool_call["thoughtSignature"] = thought_signature
                tool_calls.append(tool_call)
        msg = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        return msg

    def _build_body(self, messages, tools=None):
        system_instruction, contents = self._to_gemini_contents(messages)
        body = {"contents": contents}
        if system_instruction:
            body["systemInstruction"] = system_instruction

        gemini_tools = self._to_gemini_tools(tools)
        if gemini_tools:
            body["tools"] = gemini_tools
            body["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
        return body

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
        body = self._build_body(messages, tools=tools)
        key_param = urllib.parse.quote(self.api_key, safe="")

        if self.stream:
            url = f"{self.base_url}/models/{self.model}:streamGenerateContent?alt=sse&key={key_param}"
        else:
            url = f"{self.base_url}/models/{self.model}:generateContent?key={key_param}"

        if self.debug:
            print(f"\n[LLM Request (vertex_ai)] url={url}\n{json.dumps(body, indent=2)}\n")

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            parts = []
            with urllib.request.urlopen(req, timeout=120) as response:
                if self.stream:
                    for line in response:
                        line_str = line.decode("utf-8").strip()
                        if not line_str.startswith("data: "):
                            continue
                        data_str = line_str[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            parts.extend(self._extract_parts(chunk))
                        except Exception:
                            continue
                else:
                    res_data = json.loads(response.read().decode("utf-8"))
                    parts = self._extract_parts(res_data)

            msg = self._parts_to_message(parts)
            if self.debug:
                print(f"\n[LLM Response (vertex_ai)]\n{json.dumps(msg, indent=2)}\n")
            return msg
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass
            print(f"[!] Engine Error: {e}")
            if error_body:
                print(f"    Response Body: {error_body}")
            return {"role": "assistant", "content": f"Engine Error: {e}"}

    def tool_result_messages(self, tool_calls, results):
        messages = []
        for call, result in zip(tool_calls, results):
            messages.append({
                "role": "tool",
                "name": call.get("name", ""),
                "content": result,
                "response": {"result": result},
            })
        return messages
