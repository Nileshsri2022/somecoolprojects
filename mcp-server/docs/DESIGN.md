# DESIGN — MCP Server For AI Agents

## Architecture (one file, stdlib only)

```
mcp_server.py
  ├─ parse_args()          CLI: --http, --port, --solutions-file,
  │                        --solutions-url, --solutions-dir
  ├─ load_index()          read local file, or download URL (10 s timeout),
  │                        or fall back to bundled data/shared-solutions.md
  ├─ find_solutions()      Step 3: Markdown-link scan of the index
  ├─ slugify()             challenge name → solution-page file name
  ├─ parse_solution_table() Step 6: Markdown-table parser
  ├─ get_solution()        Step 6: local page first, then HTTP(S) download
  ├─ TOOLS / RESOURCES / PROMPTS   static capability catalogues
  ├─ handle_request()      pure dispatcher: dict in → dict out (or None
  │                        for notifications). All transport-independent
  │                        logic lives here, so stdio and HTTP share it
  │                        and tests can call it without a subprocess.
  ├─ serve_stdio()         newline-delimited JSON-RPC; logs to stderr only
  │                        (stdout must stay pure protocol, or clients
  │                        desynchronise). Malformed lines → -32700,
  │                        server keeps reading.
  └─ serve_http()          ThreadingHTTPServer, POST /mcp → JSON-RPC;
                           anything else → 404; non-POST on /mcp → 405.
                           Plain JSON response, no SSE (see SPEC §2).
```

## Wire format

JSON-RPC 2.0 objects, one per line on stdio, one per POST body on HTTP:

```json
{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
 "params": {"name": "hello", "arguments": {"name": "World"}}}
→ {"jsonrpc": "2.0", "id": 1,
   "result": {"content": [{"type": "text", "text": "Hello, World"}]}}
```

Notifications (requests with no `id`, e.g. `notifications/initialized`)
produce no response — this is required, not optional: replying to a
notification breaks MCP clients that count responses per request id.

Tool results follow the MCP shape: `{"content": [{"type": "text",
"text": "..."}], "isError": true?}`. A tool-level failure (unknown
challenge language, unreachable page) is `isError: true` inside a
successful JSON-RPC result; a protocol-level failure (unknown method,
bad params) is a JSON-RPC `error` object. Keeping those two levels
apart is deliberate and matches the MCP spec's error model.

## Index parsing (Step 3)

`find_solutions(index_text, query)` scans line by line for Markdown
links `[text](url)` (regex `\[(.*?)\]\((.*?)\)`), keeps links whose
text contains the query as a case-insensitive substring, deduplicates
by URL preserving order. It does NOT assume headings, sections, or a
specific table layout, so a real Shared Solutions README whose entries
are links will parse; entries that are bare URLs or non-link text are
simply not matches (reported as such, never fabricated).

Bundled sample index (`data/shared-solutions.md`) uses exactly this
shape — one bullet link per challenge — plus a couple of decoy entries
so tests can prove substring matching and non-matching.

## Solution-table parsing (Step 6)

`parse_solution_table(page_text, language)` scans for Markdown table
rows (`| a | b | c |`), skips the header separator row (`---`), treats
the first row as the header, and returns the first data row whose
`language` column (first column, case-insensitive) equals the requested
language. Column names come from the header row itself, so a table
with extra columns (e.g. `Notes`) still works; a table without a
language column cannot match and yields a clear error.

`get_solution()` resolution order:
1. Local page `<solutions-dir>/<slug(challenge)>.md`, if it exists —
   it is authoritative: a missing language there is an error, and no
   network fetch is attempted for that challenge.
2. Otherwise, for each Step 3 link (in order), HTTP(S) GET with a 10 s
   timeout; first page that parses AND contains the language wins.
   A download failure for one link does not abort the search over the
   remaining links; if all fail, the error names the last failure.
3. If no link yields the language, error: "no solution in language X
   found for challenge Y".

## Security notes

- No shelling out, no `eval`, no API keys. The only network activity is
  an explicit user-configured index URL or a Step 6 link follow.
- Tool arguments are treated as data, never executed. `hello` echoes
  its argument back as text only.
- Do not expose the HTTP mode beyond localhost; there is no auth.
