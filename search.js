/* /search.js
   Site search autocomplete for GrizzlyGreens.net
   - Loads /search-index.json
   - Accepts either {items:[...]} or a bare array
   - Normalizes fields to {t,d,u}
   - Renders to #searchResults if present, else uses a body-level portal box
*/
(function () {
  "use strict";

  // ---------- Find input ----------
  var input =
    document.getElementById("siteSearch") ||
    document.getElementById("site-search") ||
    document.querySelector('input[type="search"]');

  if (!input) return;

  // ---------- Optional inline results container ----------
  var inlineBox = document.getElementById("searchResults") || null;

  // ---------- State ----------
  var items = [];
  var loaded = false;
  var loading = false;
  var activeIndex = -1;
  var open = false;

  // ---------- Portal box (fallback / preferred for overlay) ----------
  var portalBox = document.createElement("div");
  portalBox.className = "search-results search-results-portal";
  portalBox.setAttribute("role", "listbox");
  portalBox.style.display = "none";
  document.body.appendChild(portalBox);

  function getBox() {
    return inlineBox || portalBox;
  }

  // ---------- Helpers ----------
  function esc(s) {
    s = String(s == null ? "" : s);
    return s.replace(/[&<>"']/g, function (c) {
      return c === "&" ? "&amp;" :
             c === "<" ? "&lt;" :
             c === ">" ? "&gt;" :
             c === '"' ? "&quot;" : "&#39;";
    });
  }

  function normUrl(u) {
    u = String(u == null ? "" : u).trim();
    if (!u) return "/";
    return u;
  }

  function placePortal() {
    if (inlineBox) return; // inline container controls its own layout
    var r = input.getBoundingClientRect();
    portalBox.style.left = Math.round(r.left) + "px";
    portalBox.style.top = Math.round(r.bottom + 8) + "px";
    portalBox.style.width = Math.round(r.width) + "px";
  }

  function openBox() {
    var box = getBox();
    if (!inlineBox) placePortal();
    box.style.display = "block";
    box.classList.add("open");
    open = true;

    input.setAttribute("aria-expanded", "true");
    input.setAttribute("aria-controls", inlineBox ? "searchResults" : "");
  }

  function closeBox() {
    var box = getBox();
    activeIndex = -1;
    open = false;

    box.classList.remove("open");
    box.style.display = "none";
    box.innerHTML = "";

    input.setAttribute("aria-expanded", "false");
  }

  function go(url) {
    url = normUrl(url);
    if (!url) return;
    window.location.href = url;
  }

  function normalizeData(data) {
    var raw = [];

    if (data && Array.isArray(data.items)) raw = data.items;
    else if (Array.isArray(data)) raw = data;

    // Normalize each entry to {t,d,u}
    var out = [];
    for (var i = 0; i < raw.length; i++) {
      var x = raw[i];
      if (!x) continue;

      var t = x.t || x.title || x.name || x.h1 || "";
      var d = x.d || x.description || x.desc || x.snippet || x.summary || "";
      var u = x.u || x.url || x.href || x.path || x.link || "";

      t = String(t == null ? "" : t).trim();
      d = String(d == null ? "" : d).trim();
      u = normUrl(u);

      if (!t || !u) continue;

      out.push({ t: t, d: d, u: u });
    }
    return out;
  }

  function ensureLoaded(cb) {
    if (loaded) return cb();
    if (loading) return cb(); // avoid repeated fetch spam
    loading = true;

    fetch("/search-index.json", { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status + " loading /search-index.json");
        return r.json();
      })
      .then(function (data) {
        items = normalizeData(data);
        loaded = true;
        loading = false;

        // Helpful debug signal
        if (!items.length) {
          console.warn("Search index loaded but contains 0 items. Check JSON shape/keys.");
        }
        cb();
      })
      .catch(function (err) {
        items = [];
        loaded = true;
        loading = false;

        console.error("Search index failed to load:", err);
        cb();
      });
  }

  function score(q, t, d) {
    q = q.toLowerCase();
    t = (t || "").toLowerCase();
    d = (d || "").toLowerCase();

    if (!q) return 0;

    // Strong title matches
    if (t === q) return 1000;
    if (t.indexOf(q) === 0) return 850;
    if (t.indexOf(q) !== -1) return 650;

    // Weaker description matches
    if (d.indexOf(q) !== -1) return 300;

    return 0;
  }

  function setActive(i) {
    var box = getBox();
    var rows = box.querySelectorAll(".search-item");
    for (var k = 0; k < rows.length; k++) {
      rows[k].classList.toggle("active", k === i);
    }
    activeIndex = i;
  }

  function render(q) {
    q = String(q == null ? "" : q).trim();
    if (!q) {
      closeBox();
      return;
    }

    var ranked = [];
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      var s = score(q, it.t, it.d);
      if (s > 0) ranked.push({ s: s, it: it });
    }

    ranked.sort(function (a, b) { return b.s - a.s; });

    var top = ranked.slice(0, 10);
    var box = getBox();

    if (top.length === 0) {
      box.innerHTML = '<div class="search-empty">No results found.</div>';
      openBox();
      return;
    }

    var html = "";
    for (var j = 0; j < top.length; j++) {
      var r = top[j].it;
      var t = esc(r.t);
      var d = esc(r.d || "");
      var u = esc(r.u || "/");

      html += '<div class="search-item" role="option" data-url="' + u + '">';
      html += '<div class="t">' + t + "</div>";
      if (d) html += '<div class="d">' + d + "</div>";
      html += "</div>";
    }

    box.innerHTML = html;
    setActive(-1);
    openBox();
  }

  // ---------- Events ----------
  getBox().addEventListener("mousedown", function (e) {
    var box = getBox();
    var row = e.target && e.target.closest ? e.target.closest(".search-item") : null;
    if (!row) return;
    if (box === portalBox) e.preventDefault(); // keep focus stable
    go(row.getAttribute("data-url"));
  });

  input.addEventListener("focus", function () {
    ensureLoaded(function () { render(input.value); });
  });

  input.addEventListener("input", function () {
    ensureLoaded(function () { render(input.value); });
  });

  input.addEventListener("keydown", function (e) {
    var box = getBox();
    var isOpen = open && box.style.display === "block";

    if (!isOpen) {
      if (e.key === "Enter") {
        ensureLoaded(function () { render(input.value); });
      }
      if (e.key === "Escape") {
        closeBox();
      }
      return;
    }

    var rows = box.querySelectorAll(".search-item");

    if (e.key === "Escape") {
      closeBox();
      input.blur();
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!rows.length) return;
      var next = activeIndex + 1;
      if (next >= rows.length) next = rows.length - 1;
      setActive(next);
      return;
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!rows.length) return;
      var prev = activeIndex - 1;
      if (prev < 0) prev = 0;
      setActive(prev);
      return;
    }

    if (e.key === "Enter") {
      e.preventDefault();
      if (!rows.length) return;
      var pick = activeIndex >= 0 ? rows[activeIndex] : rows[0];
      if (pick) go(pick.getAttribute("data-url"));
      return;
    }
  });

  document.addEventListener("mousedown", function (e) {
    if (e.target === input) return;
    if (e.target && e.target.closest && e.target.closest(".search-results")) return;
    closeBox();
  });

  window.addEventListener("resize", function () {
    if (!inlineBox && portalBox.style.display === "block") placePortal();
  });

  document.addEventListener("scroll", function () {
    if (!inlineBox && portalBox.style.display === "block") placePortal();
  }, true);
})();
