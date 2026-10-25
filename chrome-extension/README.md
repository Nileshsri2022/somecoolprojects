# chrome-extension — Build Your Own Chrome Extension

Coding Challenges challenge: build a Chrome extension that customises
every new tab. Source page (read first, 2026-10-25):
https://codingchallenges.fyi/challenges/challenge-chrome-extension

## IMPORTANT divergence (documented, not silent)

Unlike other wave projects, the deliverable here is the REAL extension
source — `manifest.json` + HTML/CSS/JavaScript, as the challenge page
specifies — because a Chrome extension cannot be written in Python.
The Python code under `tests/` is only a stdlib test harness that
statically validates the extension; it is not the product.

## What it does

- New tab on Coding Challenges Blue `#04295B`, centred wordmark
  `Coding Challenges>_` with a blinking-cursor underscore (Step 1).
- Live clock (updates every second) + human-friendly date below it
  (Step 2).
- Open pull requests for the Shared Solutions repo, via the GitHub
  REST API, no account/token needed (Step 3, Version 2).
- Latest Coding Challenges Substack posts via a configurable proxy
  (Step 3, Version 1 — Substack RSS sends no CORS headers, so a proxy
  is required; default is the public `api.allorigins.win` proxy, which
  you can change or clear in Settings).
- Daily quote (offline built-in list, same quote all day) and a
  Settings panel (gear button) for the GitHub repo, proxy URL, and
  which sections to show (Going Further, generic/customisable part).
- No credentials are ever requested, stored, or sent.

## Load it yourself (manual verification — NOT done by this worker)

This worker has no live-browser tooling, so loading in real Chrome
was NOT verified here. To verify it yourself (~2 minutes):

1. Open `chrome://extensions`, turn on **Developer mode**.
2. **Load unpacked** → select this `chrome-extension/` folder.
3. Open a new tab: you should see the blue page, wordmark, clock,
   date, quote, and both panels (or honest error text if the network
   / proxy / GitHub rate limit blocks a fetch).
4. Click the gear button, change the repo or proxy, Save, and watch
   the panels re-fetch.

## Run tests

```sh
python3 tests/test_extension.py
```

Stdlib only, no network. It validates the manifest (MV3, newtab
override, permissions), required files, HTML/CSS/JS wiring, the
`#04295B` branding, JS syntax via `node --check` (when Node exists),
the pure date/URL/parse helpers executed in Node, and that no
`innerHTML` or credential strings appear in the source.

## Files

```
manifest.json  newtab.html  css/newtab.css
js/format.js   js/quotes.js  js/newtab.js
icons/icon16.png  icons/icon48.png  icons/icon128.png
docs/SPEC.md  docs/DESIGN.md  docs/TEST_PLAN.md
tests/test_extension.py
```

## Scope limits (honest)

- NOT published to the Chrome Web Store (needs a developer account
  and review — your decision, not done here).
- NOT loaded/tested in a real Chrome browser by this worker (see
  manual steps above).
- Substack images/descriptions are not rendered: RSS descriptions
  contain HTML and are deliberately not injected into the page.
- Icons are simple blue-square placeholders, not official artwork.
- If you set a non-default proxy, add its host to
  `host_permissions` in `manifest.json` and reload the extension.
- Default GitHub repo spelling `CodingChallegesFYI/SharedSolutions`
  is kept exactly as printed on the challenge page; if GitHub 404s
  it, correct it in Settings.
