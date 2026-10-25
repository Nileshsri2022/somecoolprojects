# TEST_PLAN — SMTP Server

Runner (from the project directory):

```sh
python3 -m unittest discover -s tests -v
```

All tests start the real server in a background thread on an
ephemeral port (`port=0`) and talk to it over real sockets.
No test ever contacts a real mail server, a fixed port, or the
network beyond loopback.

## Cases (`tests/test_smtp_server.py`)

Raw-socket session tests (one helper opens a connection and asserts
the 220 greeting, then drives commands line by line):

1. `test_greeting` — connect → `220` greeting containing
   `CC SMTP Server`.
2. `test_helo_and_ehlo` — `HELO` → 250; fresh session `EHLO` → 250.
3. `test_helo_missing_argument` — bare `HELO` → 501.
4. `test_mail_before_helo_rejected` — `MAIL FROM:` before HELO → 503.
5. `test_rcpt_before_mail_rejected` — `RCPT TO:` before MAIL → 503.
6. `test_data_before_rcpt_rejected` — `DATA` before RCPT → 503.
7. `test_malformed_address_rejected` — `MAIL FROM:<not-an-address>`
   → 501.
8. `test_full_message_raw` — HELO, MAIL, two RCPTs, DATA with a
   dot-stuffed line (`..dot` arrives stored as `.dot`), terminator
   → 250; stored message has sender, both recipients, body, and
   the unstuffed line.
9. `test_rset_clears_envelope` — MAIL + RCPT, then RSET → 250;
   a following `DATA` is rejected (503) and a following `RCPT`
   is rejected (503), proving the envelope was cleared.
10. `test_noop_and_unknown_command` — `NOOP` → 250; `FROB` → 500.
11. `test_quit` — `QUIT` → 221 and the connection closes.
12. `test_case_insensitivity` — lowercase `helo`/`mail from:`/
    `rcpt to:`/`data`/`quit` all work.
13. `test_second_message_same_connection` — two complete messages
    over one connection both land in the store.
14. `test_null_reverse_path` — `MAIL FROM:<>` is accepted.

`smtplib` client tests (the page's "an SMTP client can deliver" bar):

15. `test_smtplib_sendmail` — `smtplib.SMTP` `ehlo()`, `sendmail()`,
    `quit()`; message stored with correct sender, recipient, subject
    line and body.
16. `test_concurrent_clients` — 5 threads each send one message via
    `smtplib` simultaneously; all 5 are stored exactly once.
17. `test_maildir_storage` — server started with a temp maildir;
    after one message, exactly one `.eml` file exists containing the
    sender, recipient, and body.

## Not covered (out of scope, by design)

- TLS, AUTH, SIZE limits, relaying, POP3/IMAP retrieval — none are
  implemented (see SPEC divergences), so there is nothing to test.
- Delivery to real MX hosts — explicitly forbidden by the task;
  all mail stays in memory / the temp maildir.
