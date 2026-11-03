#!/usr/bin/env python3
"""Web Search CLI — used by MMClaw agent to perform web searches."""
import argparse
import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path

import os
_WORKSPACE = Path(os.environ.get("MMCLAW_WORKSPACE", str(Path.home() / ".mmclaw")))
CONFIG_FILE = _WORKSPACE / "skill-config" / "web-search.json"


def load_config():
    if not CONFIG_FILE.exists():
        print("NOT_CONFIGURED")
        sys.exit(1)
    try:
        cfg = json.loads(CONFIG_FILE.read_text())
    except Exception:
        print("INVALID_CONFIG")
        sys.exit(1)
    provider = cfg.get("provider", "").strip()
    if not provider:
        print("NO_PROVIDER")
        sys.exit(1)
    api_key = cfg.get(provider, {}).get("api_key", "").strip()
    if not api_key and provider not in KEYLESS_PROVIDERS:
        print(f"NO_API_KEY:{provider}")
        sys.exit(1)
    return provider, api_key


ALL_PROVIDERS = ("serper", "serpapi", "brave", "tavily", "keenable")
# Providers that work without an API key (a key, if saved, is still used).
KEYLESS_PROVIDERS = ("keenable",)
KEENABLE_SNIPPET_MAX_CHARS = 1000


def save_config(provider: str, api_key: str):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config = {"provider": provider}
    for p in ALL_PROVIDERS:
        config[p] = {"api_key": api_key if p == provider else ""}
    # preserve existing keys for other providers
    if CONFIG_FILE.exists():
        try:
            existing = json.loads(CONFIG_FILE.read_text())
            for p in ALL_PROVIDERS:
                if p != provider and existing.get(p, {}).get("api_key"):
                    config[p]["api_key"] = existing[p]["api_key"]
        except Exception:
            pass
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    print(json.dumps({"ok": True, "provider": provider}))


def serper_search(query: str, api_key: str, count: int, **_) -> list:
    body = json.dumps({"q": query, "num": count}).encode()
    req = urllib.request.Request(
        "https://google.serper.dev/search",
        data=body,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        data = json.loads(res.read())
    return [
        {"title": r.get("title"), "url": r.get("link"), "snippet": r.get("snippet")}
        for r in data.get("organic", [])
    ]


def serpapi_search(query: str, api_key: str, count: int, **_) -> list:
    params = urllib.parse.urlencode({"q": query, "num": count, "api_key": api_key, "engine": "google"})
    req = urllib.request.Request(f"https://serpapi.com/search?{params}")
    with urllib.request.urlopen(req, timeout=10) as res:
        data = json.loads(res.read())
    return [
        {"title": r.get("title"), "url": r.get("link"), "snippet": r.get("snippet")}
        for r in data.get("organic_results", [])
    ]


def brave_search(query: str, api_key: str, count: int, **_) -> list:
    params = urllib.parse.urlencode({"q": query, "count": count})
    req = urllib.request.Request(
        f"https://api.search.brave.com/res/v1/web/search?{params}",
        headers={"Accept": "application/json", "X-Subscription-Token": api_key},
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        data = json.loads(res.read())
    return [
        {"title": r.get("title"), "url": r.get("url"), "snippet": r.get("description")}
        for r in data.get("web", {}).get("results", [])
    ]


def tavily_search(
    query: str,
    api_key: str,
    count: int,
    depth: str = "basic",
    topic: str = "general",
    time_range: str = None,
    include_domains: list = None,
    exclude_domains: list = None,
    raw_content: bool = False,
    **_,
) -> list:
    payload = {
        "api_key":             api_key,
        "query":               query,
        "max_results":         count,
        "search_depth":        depth,
        "topic":               topic,
        "include_raw_content": raw_content,
    }
    if time_range:
        payload["time_range"] = time_range
    if include_domains:
        payload["include_domains"] = include_domains
    if exclude_domains:
        payload["exclude_domains"] = exclude_domains

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as res:
        data = json.loads(res.read())
    return [
        {
            "title":   r.get("title"),
            "url":     r.get("url"),
            "snippet": r.get("content"),
            "score":   r.get("score"),
            **({"raw_content": r.get("raw_content")} if raw_content else {}),
        }
        for r in data.get("results", [])
    ]


def keenable_search(query: str, api_key: str, count: int, **_) -> list:
    headers = {"Content-Type": "application/json", "X-Keenable-Title": "MMClaw"}
    url = "https://api.keenable.ai/v1/search/public"
    if api_key:
        headers["X-API-Key"] = api_key
        url = "https://api.keenable.ai/v1/search"
    body = json.dumps({"query": query, "max_results": count}).encode()
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as res:
        data = json.loads(res.read())
    return [
        {
            "title":   r.get("title"),
            "url":     r.get("url"),
            "snippet": r.get("description") or (r.get("snippet") or "")[:KEENABLE_SNIPPET_MAX_CHARS],
        }
        for r in data.get("results", [])
        if r.get("url")
    ]


PROVIDERS = {
    "serper":  serper_search,
    "serpapi": serpapi_search,
    "brave":   brave_search,
    "tavily":  tavily_search,
    "keenable": keenable_search,
}


def cmd_search(args):
    provider, api_key = load_config()
    fn = PROVIDERS.get(provider)
    if not fn:
        print(f"UNKNOWN_PROVIDER:{provider}")
        sys.exit(1)
    try:
        results = fn(
            args.query,
            api_key,
            args.count,
            depth=args.depth,
            topic=args.topic,
            time_range=args.time_range,
            include_domains=args.include_domains.split(",") if args.include_domains else None,
            exclude_domains=args.exclude_domains.split(",") if args.exclude_domains else None,
            raw_content=args.raw_content,
        )
        print(json.dumps(results, ensure_ascii=False, indent=2))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        sys.exit(1)
    except TimeoutError:
        print("TIMEOUT")
        sys.exit(1)


def cmd_setup(args):
    save_config(args.provider, args.api_key)


def cmd_status(args):
    if not CONFIG_FILE.exists():
        print("NOT_CONFIGURED")
        sys.exit(1)
    try:
        cfg = json.loads(CONFIG_FILE.read_text())
    except Exception:
        print("INVALID_CONFIG")
        sys.exit(1)
    provider = cfg.get("provider", "").strip()
    if not provider:
        print("NO_PROVIDER")
        sys.exit(1)
    api_key = cfg.get(provider, {}).get("api_key", "").strip()
    masked = (api_key[:8] + "...") if api_key else ""
    configured = bool(api_key) or provider in KEYLESS_PROVIDERS
    print(json.dumps({"provider": provider, "api_key_preview": masked, "configured": configured}))


def main():
    parser = argparse.ArgumentParser(prog="web_search")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="Run a web search")
    p.add_argument("query", help="Search query")
    p.add_argument("--count", type=int, default=5, help="Number of results (default: 5)")
    p.add_argument("--depth", default="basic",
                   choices=["ultra-fast", "fast", "basic", "advanced"],
                   help="Search depth — Tavily only (default: basic)")
    p.add_argument("--topic", default="general", choices=["general", "news"],
                   help="Topic filter — Tavily only (default: general)")
    p.add_argument("--time-range", dest="time_range", default=None,
                   choices=["day", "week", "month", "year"],
                   help="Time range — Tavily only")
    p.add_argument("--include-domains", dest="include_domains", default=None,
                   help="Comma-separated domains to include — Tavily only")
    p.add_argument("--exclude-domains", dest="exclude_domains", default=None,
                   help="Comma-separated domains to exclude — Tavily only")
    p.add_argument("--raw-content", dest="raw_content", action="store_true",
                   help="Include full page content — Tavily only")

    p = sub.add_parser("setup", help="Save provider and API key")
    p.add_argument("provider", choices=list(ALL_PROVIDERS))
    p.add_argument("api_key", nargs="?", default="",
                   help="API key (optional for keenable)")

    sub.add_parser("status", help="Show current configuration")

    args = parser.parse_args()
    {"search": cmd_search, "setup": cmd_setup, "status": cmd_status}[args.command](args)


if __name__ == "__main__":
    main()
