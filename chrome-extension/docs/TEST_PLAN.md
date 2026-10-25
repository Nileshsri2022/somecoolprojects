# TEST_PLAN — Chrome Extension

## What is tested, and what is NOT

Tested here (by `tests/test_extension.py`, Python stdlib only, run
by the worker before reporting done):

1. Manifest: valid JSON, `manifest_version == 3`,
   `chrome_url_overrides.newtab == "newtab.html"`,
   `storage` permission present, `host_permissions` covers
   `api.github.com`, icons referenced exist, version/name present.
2. Required files exist: `newtab.html`, `css/newtab.css`,
   `js/newtab.js`, `js/format.js`, `js/quotes.js`, icons.
3. HTML: references the CSS + all three JS files, contains the
   `Coding Challenges` wordmark, and element ids the JS expects
   (`clock`, `date`, `quote`, `github-list`, `substack-list`,
   `settings-panel`, `settings-toggle`).
4. CSS: contains the Step 1 background colour `#04295B` and a
   centred layout for the wordmark.
5. JS syntax: every `.js` file passes `node --check` when Node is
   available (it was: Node v24 in this environment). If Node is
   absent, the harness falls back to structural checks (balanced
   braces/parens, no obviously truncated file) and reports that
   fallback — it never claims a `node --check` pass it did not run.
6. Pure-function behaviour, executed in Node: `format.js` is loaded
   and asserted on fixed dates (midnight/noon/PM, single-digit
   minutes, leap-day day-of-year), `pickDailyQuote` determinism
   (same date → same quote; different days cycle), `parseGitHubPRs`
   mapping + non-array → `[]`, `buildGitHubApiUrl` /
   `buildSubstackProxyUrl` exact URLs.
7. Safety: no `.innerHTML =` assignment anywhere in `newtab.js`
   (rendering uses `textContent` + created elements);
   no hardcoded token/password/credential strings in any source file.
8. No `__pycache__` left behind (harness run uses `-B` / cleanup).

NOT tested here (honest scope limit):

- Loading the extension in a real Chrome browser (unpacked load,
  new-tab rendering, live GitHub/Substack fetches). No live-browser
  tooling is available to this worker, so this is NOT claimed.
  Manual verification steps are in README.md ("Load it yourself")
  and take ~2 minutes: `chrome://extensions` → Developer mode →
  Load unpacked → select this folder → open a new tab.
- Live network fetches: the harness never calls api.github.com or
  Substack (no network dependence, no rate-limit burn, no flaky
  tests). Live behaviour is covered only by the manual steps.
- The default Substack proxy (allorigins) being up at any given
  moment: it is a third-party service; the panel shows its error
  honestly if it is down.

## How to run

```sh
cd chrome-extension
python3 tests/test_extension.py
```

Exit code 0 = all green. The harness prints `PASS`/`FAIL` per case
and a final `passed/failed/skipped` summary. Skipped cases (e.g.
Node absent) are counted as skipped, never as passed.
