// New-tab page wiring: clock, quote, settings, GitHub + Substack panels.
// All network-derived text is inserted via textContent, never as markup.
(function () {
  "use strict";

  var SUBSTACK_FEED = "https://codingchallenges.substack.com/feed";
  var DEFAULTS = {
    owner: "CodingChallegesFYI", // spelling exactly as on the challenge page
    repo: "SharedSolutions",
    proxy: "https://api.allorigins.win/raw?url=",
    showQuote: true, showGitHub: true, showSubstack: true
  };
  var STORE_KEY = "cc-newtab-settings";
  var settings = Object.assign({}, DEFAULTS);

  function $(id) { return document.getElementById(id); }

  function hasChromeStorage() {
    return typeof chrome !== "undefined" && chrome.storage && chrome.storage.sync;
  }

  function loadSettings(done) {
    if (hasChromeStorage()) {
      chrome.storage.sync.get(DEFAULTS, function (items) {
        settings = Object.assign({}, DEFAULTS, items);
        done();
      });
    } else {
      try {
        var raw = window.localStorage.getItem(STORE_KEY);
        if (raw) { settings = Object.assign({}, DEFAULTS, JSON.parse(raw)); }
      } catch (e) { /* fall back to defaults */ }
      done();
    }
  }

  function saveSettings() {
    if (hasChromeStorage()) {
      chrome.storage.sync.set(settings);
    } else {
      try { window.localStorage.setItem(STORE_KEY, JSON.stringify(settings)); } catch (e) { /* ignore */ }
    }
  }

  function tick() {
    var now = new Date();
    $("clock").textContent = formatTime(now);
    $("date").textContent = formatDate(now);
  }

  function renderQuote() {
    var block = $("quote-block");
    block.hidden = !settings.showQuote;
    if (!settings.showQuote) { return; }
    var q = pickDailyQuote(QUOTES, new Date());
    if (q) {
      $("quote").textContent = "\u201C" + q.text + "\u201D";
      $("quote-author").textContent = q.author;
    }
  }

  function renderList(listEl, items, emptyText) {
    listEl.textContent = "";
    if (items.length === 0) {
      var li = document.createElement("li");
      li.textContent = emptyText;
      listEl.appendChild(li);
      return;
    }
    items.forEach(function (item) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = item.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = item.title;
      li.appendChild(a);
      if (item.meta) {
        var meta = document.createElement("span");
        meta.className = "meta";
        meta.textContent = item.meta;
        li.appendChild(meta);
      }
      listEl.appendChild(li);
    });
  }

  function showError(el, message) {
    el.hidden = false;
    el.textContent = message;
  }

  function fetchGitHub() {
    var panel = $("github-panel");
    panel.hidden = !settings.showGitHub;
    if (!settings.showGitHub) { return; }
    $("github-repo-label").textContent = settings.owner + "/" + settings.repo;
    $("github-error").hidden = true;
    fetch(buildGitHubApiUrl(settings.owner, settings.repo),
      { headers: { "Accept": "application/vnd.github+json" } })
      .then(function (res) {
        if (!res.ok) { throw new Error("GitHub returned HTTP " + res.status); }
        return res.json();
      })
      .then(function (json) {
        var prs = parseGitHubPRs(json).filter(function (p) { return p.url; });
        renderList($("github-list"), prs.map(function (p) {
          return {
            title: (p.number !== null ? "#" + p.number + " " : "") + p.title,
            url: p.url,
            meta: p.author ? "by " + p.author : ""
          };
        }), "No open pull requests.");
      })
      .catch(function (err) {
        renderList($("github-list"), [], "");
        showError($("github-error"),
          "Could not load pull requests (" + err.message + "). " +
          "Check the repository name in Settings; unauthenticated GitHub " +
          "requests are also rate-limited.");
      });
  }

  function fetchSubstack() {
    var panel = $("substack-panel");
    panel.hidden = !settings.showSubstack;
    if (!settings.showSubstack) { return; }
    $("substack-error").hidden = true;
    var url = buildSubstackProxyUrl(settings.proxy, SUBSTACK_FEED);
    fetch(url)
      .then(function (res) {
        if (!res.ok) { throw new Error("Feed fetch returned HTTP " + res.status); }
        return res.text();
      })
      .then(function (xmlText) {
        var doc = new DOMParser().parseFromString(xmlText, "text/xml");
        var items = Array.prototype.slice.call(doc.querySelectorAll("item"), 0, 10);
        renderList($("substack-list"), items.map(function (item) {
          var title = item.querySelector("title");
          var link = item.querySelector("link");
          var pub = item.querySelector("pubDate");
          var d = pub ? new Date(pub.textContent) : null;
          return {
            title: title ? title.textContent : "(untitled)",
            url: link ? link.textContent.trim() : "#",
            meta: d && !isNaN(d) ? formatDate(d) : ""
          };
        }), "No posts found in the feed.");
      })
      .catch(function (err) {
        renderList($("substack-list"), [], "");
        var hint = settings.proxy
          ? "The proxy may be down or the feed unreachable."
          : "Direct Substack fetches are blocked by CORS (the feed sends no " +
            "CORS headers). Set a proxy URL in Settings to fetch it.";
        showError($("substack-error"), "Could not load the Substack feed (" + err.message + "). " + hint);
      });
  }

  function refreshPanels() { fetchGitHub(); fetchSubstack(); }

  function fillSettingsForm() {
    $("setting-owner").value = settings.owner;
    $("setting-repo").value = settings.repo;
    $("setting-proxy").value = settings.proxy;
    $("setting-show-quote").checked = !!settings.showQuote;
    $("setting-show-github").checked = !!settings.showGitHub;
    $("setting-show-substack").checked = !!settings.showSubstack;
  }

  document.addEventListener("DOMContentLoaded", function () {
    loadSettings(function () {
      tick();
      setInterval(tick, 1000);
      renderQuote();
      refreshPanels();
      fillSettingsForm();
    });

    $("settings-toggle").addEventListener("click", function () {
      var panel = $("settings-panel");
      panel.hidden = !panel.hidden;
      if (!panel.hidden) { fillSettingsForm(); }
    });

    $("settings-save").addEventListener("click", function () {
      settings.owner = $("setting-owner").value.trim() || DEFAULTS.owner;
      settings.repo = $("setting-repo").value.trim() || DEFAULTS.repo;
      settings.proxy = $("setting-proxy").value.trim();
      settings.showQuote = $("setting-show-quote").checked;
      settings.showGitHub = $("setting-show-github").checked;
      settings.showSubstack = $("setting-show-substack").checked;
      saveSettings();
      renderQuote();
      refreshPanels();
      $("settings-saved").hidden = false;
    });

    $("settings-reset").addEventListener("click", function () {
      settings = Object.assign({}, DEFAULTS);
      saveSettings();
      fillSettingsForm();
      renderQuote();
      refreshPanels();
      $("settings-saved").hidden = false;
    });
  });
})();
