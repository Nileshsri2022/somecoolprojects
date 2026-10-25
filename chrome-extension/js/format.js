// Pure helpers: no chrome.* APIs, no DOM. Safe to load in Node for tests.
(function (root) {
  var WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  var MONTHS = ["January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"];

  function pad(n) { return n < 10 ? "0" + n : String(n); }

  // 12-hour clock, e.g. "11:07:33 PM", "12:00:00 AM", "1:05:09 PM".
  function formatTime(date) {
    var h = date.getHours();
    var suffix = h >= 12 ? "PM" : "AM";
    var hour12 = h % 12;
    if (hour12 === 0) { hour12 = 12; }
    return hour12 + ":" + pad(date.getMinutes()) + ":" + pad(date.getSeconds()) + " " + suffix;
  }

  // Human-friendly date, e.g. "Sunday, 25 October 2026".
  function formatDate(date) {
    return WEEKDAYS[date.getDay()] + ", " + date.getDate() + " " +
      MONTHS[date.getMonth()] + " " + date.getFullYear();
  }

  // 1-based day of year (1 Jan -> 1; leap years handled by Date math).
  function dayOfYear(date) {
    var start = new Date(date.getFullYear(), 0, 0);
    return Math.floor((date - start) / 86400000);
  }

  function pickDailyQuote(quotes, date) {
    if (!quotes || quotes.length === 0) { return null; }
    return quotes[dayOfYear(date) % quotes.length];
  }

  function buildGitHubApiUrl(owner, repo) {
    return "https://api.github.com/repos/" + owner + "/" + repo +
      "/pulls?state=open&per_page=30";
  }

  function buildSubstackProxyUrl(proxyBase, feedUrl) {
    if (!proxyBase) { return feedUrl; }
    return proxyBase + encodeURIComponent(feedUrl);
  }

  // Map raw GitHub PR JSON to {number, title, author, url}. Non-array -> [].
  function parseGitHubPRs(json) {
    if (!Array.isArray(json)) { return []; }
    return json.map(function (pr) {
      return {
        number: pr && typeof pr.number === "number" ? pr.number : null,
        title: pr && typeof pr.title === "string" ? pr.title : "",
        author: pr && pr.user && typeof pr.user.login === "string" ? pr.user.login : "",
        url: pr && typeof pr.html_url === "string" ? pr.html_url : ""
      };
    });
  }

  var api = {
    formatTime: formatTime, formatDate: formatDate, dayOfYear: dayOfYear,
    pickDailyQuote: pickDailyQuote, buildGitHubApiUrl: buildGitHubApiUrl,
    buildSubstackProxyUrl: buildSubstackProxyUrl, parseGitHubPRs: parseGitHubPRs
  };
  // Browser: plain <script> globals. Node: module.exports for the harness.
  if (typeof module !== "undefined" && module.exports) { module.exports = api; }
  for (var k in api) { root[k] = api[k]; }
})(typeof globalThis !== "undefined" ? globalThis : this);
