# dns-resolver — Build Your Own DNS Resolver

Coding Challenges, worked in `somecoolprojects/`.
Docs first, then code — see `docs/` (SPEC, DESIGN, TEST_PLAN).
Source page: https://codingchallenges.fyi/challenges/challenge-dns-resolver/

A DNS resolver client in pure Python 3 standard library: builds DNS
messages (header, question, answers, name compression per RFC 1035),
sends queries over UDP, parses responses, and can resolve iteratively
from a root server, following NS referrals and CNAME records.

## Usage

```sh
# Recursive query (default server 8.8.8.8, like Step 2/3 of the page)
python3 dns_resolver.py dns.google.com

# Query a specific server / port / record type
python3 dns_resolver.py example.com --server 1.1.1.1 --type AAAA

# Iterative resolution from a root server (Step 4 of the page)
python3 dns_resolver.py dns.google.com --iterative
python3 dns_resolver.py dns.google.com --iterative --root 198.41.0.4
```

Answers print one per line. Errors go to stderr with a non-zero exit
code. `--timeout` defaults to 5 seconds.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use a local fake DNS server on an ephemeral port — no public
DNS server is contacted by the test suite.

## Divergences from the challenge page

1. `--port` applies to every hop of iterative resolution, not just the
   first query, so iterative resolution can be tested against a local
   fake server. Default is 53, so real-world behaviour is exact.
2. A referral whose NS has no glue A record is resolved with one
   recursive query to `--recursive-server` (default `8.8.8.8`),
   rather than a fully iterative resolution of the NS name.
3. Output is one answer per line instead of the page's quoted-list
   repr, for scriptability.
