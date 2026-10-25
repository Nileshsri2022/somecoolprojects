# DESIGN — NATS Message Broker

## Assumptions (stated before coding)

1. Python 3 standard library only, one main file (`nats_broker.py`),
   as the brief requires. No third-party NATS library, no real NATS
   server dependency.
2. The challenge page is the spec; the NATS protocol docs it links
   fill in details the page only sketches (MSG form, reply-to,
   wildcards, queue groups, UNSUB max_msgs). Where the page and real
   NATS disagree (Step 5's `UNSUB 1-`), real NATS wins and the
   divergence is recorded in SPEC.md.
3. Text protocol over TCP, CRLF framing, binary-safe PUB payloads
   (length-prefixed, not line-delimited). This forces buffered
   byte-exact reads rather than line iteration over the socket.
4. Thread-per-client (page Step 4 explicitly allows it). Shared
   subscription state is guarded by one lock; delivery snapshots the
   matching subscriptions under the lock and sends outside it, so a
   slow/blocked subscriber cannot stall the publisher's thread or
   other deliveries (a send failure just drops that connection).
5. Verbose mode always on (`+OK` after CONNECT/SUB/UNSUB/PUB) to
   match the page's telnet transcripts exactly.
6. Tests must be self-contained: they start a real server in-process
   on an ephemeral port (port 0), speak the raw protocol and via the
   bundled minimal client, and shut the server down in tearDown.
   No fixed port, no external server, no sleeps as synchronisation
   where a blocking read with a timeout will do.

## Architecture

```
nats_broker.py
  subject_matches(pattern, subject)   # token-wise *, > matching
  parse helpers                        # CONNECT json, SUB, UNSUB, PUB header
  Broker                               # subscription registry + delivery
    subscribe(client, subject, queue, sid)
    unsubscribe(client, sid) / unsubscribe_after(client, sid, max)
    publish(subject, reply_to, payload, sender)
  ClientHandler (thread)               # one per TCP connection:
                                       #   INFO -> loop: read line ->
                                       #   dispatch -> PUB reads payload
  NATSClient                           # minimal test/CLI client:
                                       #   connect, ping, subscribe,
                                       #   unsubscribe, publish,
                                       #   read_msg(timeout)
  serve(host, port) / main()           # CLI entry point
```

Subscription record: (client, subject pattern, queue name or None,
sid, remaining deliveries or None). Delivery counting for UNSUB
max_msgs is decremented per delivered message; reaching zero removes
the subscription after that delivery.

Queue-group delivery: matching subscriptions are partitioned into
non-queue subscribers (all receive a copy) and queue groups keyed by
(pattern, queue name). Each group delivers to one member, chosen
round-robin via a per-group counter kept in the broker. The counter
only advances over members that actually match the published subject,
so wildcard queue members that don't match don't consume a turn.

## What is deliberately NOT built

JetStream/streams, persistence, auth, TLS, clustering/leafnodes,
request/reply helpers beyond the reply-to field passthrough, and
`INFO` updates. Each would be speculative scope beyond the page's
five steps; the reply-to field is carried through MSG so a caller
can build request/reply on top without server changes.
