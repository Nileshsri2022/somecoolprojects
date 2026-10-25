# TEST_PLAN — MCP Server For AI Agents

Run: `python3 -m unittest discover -s tests -v` from `mcp-server/`.
Stdlib only; no network, no LLM, no real agent needed.

## Test doubles

- Scripted fake MCP client (`tests/test_mcp_server.py`, class
  `StdioClient`): spawns `mcp_server.py` as a subprocess, writes
  JSON-RPC lines to stdin, reads one JSON line per response from
  stdout. This is the Step 2 Inspector role, scripted: initialize →
  tools/list → tools/call, asserting the exact reply text.
- HTTP tests: spawn the server with `--http --port 0` (ephemeral port
  printed to stderr, parsed by the test), POST JSON-RPC via `urllib`,
  then terminate the child by explicit PID. No `pkill`, no fixed port.
- Unit tests call `handle_request()` / `find_solutions()` /
  `parse_solution_table()` directly for error paths that need no process.

## Coverage (mapped to challenge steps)

| Area | What is asserted |
|---|---|
| Step 1 `hello` | returns `Hello, World`; alias arg `string` works; missing arg → `isError`; non-string arg → `isError`; empty string → `Hello, ` |
| Step 1/2 handshake | `initialize` returns serverInfo + tools/resources/prompts capabilities; `notifications/initialized` gets no response; `ping` → `{}`; `tools/list` names all three tools with input schemas |
| Step 3 finder | exact-name match, substring match (multiple links), case-insensitive match, no-match sentence, unknown tool → JSON-RPC -32601, malformed JSON line → -32700 and server survives |
| Step 4 errors | unreachable `--solutions-url` → finder `isError` naming the failure, server still answers `ping`; custom index with no links → no-match sentence, no fabricated link; Step 6 missing language → `isError`; Step 6 missing page → `isError`; unknown resource/prompt → -32602 |
| Step 5 (scripted only) | the fake client drives the full initialize→list→call flow end-to-end over stdio, proving an agent-shaped client can use the server. NO real agent is claimed. |
| Step 6 `get_solution` | local page + language match (case-insensitive) returns the row; language absent from table → `isError`; table with extra columns still parses; slug mapping for multi-word challenge names |
| Resources/prompts | `resources/list` includes `solutions://index`; `resources/read` returns the loaded index text; `prompts/list` includes `find-solution`; `prompts/get` renders challenge (and language) into the message; unknown prompt → -32602 |
| HTTP transport | `POST /mcp` initialize + tools/call round-trip; `GET /mcp` → 404/405, not a protocol reply; unknown path → 404 |

## What is NOT tested (honestly)

- MCP Inspector UI run (not available here); covered at message level.
- A real AI agent hookup (Step 5 live): config snippet in README is
  untested against a real agent and is labelled as such.
- A live download of the real Shared Solutions README: the parser is
  tested against bundled + synthetic indexes; a real README whose
  format differs would surface as "no matches", which is the honest
  failure mode, not a silent wrong answer.
