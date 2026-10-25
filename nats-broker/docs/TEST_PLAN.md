# TEST_PLAN — NATS Message Broker

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

Every test starts a real `NATS` server in-process on an ephemeral
port (port 0, actual port read back from the socket) and stops it in
tearDown. Tests speak both raw sockets (exact wire bytes, page
transcripts) and the bundled `NATSClient`. No real NATS server, no
fixed port.

## Cases

Wire-level (raw socket, exact page sequences):

1. `test_info_and_connect_and_ping` — first line is INFO JSON with
   host/port/client_ip; `CONNECT {}` → `+OK`; `PING` → `PONG`.
   (Page Step 2 transcript.)
2. `test_page_step3_sub_pub_msg` — `SUB CC 10` → `+OK`,
   `PUB CC 4` + `JOHN` → `+OK`, then `MSG CC 10 4` + `JOHN`
   (publisher is also the subscriber, so it receives its own message).
3. `test_unknown_command_is_err_not_disconnect` — garbage line →
   `-ERR`, connection still usable afterwards (`PING` → `PONG`).
4. `test_pub_payload_with_crlf_and_binary` — length-prefixed payload
   containing CRLF bytes arrives intact (proves byte-count, not
   line, framing).

Client-level (NATSClient):

5. `test_publish_subscribe_two_clients` — subscriber on client B
   receives a message published by client A; non-subscriber gets
   nothing (read times out cleanly).
6. `test_wildcard_star_single_token` — `foo.*` receives `foo.bar`
   but not `foo.bar.baz` or `other.bar`.
7. `test_wildcard_gt_multi_token` — `foo.>` receives `foo.bar` and
   `foo.bar.baz` but not `foo` or `other.bar`.
8. `test_unsubscribe_stops_delivery_but_publish_still_works` —
   after UNSUB the client receives nothing further, but its own PUB
   still reaches another subscriber (page Step 5).
9. `test_unsub_with_max_msgs` — `UNSUB sid 1` delivers exactly one
   more message, then stops.
10. `test_reply_to_is_carried_in_msg` — `PUB subj reply 5` arrives
    as `MSG subj sid reply 5`.
11. `test_queue_group_delivers_to_one_member` — two members of the
    same queue group share two messages one each; a non-queue
    subscriber to the same subject receives both.
12. `test_concurrent_publishers_and_subscribers` — several threads
    publishing concurrently; every subscriber receives every message
    (fan-out under concurrency, page Step 4).

Unit-level (no socket):

13. `test_subject_matching_table` — wildcard matching table for
    `*`, `>`, exact, and `>` in a non-final position.

## Success criteria

All tests pass (`OK`), no test depends on a fixed port or an
external server, and the server thread is stopped after each test
(no leaked listening sockets; check with the test run completing
and the process exiting).
