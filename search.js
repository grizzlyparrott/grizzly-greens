// search.js (CREATE this file at repo root)
(function () {
  "use strict";

  var input = document.getElementById("siteSearch");
  var box = document.getElementById("searchResults");
  if (!input || !box) return;

  var indexItems = [];
  var ready = false;
  var active = -1;

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function norm(s) {
    return String(s || "").toLowerCase().trim();
  }

  function openBox() {
    box.classList.add("open");
  }

  function closeBox() {
    box.classList.remove("open");
    box.innerHTML = "";
    active = -1;
  }

  function renderEmpty() {
    box.innerHTML = '<div class="search-empty">No results found</div>';
    openBox();
  }

  function renderList(results) {
    var html = "";
    for (var i = 0; i < results.length; i++) {
      var r = results[i];
      html +=
        '<div class="search-item" role="option" data-u="' + escapeHtml(r.u) + '" data-i="' + i + '">' +
          '<div class="t">' + escapeHtml(r.t) + "</div>" +
          (r.d ? '<div class="d">' + escapeHtml(r.d) + "</div>" : "") +
        "</div>";
    }
    box.innerHTML = html;
    openBox();
    active = -1;
  }

  function setActive(i) {
    var items = box.querySelectorAll(".search-item");
    for (var k = 0; k < items.length; k++) items[k].classList.remove("active");
    if (i >= 0 && i < items.length) {
      items[i].classList.add("active");
      active = i;
    } else {
      active = -1;
    }
  }

  function goActive() {
    var items = box.querySelectorAll(".search-item");
    if (active < 0 || active >= items.length) return;
    var u = items[active].getAttribute("data-u");
    if (u) window.location.href = u;
  }

  function scoreItem(q, item) {
    // Simple, fast scoring: title hits first, then description
    var t = norm(item.t);
    var d = norm(item.d);
    if (!q) return -1;

    if (t === q) return 1000;
    if (t.indexOf(q) === 0) return 800;
    if (t.indexOf(q) !== -1) return 600;

    if (d && d.indexOf(q) !== -1) return 300;
    return -1;
  }

  function search(q) {
    q = norm(q);
    if (!q) {
      closeBox();
      return;
    }
    if (!ready) {
      box.innerHTML = '<div class="search-empty">Loading...</div>';
      openBox();
      return;
    }

    var scored = [];
    for (var i = 0; i < indexItems.length; i++) {
      var it = indexItems[i];
      var s = scoreItem(q, it);
      if (s >= 0) scored.push({ s: s, t: it.t, u: it.u, d: it.d });
    }

    scored.sort(function (a, b) {
      if (b.s !== a.s) return b.s - a.s;
      return a.t.localeCompare(b.t);
    });

    var top = scored.slice(0, 8);
    if (!top.length) renderEmpty();
    else renderList(top);
  }

  box.addEventListener("mousedown", function (e) {
    var el = e.target;
    while (el && el !== box && !el.classList.contains("search-item")) el = el.parentNode;
    if (!el || el === box) return;
    var u = el.getAttribute("data-u");
    if (u) window.location.href = u;
  });

  document.addEventListener("click", function (e) {
    if (e.target === input || box.contains(e.target)) return;
    closeBox();
  });

  input.addEventListener("input", function () {
    search(input.value);
  });

  input.addEventListener("keydown", function (e) {
    if (!box.classList.contains("open")) return;

    var items = box.querySelectorAll(".search-item");
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!items.length) return;
      var next = active + 1;
      if (next >= items.length) next = 0;
      setActive(next);
      return;
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!items.length) return;
      var prev = active - 1;
      if (prev < 0) prev = items.length - 1;
      setActive(prev);
      return;
    }

    if (e.key === "Enter") {
      // If something is highlighted, go there. Otherwise, do nothing.
      if (active >= 0) {
        e.preventDefault();
        goActive();
      }
      return;
    }

    if (e.key === "Escape") {
      closeBox();
    }
  });

  // Load index
  fetch("/search-index.json", { cache: "no-store" })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      indexItems = (data && data.items) ? data.items : [];
      ready = true;
    })
    .catch(function () {
      ready = false;
    });
})();
