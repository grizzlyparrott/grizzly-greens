/* /search.js
   Body-level "portal" autocomplete so results always render above hero/sections.
*/
(function () {
  "use strict";

  var input =
    document.getElementById("siteSearch") ||
    document.getElementById("site-search") ||
    document.querySelector('input[type="search"]');

  if (!input) return;

  var items = [];
  var loaded = false;
  var activeIndex = -1;

  var box = document.createElement("div");
  box.className = "search-results search-results-portal";
  box.setAttribute("role", "listbox");
  box.style.display = "none";
  document.body.appendChild(box);

  function esc(s) {
    s = String(s == null ? "" : s);
    return s.replace(/[&<>"']/g, function (c) {
      return c === "&" ? "&amp;" :
             c === "<" ? "&lt;" :
             c === ">" ? "&gt;" :
             c === '"' ? "&quot;" : "&#39;";
    });
  }

  function placeBox() {
    var r = input.getBoundingClientRect();
    box.style.left = Math.round(r.left) + "px";
    box.style.top = Math.round(r.bottom + 8) + "px";
    box.style.width = Math.round(r.width) + "px";
  }

  function openBox() {
    placeBox();
    box.style.display = "block";
    box.classList.add("open");
  }

  function closeBox() {
    activeIndex = -1;
    box.classList.remove("open");
    box.style.display = "none";
    box.innerHTML = "";
  }

  function ensureLoaded(cb) {
    if (loaded) return cb();
    loaded = true;
    fetch("/search-index.json", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        items = (data && Array.isArray(data.items)) ? data.items : [];
        cb();
      })
      .catch(function () {
        items = [];
        cb();
      });
  }

  function score(q, t, d) {
    q = q.toLowerCase();
    t = (t || "").toLowerCase();
    d = (d || "").toLowerCase();
    if (!q) return 0;
    if (t === q) return 1000;
    if (t.indexOf(q) === 0) return 800;
    if (t.indexOf(q) !== -1) return 600;
    if (d.indexOf(q) !== -1) return 300;
    return 0;
  }

  function setActive(i) {
    var rows = box.querySelectorAll(".search-item");
    for (var k = 0; k < rows.length; k++) {
      rows[k].classList.toggle("active", k === i);
    }
    activeIndex = i;
  }

  function go(url) {
    if (!url) return;
    window.location.href = url;
  }

  function render(q) {
    q = (q || "").trim();
    if (!q) { closeBox(); return; }

    var ranked = [];
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      var s = score(q, it.t, it.d);
      if (s > 0) ranked.push({ s: s, it: it });
    }
    ranked.sort(function (a, b) { return b.s - a.s; });

    var top = ranked.slice(0, 10);
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

  box.addEventListener("mousedown", function (e) {
    var row = e.target && e.target.closest ? e.target.closest(".search-item") : null;
    if (!row) return;
    e.preventDefault();
    go(row.getAttribute("data-url"));
  });

  input.addEventListener("focus", function () {
    ensureLoaded(function () { render(input.value); });
  });

  input.addEventListener("input", function () {
    ensureLoaded(function () { render(input.value); });
  });

  input.addEventListener("keydown", function (e) {
    if (box.style.display !== "block") {
      if (e.key === "Enter") {
        ensureLoaded(function () { render(input.value); });
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
    if (e.target && e.target.closest && e.target.closest(".search-results-portal")) return;
    closeBox();
  });

  window.addEventListener("resize", function () {
    if (box.style.display === "block") placeBox();
  });

  document.addEventListener("scroll", function () {
    if (box.style.display === "block") placeBox();
  }, true);
})();
