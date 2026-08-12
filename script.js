// Progressive enhancement only: the page is fully readable and navigable with
// JavaScript disabled. Two behaviours live here — the mobile menu and the
// copy buttons on the install commands.

(function () {
  "use strict";

  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");

  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.getAttribute("data-open") === "true";
      nav.setAttribute("data-open", String(!open));
      toggle.setAttribute("aria-expanded", String(!open));
    });

    // Following a link closes the menu; on desktop the attribute is inert.
    nav.addEventListener("click", function (event) {
      if (event.target.closest("a")) {
        nav.setAttribute("data-open", "false");
        toggle.setAttribute("aria-expanded", "false");
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && nav.getAttribute("data-open") === "true") {
        nav.setAttribute("data-open", "false");
        toggle.setAttribute("aria-expanded", "false");
        toggle.focus();
      }
    });
  }

  // "Lock this browser" forgets the gate and goes back to the coming-soon page.
  // It does not revoke anything — whoever has the address still has it — it just
  // stops this browser walking straight in.
  var lock = document.querySelector("[data-lock]");
  if (lock) {
    lock.addEventListener("click", function () {
      try {
        window.localStorage.removeItem("bitpoker.gate");
      } catch (error) {
        /* storage blocked: there was nothing remembered to forget */
      }
      window.location.replace("index.html");
    });
  }

  // Clipboard access needs a secure context; without it the button says so
  // rather than silently doing nothing, and the command stays selectable.
  document.querySelectorAll(".copy").forEach(function (button) {
    var source = document.getElementById(button.getAttribute("data-copy-target"));
    if (!source) return;

    button.addEventListener("click", function () {
      var done = function (label) {
        var original = "Copy";
        button.textContent = label;
        button.setAttribute("data-copied", "true");
        window.setTimeout(function () {
          button.textContent = original;
          button.removeAttribute("data-copied");
        }, 2000);
      };

      if (!navigator.clipboard) {
        done("Select it");
        return;
      }

      navigator.clipboard.writeText(source.textContent.trim()).then(
        function () { done("Copied"); },
        function () { done("Select it"); }
      );
    });
  });
})();
