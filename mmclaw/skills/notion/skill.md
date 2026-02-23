---
name: notion
description: Notion API for creating and managing pages, databases, and blocks.
homepage: https://developers.notion.com
metadata:
  { "mmclaw": { "emoji": "📝", "requires": { "config": ["skill-config/notion.json"] } } }
---

# Notion Skill (MMClaw)

Use the Notion API to create/read/update pages, databases, and blocks.

## Config File

```
~/.mmclaw/skill-config/notion.json
```

```json
{
  "auth": {
    "api_key": "ntn_your_key_here"
  },
  "defaults": {
    "database_name": "MMClaw"
  }
}
```

- `api_key`: your Notion integration token (starts with `ntn_` or `secret_`)
- `defaults.database_name`: the name of the database where pages are created when the user doesn't specify a location

## Preconditions

**Before any API call**, run this check:

```bash
CONFIG_FILE="$HOME/.mmclaw/skill-config/notion.json"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "NOT_CONFIGURED"
  exit 1
fi

NOTION_KEY=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['auth']['api_key'])" 2>/dev/null)
DEFAULT_DB_NAME=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('defaults', {}).get('database_name', ''))" 2>/dev/null)

if [ -z "$NOTION_KEY" ] || [[ "$NOTION_KEY" != ntn_* && "$NOTION_KEY" != secret_* ]]; then
  echo "INVALID_KEY"
  exit 1
fi

if [ -z "$DEFAULT_DB_NAME" ]; then
  echo "NO_DEFAULT_DB"
  exit 1
fi
```

**If `NOT_CONFIGURED`**, stop and return:

> ⚠️ Notion is not configured.
>
> Please create `~/.mmclaw/skill-config/notion.json`:
> ```json
> {
>   "auth": {
>     "api_key": "ntn_your_key_here"
>   },
>   "defaults": {
>     "database_name": "MMClaw"
>   }
> }
> ```
>
> **Step 1 — Get an API key:**
> 1. Go to https://notion.so/my-integrations
> 2. Click "New integration", give it a name (e.g. "MMClaw")
> 3. Copy the token (starts with `ntn_` or `secret_`)
> 4. Paste it as `auth.api_key`
>
> **Step 2 — Create a default database:**
> 1. In Notion, create a new database (e.g. name it "MMClaw")
> 2. Set `defaults.database_name` in config to the database name (e.g. `"MMClaw"`)
>
> **Step 3 — Grant Content Access:**
> 1. Go to https://notion.so/my-integrations → select your integration
> 2. Click "Edit Integration" → "Content Access" → "Edit Access"
> 3. Under "Private", check the database you just created

**If `INVALID_KEY`**, stop and return:

> ⚠️ Notion API key looks invalid.
>
> The key in `~/.mmclaw/skill-config/notion.json` should start with `ntn_` or `secret_`.

**If `NO_DEFAULT_DB`**, do NOT ask the user for a UUID and do NOT loop asking for the name repeatedly. Instead:

1. If the user has already mentioned a database name in the conversation, use that. Otherwise ask once: "Which Notion database should I use as default?"
2. Search for the name:

```bash
DB_NAME="USER_PROVIDED_NAME"

# Use empty query to list all accessible data sources, then match by name
SEARCH_RESULT=$(curl -s -X POST "https://api.notion.com/v1/search" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{"filter": {"value": "data_source", "property": "object"}}')

FOUND_ID=$(echo "$SEARCH_RESULT" | python3 -c "
import json, sys
target = '$DB_NAME'.lower()
results = json.load(sys.stdin).get('results', [])
match = next((r['id'] for r in results if (r.get('title') or [{}])[0].get('plain_text','').lower() == target), '')
print(match)
")
```

3. If `FOUND_ID` is not empty → save the name to config:

```bash
python3 << 'EOF'
import json, os
path = os.path.expanduser("~/.mmclaw/skill-config/notion.json")
with open(path, encoding="utf-8") as f:
    config = json.load(f)
config.setdefault("defaults", {})["database_name"] = "$DB_NAME"
with open(path, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
print("Saved database_name:", config["defaults"]["database_name"])
EOF
```

4. If search returns empty → stop and return:

> ⚠️ Could not find that database. This is likely a permissions issue.
>
> Please grant Content Access first:
> 1. Go to https://notion.so/my-integrations → select your MMClaw integration
> 2. Click "Edit Integration" → "Content Access" → "Edit Access" → check the database
>
> Then tell me the database name again.

## API Basics

```bash
NOTION_KEY=$(python3 -c "import json; print(json.load(open('$HOME/.mmclaw/skill-config/notion.json'))['auth']['api_key'])")
DEFAULT_DB_NAME=$(python3 -c "import json; print(json.load(open('$HOME/.mmclaw/skill-config/notion.json'))['defaults']['database_name'])")
```

> **Important:** In API version `2025-09-03`, most database operations require a `data_source_id`, not the `database_id`. Always run the Discovery step first when working with a database.

## Discovery: Getting the data_source_id

Before querying or writing to a database, resolve the name to a `data_source_id`.

**IMPORTANT: Always use an empty query (`{}` body with only filter) to list ALL databases, then match by name in Python. Never pass the database name as `query` parameter — Notion's search is fuzzy and unreliable for exact matching.**

```bash
# List ALL accessible data sources (empty query = return all)
SEARCH_RESULT=$(curl -s -X POST "https://api.notion.com/v1/search" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{"filter": {"value": "data_source", "property": "object"}}')

# Match by name (case-insensitive) — note: no quotes around EOF so $DEFAULT_DB_NAME expands
DATA_SOURCE_ID=$(echo "$SEARCH_RESULT" | python3 -c "
import json, sys
target = '$DEFAULT_DB_NAME'.lower()
results = json.load(sys.stdin).get('results', [])
match = next((r['id'] for r in results if (r.get('title') or [{}])[0].get('plain_text','').lower() == target), '')
print(match)
")
```

> If `DATA_SOURCE_ID` is still empty after the above, print all available names for debugging:
> ```bash
> echo "$SEARCH_RESULT" | python3 -c "
> import json, sys
> for r in json.load(sys.stdin).get('results', []):
>     print(r.get('title', [{}])[0].get('plain_text','(untitled)'), '->', r['id'])
> "
> ```

If `DATA_SOURCE_ID` is empty → the database is not accessible. See the permissions guidance in the Default Parent Behavior section.

Use `DATA_SOURCE_ID` for all subsequent calls.

## Default Parent Behavior

**If the user does NOT specify a location:**
1. Get `data_source_id` from the default database (Discovery step above)
2. Create a new page in that database, title = `MMClaw-{timestamp}` (format: `YYYYMMDD-HHMMSS`)
3. Add the user's content as blocks inside that page
4. Do NOT create a child page or search for another database

```bash
TIMESTAMP=$(date -u +"%Y%m%d-%H%M%S")
DATA_SOURCE_ID="..."  # from Discovery step

# Step 1: create the page
PAGE=$(curl -s -X POST "https://api.notion.com/v1/pages" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "parent": {"type": "data_source_id", "data_source_id": "'"$DATA_SOURCE_ID"'"},
    "properties": {
      "Name": {"title": [{"text": {"content": "MMClaw-'"$TIMESTAMP"'"}}]}
    }
  }')

PAGE_ID=$(echo $PAGE | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

# Step 2: append user content as blocks
curl -X PATCH "https://api.notion.com/v1/blocks/$PAGE_ID/children" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "children": [
      {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "..."}}]}}
    ]
  }'
```

**If the user specifies a location** (e.g. "put it in my Tasks database"):
1. Search for the database by name
2. If found and accessible → get its `data_source_id` and use it as parent
3. If found but returns 403 → stop and return the access error message below

**If search returns empty results** (no databases found at all), this almost always means the integration has no Content Access granted — not that the database doesn't exist. Stop and return:

> ⚠️ MMClaw cannot find any Notion databases. This is likely a permissions issue, not a missing database.
>
> Please grant Content Access:
> 1. Go to https://notion.so/my-integrations → select your MMClaw integration
> 2. Click "Edit Integration" → "Content Access" → "Edit Access"
> 3. Under "Private", check the database you want MMClaw to access
>
> After completing the above, tell me the database name again.

**If a specific database returns 403**, stop and return:

> ⚠️ MMClaw doesn't have access to that database.
>
> To grant access:
> 1. Go to https://notion.so/my-integrations → select your MMClaw integration
> 2. Click "Edit Integration" → "Content Access" → "Edit Access" → check the database

**Never ask the user to provide raw UUIDs or find IDs from URLs.**

## Operations

### Search

```bash
curl -X POST "https://api.notion.com/v1/search" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{"query": "database name"}'
```

Filter by data source only:

```bash
-d '{"query": "name", "filter": {"value": "data_source", "property": "object"}}'
```

### Pages

**Get a page:**

```bash
curl "https://api.notion.com/v1/pages/{page_id}" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03"
```

**Create a page in a database:**

```bash
curl -X POST "https://api.notion.com/v1/pages" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "parent": {"type": "data_source_id", "data_source_id": "xxx"},
    "properties": {
      "Name": {"title": [{"text": {"content": "Page Title"}}]}
    }
  }'
```

**Update page properties:**

```bash
curl -X PATCH "https://api.notion.com/v1/pages/{page_id}" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{"properties": {"Status": {"select": {"name": "Done"}}}}'
```

### Databases

**Query a data source:**

```bash
curl -X POST "https://api.notion.com/v1/data_sources/{data_source_id}/query" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {"property": "Status", "select": {"equals": "Active"}},
    "sorts": [{"property": "Date", "direction": "descending"}]
  }'
```

**Retrieve a data source** (schema/properties):

```bash
curl "https://api.notion.com/v1/data_sources/{data_source_id}" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03"
```

**Create a database:**

```bash
curl -X POST "https://api.notion.com/v1/databases" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "parent": {"page_id": "xxx"},
    "is_inline": true,
    "title": [{"text": {"content": "My Database"}}],
    "initial_data_source": {
      "properties": {
        "Name": {"title": {}},
        "Status": {"select": {"options": [{"name": "Todo"}, {"name": "Done"}]}},
        "Date": {"date": {}}
      }
    }
  }'
```

**Update database schema** (use data source endpoint):

```bash
curl -X PATCH "https://api.notion.com/v1/data_sources/{data_source_id}" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{"properties": {"New Column": {"checkbox": {}}, "Old Column": null}}'
```

**Update database attributes** (title, icon, is_inline):

```bash
curl -X PATCH "https://api.notion.com/v1/databases/{database_id}" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{"title": [{"text": {"content": "New Title"}}]}'
```

### Blocks

**Get page blocks:**

```bash
curl "https://api.notion.com/v1/blocks/{page_id}/children" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03"
```

**Append blocks:**

```bash
curl -X PATCH "https://api.notion.com/v1/blocks/{page_id}/children" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "children": [
      {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "Hello world"}}]}},
      {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "Section Title"}}]}},
      {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "List item"}}]}}
    ]
  }'
```

## Property Types Reference

| Type | Format |
|---|---|
| Title | `{"title": [{"text": {"content": "..."}}]}` |
| Rich text | `{"rich_text": [{"text": {"content": "..."}}]}` |
| Select | `{"select": {"name": "Option"}}` |
| Multi-select | `{"multi_select": [{"name": "A"}, {"name": "B"}]}` |
| Date | `{"date": {"start": "2024-01-15", "end": "2024-01-16"}}` |
| Checkbox | `{"checkbox": true}` |
| Number | `{"number": 42}` |
| URL | `{"url": "https://..."}` |
| Email | `{"email": "a@b.com"}` |
| Relation | `{"relation": [{"id": "data_source_id"}]}` |

## Error Handling

| HTTP Status | Cause | Action |
|---|---|---|
| 401 | Invalid API key | Check `auth.api_key` in config |
| 403 | Database not accessible | Guide user to grant Content Access: https://notion.so/my-integrations → "Edit Integration" → "Content Access" → "Edit Access" |
| 404 | Wrong ID | Verify the ID; check if deleted |
| 429 | Rate limit | Wait and retry; ~3 req/sec average |
| 400 | Malformed body | Check property types; ensure `data_source_id` is used where required |

## Notes

- IDs are UUIDs — accepted with or without dashes
- The API cannot set database view filters (UI-only)
- `is_inline: true` embeds a database inside a page
- A database can have multiple data sources; `data_sources[0]` is the default