# MCP Server For AI Agents

Build Your Own MCP Server — Coding Challenges challenge:
http://codingchallenges.fyi/challenges/challenge-mcp-server/

A Model Context Protocol server implemented directly in Python 3
standard library (no MCP SDK, no third-party packages). It speaks
JSON-RPC 2.0 over stdio by default, or plain JSON-RPC POST on `--http`.

## Tools (challenge Steps 1, 3, 6)

| Tool | Arguments | Returns |
|---|---|---|
| `hello` | `name` (string; alias `string`) | `Hello, <name>` |
| `CodingChallengesSolutionFinder` | `challenge` (name or part of it) | List of `Challenge: URL` lines, or `No shared solutions listed for "<query>".` |
| `get_solution` | `challenge`, `language` | The solution-table row for that language, or a plain error |

Also: `initialize`, `ping`, `tools/list`, `resources/list` +
`resources/read` (`solutions://index`), `prompts/list` + `prompts/get`
(`find-solution`).

## Run

```sh
# stdio (default) — pipe JSON-RPC lines in, read replies out
python3 mcp_server.py

# HTTP (plain JSON-RPC POST /mcp, NOT Streamable HTTP/SSE — see docs/SPEC.md)
python3 mcp_server.py --http --port 8080

# Use a real solutions index instead of the bundled sample
python3 mcp_server.py --solutions-file /path/to/README.md
python3 mcp_server.py --solutions-url https://example.com/README.md
python3 mcp_server.py --solutions-dir /path/to/solution-pages
```

## Tests

```sh
python3 -m unittest discover -s tests -v   # 22 tests, scripted fake client only
```

## Honest limits — read before using

- **No live LLM or AI agent was connected.** Step 5 (hook up to a real
  coding agent) was NOT performed here: no API key, no account, no
  Amp/Claude/Cursor run. Live use needs the user's own provider setup.
  A sample client config for pasting into your own agent:
  ```json
  {"mcpServers": {"coding-challenges": {
    "command": "python3",
    "args": ["/path/to/mcp-server/mcp_server.py"]}}}
  ```
  That hookup is untested against a real agent.
- **The bundled index is a sample**, not a live copy of the Coding
  Challenges Shared repository README (which the Step 3 tool is meant
  to parse). The parser is generic Markdown-link parsing, so a real
  README in link form works with `--solutions-file`/`--solutions-url`
  and no code change; a differently-shaped README surfaces as
  "no matches", never as a fabricated link.
- **MCP Inspector was not run** here; its role is covered at the
  message level by the scripted fake client in `tests/`.
- **No auth, TLS, or sandboxing.** Local development use only; do not
  expose the HTTP mode beyond localhost.

Docs: `docs/SPEC.md` (steps, divergences, scope limits),
`docs/DESIGN.md`, `docs/TEST_PLAN.md`.
