# DESIGN — Whois

## Assumptions (stated before coding, per ponytail rules)

1. The whois protocol is line-oriented text with no length prefix:
   the only end-of-response signal is the server closing the
   connection (RFC 3912). So `query()` reads with `recv()` in a loop
   until EOF, then decodes as UTF-8 with errors replaced.
2. Real responses are mostly `Key: Value`, but keys vary by server
   (IANA uses `refer:`; registries use `Registrar WHOIS Server:`).
   Parsing must therefore be case-insensitive and tolerant: a line
   without a colon is kept under the key `""` only if `--parsed`
   output needs it — in practice such lines are rare (continuation
   lines); this implementation appends a colon-less line to the
   previous value, and drops it if there is no previous value.
   Blank lines and lines starting with `%` (after stripping leading
   whitespace) are dropped, per Step 2.
3. A key may repeat (e.g. multiple `Domain Status:` / `Name Server:`
   lines). The parsed structure is therefore
   `dict[str, list[str]]` with lower-cased keys, insertion-ordered
   (Python dicts preserve it), not a flat `dict[str, str]`.
4. Referrals carry no port in the real protocol, so a single
   `--port` for all hops is the only sane test hook (see SPEC).
   Default port is 43, so real-world behaviour is unchanged.
5. The query is one argument. Multiple queries, interactive mode,
   and RDAP are out of scope — nothing speculative is built.

## Module layout (single file, stdlib only)

`whois.py`:

- `query(server, query, port=43, timeout=10)` — one RFC 3912
  exchange: `socket.create_connection`, `sendall(query + "\r\n")`,
  read to EOF, return decoded text. Raises `OSError` on failure;
  the caller turns that into a clean stderr message.
- `parse_whois(text)` — returns `dict[str, list[str]]` per
  assumption 2. Splits on the first `:` only, so values containing
  colons (URLs, timestamps) survive intact. Strips the key and value.
- `find_referral(parsed)` — scans the referral keys in SPEC order,
  returns the first non-empty value, or `None`. Strips a URL scheme
  and a `:port` suffix if present.
- `lookup(query, server, port, timeout, max_hops, follow)` —
  returns `list[tuple[server, response]]`, the hop chain. Tracks
  visited servers (lower-cased) to break loops; stops after
  `max_hops` hops or when no referral is found.
- `format_parsed(parsed)` — renders parsed data as
  `key: value` lines, one per value, keys in first-seen order
  (lower-cased, matching the parse step; original case is not
  preserved because the structure is keyed case-insensitively).
- `main(argv)` — argparse CLI, prints each hop's raw (default)
  or parsed (`--parsed`) response; on `OSError` prints to stderr
  and returns 1. Hops are printed in order with no separator
  added, because each response already ends with a newline; a
  missing trailing newline is added so hops never run together.

## Why no separate client class

The whole tool is one exchange plus a loop over it. A class would
add surface with no behaviour to hold; plain functions are the
minimum code that satisfies the page's steps.

## Test approach (see TEST_PLAN.md)

A fake whois server is a `socketserver.ThreadingTCPServer` bound
to port 0 (ephemeral) in the test process. It reads one CRLF-
terminated line, then sends a scripted response and closes — the
same close-to-signal-EOF contract as a real server. Referral-chain
logic itself is tested with `query()` stubbed (distinct hosts),
because referrals carry no port and two fake servers cannot share
one ephemeral port; `--port` applying to every hop still lets a
single fake server be exercised end-to-end via `main`.
