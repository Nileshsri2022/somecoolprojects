# SPEC — Build Your Own Chrome Extension

Source: https://codingchallenges.fyi/challenges/challenge-chrome-extension
(read 2026-10-25; page live, not a 404)

## What the challenge asks for

A Chrome extension (JavaScript/TypeScript + HTML + CSS) that customises
every new tab, inspired by Bonjourr and Momentum.

- **Step Zero** — Set up the IDE/tooling as you like. (Tooling here: plain
  HTML/CSS/JS, no build step, no framework, so there is nothing to install
  to load the extension.)
- **Step 1 — "Hello, World" new tab** — An extension that:
  1. Can be installed locally (unpacked).
  2. Sets the new-tab background to Coding Challenges Blue `#04295B`.
  3. Displays `Coding Challenges>_` centred on the new tab (branding
     matched as far as a static page allows: blue background, white
     monospace wordmark, blinking-cursor underscore).
- **Step 2 — Clock** — Add the current time to the tab and the date in a
  human-friendly format below it, updating live (every second).
- **Step 3, Version 1 — Substack feed** — List the latest coding
  challenges from the Coding Challenges Substack feed. The page warns
  the Substack RSS feed does not include CORS headers, so a proxy is
  needed to fetch it from a web page.
- **Step 3, Version 2 — GitHub PRs (alternate, no proxy needed)** —
  Display all open PRs for the Shared Solutions GitHub repository, via
  `https://api.github.com/repos/CodingChallegesFYI/SharedSolutions/pulls`
  (spelling exactly as printed on the challenge page, including
  `CodingChallegesFYI`).
- **Going Further** — Extract more info from the dynamic elements
  (images/title/description); make the extension more generic (a daily
  quote, a customisable GitHub feed); package it for the Chrome Web
  Store.

## What this build does

- Manifest V3 extension, `chrome_url_overrides: { "newtab": "newtab.html" }`.
- New tab: blue `#04295B` background, centred `Coding Challenges>_`
  wordmark, live clock (updates every second) + human-friendly date
  (e.g. `Sunday, 25 October 2026`), a daily quote, and two dynamic
  panels: open GitHub PRs and latest Substack posts.
- GitHub panel: unauthenticated `api.github.com` fetch (no credentials,
  no token, no account needed). Repository is customisable from the
  on-page settings panel (default: the page's
  `CodingChallegesFYI/SharedSolutions`). Shows PR number, title, author,
  and link. Failures (network, rate limit, wrong repo name) render an
  honest error message in the panel, never fake PRs.
- Substack panel: RSS fetched through a user-configurable proxy URL
  (see Divergence D2). Shows post title, link, and publish date.
- Daily quote: built-in list, chosen deterministically by day-of-year
  (no network, no API key). This is the "generic daily quote" Going
  Further item, implemented offline on purpose.
- Settings panel on the new tab (gear button): GitHub owner/repo,
  Substack proxy URL, show/hide each section. Saved with
  `chrome.storage.sync` when available, falling back to `localStorage`
  so the page still works opened as a plain file for inspection.
- No background service worker is needed: the new-tab page itself does
  the fetching, which is all MV3 `host_permissions` covers.

## Deliberate divergences (honest, not silent)

- **D1 — Language exception (task-mandated).** Unlike other wave
  projects, the deliverable is the real extension source
  (manifest.json + HTML/CSS/JS), not Python, because a Chrome
  extension cannot be written in Python. A Python (stdlib-only) test
  harness under `tests/` statically validates the extension instead
  of being the product.
- **D2 — Substack proxy default.** The page says a proxy is required
  but names none. The default proxy is the public CORS proxy
  `https://api.allorigins.win/raw?url=` (no key, no account), used
  ONLY for the Substack RSS fetch, and it is editable/clearable in
  settings. If it is cleared, the panel attempts a direct fetch and,
  when that fails (expected CORS failure), shows an explanation
  instead of silently emptying. A third-party proxy is a dependency
  the user can replace; it is not presented as part of Substack.
- **D3 — GitHub repo spelling kept verbatim.** The default repo is
  `CodingChallegesFYI/SharedSolutions` exactly as printed on the
  challenge page. If GitHub returns 404 for that spelling, the panel
  shows the error and the user can correct the repo in settings; the
  code does not silently "fix" the spelling to a guessed name.
- **D4 — No Chrome Web Store packaging.** The extension is delivered
  as an unpacked-loadable directory with manual load steps in
  README.md. It is NOT published to the Web Store (that needs a
  developer account, review, and the user's own decision) and no
  store listing is claimed.
- **D5 — No real-browser load claim.** The extension was NOT loaded
  into a real Chrome browser in this environment (no live-browser
  tooling is available to this worker). Verification is the static
  test harness plus manual load steps. See TEST_PLAN.md.
- **D6 — Icons are simple placeholders.** `icons/icon*.png` are
  minimal generated PNGs (blue square with "CC") so the manifest's
  icon references resolve; they are not official Coding Challenges
  artwork.

## Explicitly NOT built

- Chrome Web Store publication / store listing (D4).
- Real-browser automated test (D5) — manual steps documented instead.
- Weather (Bonjourr-style): the challenge's own dynamic items are
  Substack + GitHub PRs, so no weather API/key is introduced.
- Accounts, sign-in, sync of personal data, or any credential handling:
  nothing in this extension asks for, stores, or sends a credential.
- Push notifications, alarms, or a background service worker: not
  required by any step.
- The "Going Further" image extraction for Substack posts: RSS item
  descriptions may contain HTML; only title/date/link are rendered
  (description HTML is deliberately not injected, to avoid injecting
  untrusted markup into the new-tab page).
