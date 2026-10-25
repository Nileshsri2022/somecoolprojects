# video-chat — TEST PLAN

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

Every test starts a real server on an ephemeral port
(`port 0`) in a background thread and talks to it over HTTP
through the `Client` class — no mocks of the server, so the
tests verify the actual wire behaviour. Servers are shut down
in `tearDown` (explicit `shutdown()` + `server_close()`).

## Cases

Health and rooms:

1. `GET /` returns service name and room count 0.
2. `GET /rooms` is empty before any join, lists a room after
   a join, and drops it after the last member leaves.

Join / leave:

3. First join returns an empty peer list; second join returns
   the first peer, and the first peer's poll sees
   `peer-joined` for the second.
4. Re-joining the same user is idempotent: no duplicate member,
   peer list unchanged, no second `peer-joined`.
5. Leaving broadcasts `peer-left` to remaining members; the
   room disappears when the last member leaves.
6. Leaving a room you are not in, or an unknown room, fails
   (404) and changes nothing.

Send / poll (the signalling flow):

7. Full call flow, in order: alice joins, bob joins, alice
   sends `offer` (SDP-shaped dict payload) to bob, bob polls
   and receives exactly that offer, bob sends `answer`, alice
   receives it, both exchange `candidate` messages, both
   exchange `chat` messages, alice sends `bye`, bob receives
   it. Sequence numbers are strictly increasing in poll order.
8. Broadcast (`to` omitted): delivered to all other members,
   never echoed to the sender.
9. Polling with `since` returns only newer messages, and
   re-polling with the same `since` returns the same set
   (idempotent, non-destructive).
10. Rooms are isolated: a message sent in room-a is never
    visible to a member polling room-b.

Validation / errors:

11. Invalid room/user names (empty, spaces, `/`, over 64
    chars) are rejected with 400.
12. Malformed JSON body, non-object body, and missing required
    fields are rejected with 400.
13. Unknown message `type` is rejected with 400.
14. Sending from a non-member is 403; sending to a non-member
    or polling an unknown room is 404; polling as a
    non-member is 403.
15. Payloads are relayed opaquely and byte-identical in
    structure: a nested SDP dict and a plain-string chat
    payload both arrive unchanged (verified by equality).
16. Demo scenario: the scripted `run_demo` flow completes
    against its own ephemeral server (covered at CLI level by
    running `python3 video_chat.py demo` manually; the unit
    tests cover the same steps through the client).

## Success criteria

All tests pass; the demo prints each step with its
verification and exits 0; no test leaves a server thread
running (each `tearDown` shuts its server down). Manual check:
`serve` on a chosen port answers `GET /` with curl.
