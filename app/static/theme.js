(function () {
  var key = "skilldock-theme";
  function apply(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(key, theme);
    } catch (e) {}
  }
  var stored = null;
  try {
    stored = localStorage.getItem(key);
  } catch (e) {}
  if (stored !== "dark" && stored !== "light") {
    stored =
      window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
  }
  apply(stored);
  document.addEventListener("click", function (e) {
    var t = e.target && e.target.closest && e.target.closest("[data-theme-toggle]");
    if (!t) return;
    var cur = document.documentElement.getAttribute("data-theme") || "light";
    apply(cur === "dark" ? "light" : "dark");
  });
})();
