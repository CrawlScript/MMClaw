import json
import urllib.request
import urllib.error

class Engine(object):
    def __init__(self, config):
        self.api_key = config["api_key"]
        self.base_url = config["base_url"].rstrip('/')
        self.model = config["model"]
        self.debug = config.get("debug", False)

    def ask(self, messages, tools=None):
        payload = {
            "model": self.model, 
            "messages": messages, 
            "stream": False
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}", 
                "Content-Type": "application/json"
            },
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                msg = res_data["choices"][0]["message"]
                if self.debug:
                    print(f"\n[LLM Response]\n{json.dumps(msg, indent=2)}\n")
                return msg
        except Exception as e:
            # For a tutorial, we return a simple error message in message format
            return {"role": "assistant", "content": f"Engine Error: {e}"}