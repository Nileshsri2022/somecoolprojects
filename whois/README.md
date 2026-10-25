# whois — Build Your Own Whois

Coding Challenges, worked in `somecoolprojects/`.
Docs first, then code — see `docs/` (SPEC, DESIGN, TEST_PLAN).
Source page: https://codingchallenges.fyi/challenges/challenge-whois/

A whois client in pure Python 3 standard library: queries a whois
server on port 43 per RFC 3912, parses the `Key: Value` response
(dropping blank lines and `%` comments), and follows referrals —
IANA's `refer` field, then a registry's `Registrar WHOIS Server`
field — until a response carries no referral. Works for domain
names, IP addresses, and AS numbers, all through the same path.

## Usage

```sh
# IANA chain for a domain (default server whois.iana.org, port 43)
python3 whois.py example.com

# IP address (Step 5 of the page)
python3 whois.py 8.8.8.8

# Only the first server, no referral following
python3 whois.py example.com --no-follow

# Parsed key/value output instead of raw responses
python3 whois.py example.com --parsed

# Query a specific server / port / timeout / hop limit
python3 whois.py example.com --server whois.verisign-grs.com
python3 whois.py example.com --server 127.0.0.1 --port 4343
python3 whois.py example.com --timeout 5 --max-hops 3
```

Errors go to stderr with a non-zero exit code.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use local fake whois servers on ephemeral ports — no real
whois server is contacted by the test suite.

## Divergences from the challenge page

1. `--port` applies to every hop, not just the first query, so
   referral chains can be tested against local fake servers.
   Default is 43, so real-world behaviour is exact.
2. Beyond the page's `refer` field, the registrar hop is followed
   via `Registrar WHOIS Server` (also `Whois Server` / `Whois` as
   fallbacks). The page's Step 4 says "if there is another `refer`
   field"; in practice registry responses carry the registrar in
   the `Registrar WHOIS Server` field, not `refer`, so following
   only `refer` would stop one hop early on real domains.
3. RDAP (the page's "Going Further") is not implemented — the
   challenge steps are the whois protocol only.
4. Loop protection (visited-server set) and a `--max-hops` cap
   (default 5) are added; the page does not mention them, but
   without them a cyclic referral would loop forever.
