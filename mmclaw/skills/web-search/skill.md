---
name: web-search
description: Search the web using a configured search provider. Use when the user explicitly asks to search, look up current information, or needs real-time data such as news, prices, or recent events.
metadata:
  { "mmclaw": { "emoji": "🔍", "os": ["linux", "darwin", "win32"], "requires": { "bins": ["python3"] } } }
---
# Web Search Skill

Use this skill when the user explicitly asks to search the web or needs real-time information. Trigger phrases: "search", "look up", "latest", "current", "today", "find online", "what's the news on".

Do NOT trigger this skill proactively. Only search when the user clearly requests it or the question cannot be answered from existing knowledge.

**Note**: "provider" here refers to the **search provider** (Tavily, Serper, SerpApi, Brave), not the LLM provider configured elsewhere in your setup. These are independent settings.

**IMPORTANT — provider lock-in**: Only use the search provider set in the config. Do NOT fall back to another provider silently. If the configured provider fails or has no key, inform the user and stop.

## CLI Tool

All operations use:
```
python $MMCLAW_WORKSPACE/skills/web-search/web_search.py <command> [args]
```

## Preconditions

Run `status` first. Handle output codes:

| Output | Action |
|--------|--------|
| `NOT_CONFIGURED` | No config file — show provider list below, ask user to choose, then run setup |
| `INVALID_CONFIG` | Config file is corrupt — ask user to re-run setup |
| `NO_PROVIDER` | Config exists but no provider set — ask user to choose a provider |
| `NO_API_KEY:<provider>` | Provider set but key missing — ask user for their API key |
| JSON with `"configured": true` | Ready — proceed with search |

```
python $MMCLAW_WORKSPACE/skills/web-search/web_search.py status
```

---

## Commands

### Check Status
```
python $MMCLAW_WORKSPACE/skills/web-search/web_search.py status
```

### Search
```
python $MMCLAW_WORKSPACE/skills/web-search/web_search.py search "<query>" [--count N] [--depth <depth>] [--topic <topic>] [--time-range <range>] [--include-domains <domains>] [--exclude-domains <domains>] [--raw-content]
```
Returns a JSON array of `{title, url, snippet}` objects (Tavily also includes `score` and optionally `raw_content`). Default count: 5.

**Tavily-only options** (ignored by other providers):

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--depth` | `ultra-fast`, `fast`, `basic`, `advanced` | `basic` | Search depth / relevance trade-off |
| `--topic` | `general`, `news` | `general` | Topic filter |
| `--time-range` | `day`, `week`, `month`, `year` | — | Restrict to recent results |
| `--include-domains` | comma-separated | — | Only return results from these domains |
| `--exclude-domains` | comma-separated | — | Exclude results from these domains |
| `--raw-content` | flag | false | Include full page content in results |

**Tips for Tavily:**
- Keep queries under 400 characters — write search terms, not prompts
- Use `--depth advanced` when precision matters (research); `--depth fast` when latency matters
- Use `--include-domains` to focus on trusted sources
- Use `--topic news` + `--time-range week` for current events

**IMPORTANT — always report results verbatim**: Present Title, URL, and key points from the results directly in your reply. If a result contains a specific version number, date, or fact, quote it exactly — do NOT paraphrase with vague terms like "recent" or "the latest version". Do NOT tell the user to check the output themselves.

### Setup (save provider + API key)
```
python $MMCLAW_WORKSPACE/skills/web-search/web_search.py setup <provider> <api_key>
```
`provider` must be one of: `tavily`, `serper`, `serpapi`, `brave`, `keenable`. The API key is optional for `keenable` (`setup keenable` works without one).

---

## Provider Setup Flow

If not configured, show this list and ask the user to choose. Translate descriptions into the language the user has been writing in.

**⭐ 1. Tavily** (recommended) — https://tavily.com
- Free: 1,000 queries/month, no credit card required
- Pro: LLM-optimized results with relevance scores, depth control, topic/time filters, raw page content

**2. Serper** — https://serper.dev
- Free: 2,500 queries lifetime (one-time, does not reset), no credit card required
- Pro: Fast, Google results, easiest to get started
- Con: Fewer advanced filtering options

**3. SerpApi** — https://serpapi.com
- Free: 250 queries/month, no credit card required
- Pro: Supports Google, Bing, DuckDuckGo and more
- Con: Free tier is very limited (250/month)

**4. Brave** — https://brave.com/search/api/
- Free: None, paid only
- Pro: Independent search index, not reliant on Google
- Con: Requires credit card, no free tier

**5. Keenable** — https://keenable.ai
- Free: works with no API key and no sign-up (`setup keenable`)
- Pro: Zero setup; an optional API key raises rate limits
- Con: No Tavily-style depth/topic/domain filters

Once the user chooses a provider and shares their API key, run:
```
python $MMCLAW_WORKSPACE/skills/web-search/web_search.py setup <provider> <api_key>
```

---

## Error Handling

| Error | Action |
|-------|--------|
| `NOT_CONFIGURED` | Show provider list, ask user to choose, then run setup |
| `NO_PROVIDER` | Ask user to set a provider — do NOT default to any |
| `HTTP 401` | API key is invalid — ask the user to re-enter it and re-run setup |
| `HTTP 429` | Monthly quota exhausted — inform the user, suggest upgrading or switching provider |
| `TIMEOUT` | Inform the user, answer from existing knowledge, note it may not be current |

On any error, do NOT retry automatically and do NOT switch providers silently.

---

## Notes

- To switch providers, re-run `setup` with the new provider and key
- Multiple API keys can coexist in the config — only the active provider is used
- Tavily and SerpApi free tiers reset monthly; Serper's free quota is a one-time lifetime allocation (does not reset)
