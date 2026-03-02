---
name: web-search
description: Search the web using a configured search provider. Use when the user explicitly asks to search, look up current information, or needs real-time data such as news, prices, or recent events.
metadata:
  { "mmclaw": { "emoji": "🔍", "os": ["linux", "darwin", "win32"], "requires": { "bins": ["python3"] } } }
---
# Web Search Skill

Use this skill when the user explicitly asks to search the web or needs real-time information. Trigger phrases: "search", "look up", "latest", "current", "today", "find online", "what's the news on".

Do NOT trigger this skill proactively. Only search when the user clearly requests it or the question cannot be answered from existing knowledge.

**Note**: "provider" here refers to the **search provider** (Serper, Brave, SerpApi), not the LLM provider configured elsewhere in your setup. These are independent settings.

**IMPORTANT — provider lock-in**: Only use the search provider set in the `provider` field of the config file below. Do NOT fall back to another provider silently. If the configured provider fails or has no key, inform the user and stop.

## Configuration

All settings are stored at `~/.mmclaw/skill-config/web-search.json`:

```json
{
  "provider": "serper",
  "serper":  { "api_key": "" },
  "brave":   { "api_key": "" },
  "serpapi": { "api_key": "" }
}
```

### If the config file does not exist

Do NOT proceed with any search. Instead:

1. Show the user the available search providers and recommend **Serper** as the first choice. Translate the provider descriptions below into the language the user has been writing in before presenting them.

**⭐ 1. Serper** (recommended) — https://serper.dev
- Free: 2,500 queries/month, no credit card required
- Pro: Fast, Google results, easiest to get started
- Con: Fewer queries than paid plans

**2. SerpApi** — https://serpapi.com
- Free: 250 queries/month, no credit card required
- Pro: Supports Google, Bing, DuckDuckGo and more
- Con: Free tier is very limited (250/month)

**3. Brave** — https://brave.com/search/api/
- Free: None, paid only
- Pro: Independent search index, not reliant on Google
- Con: Requires credit card, no free tier

2. Ask the user which provider they want to use. If unsure, recommend Serper.

3. Ask the user to sign up at the provider's site and get their API key. Then instruct them to set it up using one of the following methods:

**Method 1 (recommended)** — Reply directly in chat with the service name and key, MMClaw will set it up automatically:
```
provider: serper
api_key: YOUR_KEY_HERE
```

**Method 2 (manual fallback)** — If Method 1 fails or the LLM does not support reading sensitive input, create the config file manually at `~/.mmclaw/skill-config/web-search.json` with the following content (replace placeholders, leave unused keys as empty strings):
```json
{
  "provider": "<chosen_provider>",
  "serper":  { "api_key": "<your_serper_key_or_empty>" },
  "brave":   { "api_key": "<your_brave_key_or_empty>" },
  "serpapi": { "api_key": "<your_serpapi_key_or_empty>" }
}
```

4. Once the key is provided via Method 1, save the config file:

```python
import json, os

provider = "<chosen_provider>"  # "serper", "brave", or "serpapi"
api_key  = "<key_provided_by_user>"

config = {
    "provider": provider,
    "serper":  {"api_key": api_key if provider == "serper"  else ""},
    "brave":   {"api_key": api_key if provider == "brave"   else ""},
    "serpapi": {"api_key": api_key if provider == "serpapi" else ""},
}
path = os.path.expanduser("~/.mmclaw/skill-config/web-search.json")
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w") as f:
    json.dump(config, f, indent=2)
print(f"Config saved to {path}")
```

### If the config file exists but `provider` is empty or missing

Ask the user to choose a provider. Do NOT guess or default to any.

---

## Usage

### Step 1 — Load config and resolve provider

```python
import json, os

path = os.path.expanduser("~/.mmclaw/skill-config/web-search.json")
config = json.load(open(path))
provider = config.get("provider", "").strip()
if not provider:
    raise ValueError("No provider set in web-search.json. Please set a provider.")
api_key = config.get(provider, {}).get("api_key", "").strip()
if not api_key:
    raise ValueError(f"No API key found for provider '{provider}' in web-search.json.")
print(f"Provider: {provider}")
print(f"Key: {api_key[:8]}...")
```

### Step 2 — Run the search

Use only the block matching the configured provider.

#### Serper

```python
import urllib.request, json

def serper_search(query, api_key, count=5):
    body = json.dumps({"q": query, "num": count}).encode()
    req = urllib.request.Request(
        "https://google.serper.dev/search",
        data=body,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        data = json.loads(res.read())
    for r in data.get("organic", []):
        print(f"Title: {r.get('title')}")
        print(f"URL:   {r.get('link')}")
        print(f"Desc:  {r.get('snippet')}")
        print()

serper_search("<USER_QUERY>", api_key)
```

#### SerpApi

```python
import urllib.request, urllib.parse, json

def serpapi_search(query, api_key, count=5):
    params = urllib.parse.urlencode({"q": query, "num": count, "api_key": api_key, "engine": "google"})
    req = urllib.request.Request(f"https://serpapi.com/search?{params}")
    with urllib.request.urlopen(req, timeout=10) as res:
        data = json.loads(res.read())
    for r in data.get("organic_results", []):
        print(f"Title: {r.get('title')}")
        print(f"URL:   {r.get('link')}")
        print(f"Desc:  {r.get('snippet')}")
        print()

serpapi_search("<USER_QUERY>", api_key)
```

#### Brave

```python
import urllib.request, urllib.parse, json

def brave_search(query, api_key, count=5):
    params = urllib.parse.urlencode({"q": query, "count": count})
    req = urllib.request.Request(
        f"https://api.search.brave.com/res/v1/web/search?{params}",
        headers={"Accept": "application/json", "X-Subscription-Token": api_key},
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        data = json.loads(res.read())
    for r in data.get("web", {}).get("results", []):
        print(f"Title: {r.get('title')}")
        print(f"URL:   {r.get('url')}")
        print(f"Desc:  {r.get('description')}")
        print()

brave_search("<USER_QUERY>", api_key)
```

Replace `<USER_QUERY>` with the user's actual search query.

---

## IMPORTANT — always report results verbatim

After Step 2, you MUST present Title, URL, and key points from the results directly in your reply. If a result contains a specific version number, date, or fact, quote it exactly — do NOT paraphrase with vague terms like "recent" or "the latest version". Do NOT tell the user to check the output themselves.

---

## Error Handling

| Error | Action |
|-------|--------|
| Config file not found | Show provider list, ask user to choose, then run setup |
| `provider` empty or missing | Ask user to set a provider — do NOT default to any |
| `401 Unauthorized` | API key is invalid — ask the user to re-enter it via Method 1 or Method 2 |
| `429 Too Many Requests` | Monthly quota exhausted — inform the user, suggest upgrading or switching provider |
| Network timeout | Inform the user, answer from existing knowledge, note it may not be current |

On any error, do NOT retry automatically and do NOT switch providers silently.

---

## Notes

- To switch providers, update the `provider` field in `~/.mmclaw/skill-config/web-search.json`
- Multiple API keys can coexist in the config — only the active `provider` is used
- Serper and SerpApi free tiers reset monthly