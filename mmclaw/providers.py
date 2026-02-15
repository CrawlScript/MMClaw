import json
import urllib.request
import urllib.error
import base64
import io

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
        self.engine_type = config["engine_type"] # Raises KeyError if missing
        engine_config = config["engines"][self.engine_type]
        
        self.api_key = engine_config["api_key"]
        self.base_url = engine_config["base_url"].rstrip('/')
        self.model = engine_config["model"]
        self.debug = config.get("debug", False)

    def ask(self, messages, tools=None):
        if self.engine_type in ["openai", "google", "deepseek", "openrouter", "openai_compatible"]:
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