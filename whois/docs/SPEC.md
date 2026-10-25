# SPEC — Build Your Own Whois

Source page: https://codingchallenges.fyi/challenges/challenge-whois/
(Slug: `challenge-whois` — first guess, no 404, no correction needed.)

Protocol: WHOIS, RFC 3912. A client opens a TCP connection to port 43,
sends the query followed by CRLF, and reads until the server closes
the connection. There is no framing, no authentication, and no
structured response format — the reply is free-form text, mostly
`Key: Value` lines.

## Steps from the page, mapped to behaviour

- Step 1: Accept exactly one query argument (a domain name). Send it
  to IANA (`whois.iana.org`, port 43). Receive the response and print it.
- Step 2: Parse the response: throw away blank lines and `%` comment
  lines, put the rest into a key/value data structure.
- Step 3: Use the `refer` field of the parsed response to find the
  next server, send it the same query, read and print its response.
- Step 4: Parse that response too; if it contains another referral,
  repeat — follow the chain until a response has no referral.
- Step 5: The same code path must work for an IP address (and, by the
  same mechanism, an AS number) instead of a domain name, because
  IANA knows about IPs and AS numbers as well as domains.
- Going Further (RDAP): explicitly NOT built — out of scope, see
  Divergences in README.md.

## Behaviour specified here

- Default first server: `whois.iana.org`, port 43, timeout 10 s.
- Default output: the raw response of every hop, in order. This
  matches Steps 1/3/4 ("print the response") at each hop.
- `--parsed`: instead of raw text, print the parsed key/value lines
  of every hop (comments and blank lines dropped, as in Step 2).
- `--no-follow`: query only the first server, do not follow referrals.
- `--server`, `--port`, `--timeout`, `--max-hops` override the defaults.
  `--port` applies to every hop (needed to test referrals against a
  local fake server; see Divergences).
- Referral fields, checked in this order, case-insensitively:
  `refer`, then `registrar whois server`, then `whois server`,
  then `whois`. The first non-empty value wins. A referral equal to
  the server just queried, or already visited, ends the chain
  (loop protection); so does reaching `--max-hops` (default 5).
- A referral value may carry a trailing port (`host:port`) or a URL
  scheme; the host part is used and `--port` still wins. Real whois
  referrals are bare hostnames, so this is defensive parsing only.
- The query string is sent verbatim (after stripping surrounding
  whitespace). No validation beyond: non-empty, no whitespace or
  control characters inside it. Domain, IPv4, IPv6 and AS queries
  all go through the same path, as Step 5 requires.
- Errors (DNS failure, connection refused, timeout, empty query,
  no argument) are reported on stderr with a non-zero exit code.
  No partial raw output is printed for a failed hop.

## Success criteria

1. `python3 whois.py facebook.com` against the real IANA chain
   returns the IANA response followed by the registry response
   (network-dependent; not asserted by the test suite).
2. `python3 -m unittest discover -s tests -v` passes with no
   network access to real whois servers (local fake servers only).
3. A two-hop fake chain (IANA-like `refer:` → registrar-like
   response with no referral) is followed and both responses shown.
4. A fake chain that refers back to an already-visited server
   terminates instead of looping forever.
