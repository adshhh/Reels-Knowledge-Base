// Keyboard shortcuts for the holdout labelling page (speed matters: PLAN.md §7 budgets this
// at ~1 hour, and it's the owner's critical path). No-op on any page without these elements.
(function () {
  "use strict";

  function isTypingTarget(el) {
    if (!el) return false;
    const tag = el.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
  }

  document.addEventListener("keydown", function (e) {
    if (isTypingTarget(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;

    if (/^[1-9]$/.test(e.key)) {
      const btn = document.querySelector('.cat-btn[data-key="' + e.key + '"]');
      if (btn) {
        e.preventDefault();
        btn.click();
      }
      return;
    }

    if (e.key === "0" || e.key === "s") {
      const skip = document.getElementById("skip-link");
      if (skip) {
        e.preventDefault();
        skip.click();
      }
      return;
    }

    if (e.key === "b" || e.key === "ArrowLeft") {
      const back = document.getElementById("back-link");
      if (back) {
        e.preventDefault();
        back.click();
      }
      return;
    }

    if (e.key === "ArrowRight") {
      const next = document.getElementById("next-link");
      if (next) {
        e.preventDefault();
        next.click();
      }
    }
  });
})();
