# SPEC — MCP Server For AI Agents

## Resolved challenge page (read before writing anything)

- Challenge page: http://codingchallenges.fyi/challenges/challenge-mcp-server/
- Title on page: "Build Your Own MCP Server For AI Agents"
- Found via the site's tag index: https://codingchallenges.fyi/challenges/tags
  → tag page https://codingchallenges.fyi/challenges/tags/mcp (exactly one doc
  tagged "mcp": this challenge). The challenge URL was NOT guessed.
- Tags on the assignment: ai, ai agents, artificial intelligence, mcp, llms.

## What the page asks for (Steps 0–6, verbatim in substance)

- Step 0: Create a new project/repo, pick a technology stack. Any language;
  SDKs exist for Python, Go, TypeScript, Java, Kotlin, C#, PHP, Ruby, Rust,
  Swift; otherwise implement the protocol and transport directly.
- Step 1: A very simple MCP server ("Hello, World" of MCP). Implement the
  protocol yourself using the MCP specification — "it's just JSON-RPC over
  standard io or streamable HTTP", stdio first. Export a tool called `hello`
  that takes a string and returns `Hello, <string>`.
- Step 2: Test with the MCP Inspector (transport + command set correctly):
  List Tools, select the tool, enter test data, get the Step 1 response back.
- Step 3: A new tool `CodingChallengesSolutionFinder`. Takes a single
  parameter, the name (or part of the name) of the Coding Challenge to look
  for, and returns a list of links to the relevant pages listing solutions
  to that Coding Challenge. Implementation: fetch the `README.md` from the
  Coding Challenges Shared repository and find the data within it.
- Step 4: Handle errors: not being able to access GitHub, the format of the
  page changing, or the coding challenge not being listed on the page.
- Step 5: Add the MCP server to your AI coding agent and use it to see if
  there is a solution to one of the Coding Challenges (page shows Amp).
- Step 6: Extend the server to get the solutions for a particular challenge
  in a particular language: follow the link found in Step 3, download the
  content of that page, and parse the table for a solution in the required
  language.
- Going Further (optional): documentation tool for an internal codebase,
  action tools (e.g. updating a wiki / project-management software).

## This implementation

- Language: Python 3, standard library ONLY (no MCP SDK, no third-party
  packages). The protocol + transport are implemented directly, as the page
  explicitly allows and suggests for learning ("implementing the protocol
  and transport directly").
- Single main file: `mcp_server.py`. Transports:
  - stdio (default): newline-delimited JSON-RPC 2.0 on stdin/stdout.
    This is the primary, tested transport.
  - HTTP (`--http`): plain JSON-RPC 2.0 `POST /mcp`. See Divergences.
- Protocol surface (MCP core, JSON-RPC 2.0):
  - `initialize` → `protocolVersion`, `capabilities` (tools/resources/
    prompts), `serverInfo` (`mcp-server` 0.1.0). The server accepts the
    client's protocol version and echoes back a version it supports
    (`2024-11-05`); it does NOT reject unknown client versions.
  - `notifications/initialized` (notification, no response).
  - `ping` → `{}`.
  - `tools/list`, `tools/call`.
  - `resources/list`, `resources/read` (resource `solutions://index`:
    the raw text of the solutions index currently loaded).
  - `prompts/list`, `prompts/get` (prompt `find-solution`).
- Tools:
  1. `hello` — arguments: `name` (string). Alias `string` is also
     accepted for convenience. Returns `Hello, <name>`.
     Missing/non-string argument → tool error (`isError: true`), not a crash.
  2. `CodingChallengesSolutionFinder` — arguments: `challenge` (string).
     Aliases `name`, `query` accepted. Returns one text block: one
     `Challenge Name: URL` line per match, or the sentence
     `No shared solutions listed for "<query>".` when nothing matches.
     Matching is case-insensitive substring on the link text of the
     index document. A match list, not a single link, because the page
     says "a list of links".
  3. `get_solution` (Step 6 extension) — arguments: `challenge` (string),
     `language` (string). Follows the Step 3 link: first looks for a local
     solution-list page in `--solutions-dir` (file name = slug of the
     challenge, e.g. `build-your-own-wc-tool.md`); if none is present it
     tries to download the linked page over HTTP(S) with a short timeout;
     then parses its Markdown table for a row whose language cell matches
     (case-insensitive). Returns the row as `Language: … | Author: … |
     Link: …` (whatever columns the table has), or a tool error stating
     plainly that the page/language was not found. It never invents a link.
- Prompts:
  - `find-solution` — arguments `challenge`, optional `language`.
    Returns a user-role message templating a request to use
    `CodingChallengesSolutionFinder` (and `get_solution` when a language
    is given). It is a template only; it runs no tool itself.
- Solutions index source (Step 3, honest sourcing):
  - Default: the bundled `data/shared-solutions.md` (see below).
  - `--solutions-file PATH`: load a local Markdown index instead.
  - `--solutions-url URL`: download a Markdown index over HTTP(S)
    (timeout 10 s). On failure the server keeps running with an empty
    index and every finder call reports the fetch error (Step 4); it does
    NOT silently fall back to stale bundled data.
  - `--solutions-dir PATH`: directory of per-challenge solution-list
    pages for Step 6 (default `data/solutions/` next to the script).

## Deliberate divergences from the page

1. No MCP SDK: protocol implemented by hand in stdlib Python, per the
   page's own alternative ("implement the protocol and transport
   directly"). Consequence: no SDK conveniences (no automatic schema
   validation beyond what is coded here, no SSE streaming).
2. HTTP transport is plain JSON-RPC POST, NOT Streamable HTTP with SSE:
   the page says "JSON-RPC over standard io or streamable HTTP", but
   full Streamable HTTP (SSE streams, session ids, resumability) is out
   of scope for this build. Stdio is the complete transport; HTTP is a
   minimal JSON-RPC-over-POST convenience. This is stated in the README.
3. The bundled index is a SAMPLE, not a live copy of the Coding
   Challenges Shared repository README (see Scope limits). The parser is
   generic Markdown-link/table parsing, so a real README in the same
   shape works without code changes; a differently-shaped README is
   handled as "no matches" / parse error, not by guessing.
4. `hello`'s parameter is named `name` (alias `string`): the page says
   only "takes a string" and names no parameter, so a name had to be
   chosen; both common spellings are accepted.
5. Step 6's tool is named `get_solution` (the page names no tool for
   Step 6, only the behaviour), with `challenge` + `language` arguments.

## Scope limits / NOT built (honestly)

- NO live LLM or AI agent was connected. Step 5 was NOT performed with a
  real agent (no Amp/Claude/Cursor hookup, no API key, no account). The
  README gives a sample MCP client-config snippet for the user to paste
  into their own agent, but that hookup is untested here and is the
  user's own provider setup. Tests use a scripted fake MCP client only.
- NO MCP Inspector run: the Inspector is a browser/Node tool outside
  this build environment. Its role (List Tools → call tool → see reply)
  is covered by the scripted fake client in `tests/`, which speaks the
  same JSON-RPC messages. Inspector compatibility is therefore claimed
  only at the protocol-message level, not as a verified Inspector run.
- NO real GitHub fetch at runtime by default: the server does not phone
  home to GitHub on start. Live fetching happens only if the user passes
  `--solutions-url` / a Step 6 link is followed, and any failure is
  reported as a tool error (Step 4).
- NO "Going Further" tools (internal-codebase docs tool, wiki/PM action
  tools): not built.
- NO authentication, authorisation, TLS, rate limiting, or sandboxing of
  tool arguments. This is a local development server; do not expose it
  to untrusted clients or the internet.
- NO API keys of any kind are invented, hardcoded, or requested.

## Error behaviour (Step 4)

- GitHub/index unreachable → finder calls return `isError: true` with
  the fetch error; server stays up.
- Index present but unparseable / differently formatted → no fabricated
  links; finder returns "no matches" text for that query, and a
  `--solutions-url` fetch that returns non-200 is an error, not data.
- Challenge not listed → `No shared solutions listed for "<query>".`
  (plain text, not an error, because "not listed" is a valid answer).
- Step 6 page/language not found → `isError: true` naming what was
  missing (page, table, or language row).
- Unknown tool / unknown method / bad params → JSON-RPC errors
  (-32601 / -32602). Malformed JSON line → -32700, server continues.
- Unknown resource URI / unknown prompt → JSON-RPC -32602 error.
