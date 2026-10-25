# DESIGN — Chrome Extension (new-tab override)

## Files

```
chrome-extension/
  manifest.json          MV3 manifest (newtab override, permissions)
  newtab.html            New-tab page markup
  css/newtab.css         All styling (Coding Challenges Blue theme)
  js/format.js           Pure, browser-independent helpers (no chrome.*,
                         no DOM): formatTime, formatDate, dayOfYear,
                         pickDailyQuote, parseGitHubPRs, buildGitHubApiUrl,
                         buildSubstackProxyUrl
  js/newtab.js           Page wiring: clock tick, quote, settings
                         (chrome.storage.sync w/ localStorage fallback),
                         GitHub + Substack fetching + rendering
  js/quotes.js           Built-in daily-quote list (no network)
  icons/icon16.png, icon48.png, icon128.png   Placeholder icons
  tests/test_extension.py  Python stdlib harness (see TEST_PLAN.md)
  docs/SPEC.md, docs/DESIGN.md, docs/TEST_PLAN.md
  README.md
```

## Manifest (MV3)

- `manifest_version: 3`, `name: "Coding Challenges New Tab"`,
  `version: "1.0"`, `description` stating what it does.
- `chrome_url_overrides: { "newtab": "newtab.html" }` — this is the
  whole Step 1 mechanism: Chrome replaces the new tab with our page.
- `permissions: ["storage"]` (settings only).
- `host_permissions`: `https://api.github.com/*` and
  `https://api.allorigins.win/*` (the default Substack proxy). The
  Substack origin itself is NOT listed because the fetch goes through
  the proxy; if the user sets a different proxy, they must add that
  host to `host_permissions` themselves (documented in README.md).
- `icons` + `action.default_title` (a toolbar tooltip; the extension
  has no popup because its UI is the new tab itself).

## Page layout (newtab.html)

Centred column on `#04295B`:

1. `Coding Challenges>_` wordmark (white, monospace; the trailing `_`
   blinks via CSS animation — a cursor, not a typo).
2. Clock (`#clock`, large) + date (`#date`, human-friendly) below it.
3. Daily quote (`#quote` + `#quote-author`).
4. Two panels side-by-side on wide screens, stacked on narrow ones:
   - `#github-panel`: "Open pull requests" + repo label + list/error.
   - `#substack-panel`: "Latest coding challenges" + list/error.
5. Gear button (`#settings-toggle`) opening `#settings-panel` with
   inputs for GitHub owner, GitHub repo, Substack proxy URL, and
   checkboxes to show/hide the quote and each panel. Save writes
   settings; Reset restores defaults.

All dynamic text is inserted via `textContent` (never `innerHTML`
with network data), except links whose `href` comes from the API
response and whose text is set via `textContent`.

## Clock and date

- `formatTime(date)` → 12-hour `H:MM:SS AM/PM` (e.g. `11:07:33 PM`),
  zero-padded minutes/seconds, no zero-padding on the hour.
- `formatDate(date)` → `Weekday, D Month YYYY`
  (e.g. `Sunday, 25 October 2026`), using English weekday/month names
  from fixed arrays (not locale-dependent `toLocaleDateString`, so the
  output is deterministic and testable).
- `setInterval(tick, 1000)` in `newtab.js`; `tick()` also re-renders
  the date in case midnight passes while the tab is open.

## Daily quote

- `quotes.js` exports `QUOTES` (array of `{text, author}`).
- `pickDailyQuote(quotes, date)` picks `quotes[dayOfYear(date) %
  quotes.length]` — same quote all day, changes daily, no network.

## GitHub PRs (Step 3 Version 2)

- URL: `https://api.github.com/repos/{owner}/{repo}/pulls?state=open&per_page=30`
  built by `buildGitHubApiUrl(owner, repo)`.
- `parseGitHubPRs(json)` maps each PR to `{number, title, author,
  url}` using only `number`, `title`, `user.login`, `html_url`.
  Non-array input → `[]`. Missing fields degrade to `""`/`null`
  rather than throwing, and the renderer skips entries without a URL.
- Unauthenticated: subject to GitHub's unauthenticated rate limit
  (60/hour/IP). A 403/404 renders the status in the panel; the user
  can change the repo in settings. No token field exists, by design
  (no credentials are ever requested).

## Substack feed (Step 3 Version 1)

- RSS URL: `https://codingchallenges.substack.com/feed`.
- Default fetch: `buildSubstackProxyUrl(proxyBase, feedUrl)` →
  `proxyBase + encodeURIComponent(feedUrl)`.
- The response XML is parsed with `DOMParser` in `newtab.js` and up
  to 10 `<item>`s are rendered (title, link, `pubDate` → short date).
  Item descriptions are NOT rendered (see SPEC D-note: no untrusted
  HTML injection).
- If the proxy setting is empty, a direct fetch is attempted; its
  expected CORS failure is caught and rendered as an explanatory
  message telling the user to set a proxy.

## Settings storage

- `loadSettings()` / `saveSettings()` in `newtab.js`: prefer
  `chrome.storage.sync` (guarded by `typeof chrome !== "undefined"`),
  fall back to `localStorage` key `cc-newtab-settings`. Defaults:
  `{ owner: "CodingChallegesFYI", repo: "SharedSolutions",
     proxy: "https://api.allorigins.win/raw?url=",
     showQuote: true, showGitHub: true, showSubstack: true }`.
- Settings changes re-fetch both panels immediately.

## Why no service worker / popup / content script

None is needed: the new-tab page is a full page with its own JS, and
host permissions let that page fetch directly. Adding a worker would
be speculative code (against the project's smallest-change rule).
