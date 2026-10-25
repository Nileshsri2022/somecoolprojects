# TEST_PLAN — Uptime Monitoring Service

Run: `python3 -m unittest discover -s tests -v` from the project
directory. All tests use LOCAL fake HTTP servers on ephemeral
ports only (port 0 → OS-assigned, read back from the server).
No test probes a real public site. Servers are shut down in
`tearDown` and no test leaves a stray process.

## Coverage map

| Area | Tests |
|------|-------|
| URL validation (bad scheme, missing host, ok http/https) | `test_add_rejects_bad_url`, `test_add_accepts_http_and_https_urls` |
| `add`/`list`/`remove`, duplicate add rejected, remove of unknown target errors | add/list/remove tests |
| Interval validation (0 / negative rejected, 1 accepted) | `test_add_rejects_interval_below_one` |
| Method validation (HEAD/GET ok, POST rejected) | `test_add_rejects_bad_method` |
| HEAD check against local server: status 200, ok=True, latency recorded | `test_head_check_records_success` |
| HEAD 500 → ok=False, status recorded | `test_head_check_records_server_error_as_down` |
| Unreachable target (closed port) → ok=False, status None, error set | `test_check_unreachable_target_records_error` |
| GET check: ttfb_ms and total_ms recorded, ttfb <= total | `test_get_check_records_ttfb_and_total` |
| Slow GET server (delayed body) → ttfb < total | `test_get_check_slow_body_ttfb_less_than_total` |
| DOWN alert after N consecutive failures, exactly once per incident, RECOVERY on success | `test_down_alert_after_n_failures_once_per_incident`, `test_recovery_alert_after_incident` |
| Below-threshold failures produce no alert | `test_no_alert_below_threshold` |
| SLOW alert when latency exceeds threshold; slow does not increment failure counter | `test_slow_alert_and_no_failure_count` |
| Alert sinks: log file line, email-hook file content, webhook POST JSON received by local server | sink tests |
| Report: uptime % math, date-range filtering, empty range → n/a | report tests |
| Report sparkline present when checks exist | `test_report_contains_sparkline` |
| Export JSON round-trips checks; export CSV header + rows | export tests |
| `run --cycles` performs checks for due targets and stores them | `test_run_cycles_checks_due_targets` |
| Store persistence: checks survive a fresh load | `test_store_persists_across_loads` |
| Corrupt store file raises a clear error, does not silently reset | `test_corrupt_store_raises` |
| One failing target does not block another target's check | `test_one_bad_target_does_not_block_others` |

## Manual checks (not automated)

- `run` without `--cycles` loops until Ctrl-C and exits with a
  summary line (verified by hand during development, not in the
  automated suite, to avoid a hanging test).
- Webhook against a real external endpoint: not tested (would
  need a public URL); the local webhook-receiver test proves the
  POST shape.
