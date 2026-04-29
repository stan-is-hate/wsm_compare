// Click-to-sort for tables marked <table class="sortable">.
// Detects numeric vs text columns from cell content, toggles direction on
// repeat clicks, and pushes DNS rows to the bottom of numeric columns.
(function () {
  function sortValue(cell, mode) {
    if (cell.dataset.sort !== undefined) {
      return mode === "number" ? parseFloat(cell.dataset.sort) : cell.dataset.sort.toLowerCase();
    }
    var txt = cell.textContent.trim();
    if (mode === "number") {
      if (txt.startsWith("DNS") || txt === "—" || txt === "") return Infinity;
      var m = txt.match(/-?\d+(?:\.\d+)?/);
      return m ? parseFloat(m[0]) : Infinity;
    }
    return txt.toLowerCase();
  }

  function detectMode(rows, idx) {
    var seenAny = false;
    for (var i = 0; i < rows.length; i++) {
      var c = rows[i].cells[idx];
      if (!c) continue;
      var t = c.textContent.trim();
      if (!t || t.startsWith("DNS")) continue;
      seenAny = true;
      if (!/^\s*-?\d/.test(t) && !/^T\d/.test(t)) return "text";
    }
    return seenAny ? "number" : "text";
  }

  function attach(table) {
    var thead = table.tHead;
    if (!thead) return;
    var headers = thead.querySelectorAll("th");
    headers.forEach(function (th, idx) {
      th.style.cursor = "pointer";
      th.addEventListener("click", function () {
        var dir = th.dataset.sortDir === "asc" ? "desc" : "asc";
        for (var b = 0; b < table.tBodies.length; b++) {
          var tbody = table.tBodies[b];
          var rows = Array.prototype.slice.call(tbody.rows);
          var mode = detectMode(rows, idx);
          rows.sort(function (a, b) {
            var av = sortValue(a.cells[idx], mode);
            var bv = sortValue(b.cells[idx], mode);
            if (av < bv) return dir === "asc" ? -1 : 1;
            if (av > bv) return dir === "asc" ? 1 : -1;
            return 0;
          });
          rows.forEach(function (r) { tbody.appendChild(r); });
        }
        headers.forEach(function (h) {
          h.classList.remove("sort-asc", "sort-desc");
          delete h.dataset.sortDir;
        });
        th.dataset.sortDir = dir;
        th.classList.add("sort-" + dir);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("table.sortable").forEach(attach);
  });
})();
