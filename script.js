// Progressive enhancement only: the page is fully readable and navigable with
// JavaScript disabled. Three behaviours live here — the mobile menu, the copy
// buttons on the install commands, and the faucet form, which is the one thing
// on the page that cannot work without a script and so is hidden until one
// runs and finds a faucet to talk to.

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

  // "Lock this browser" forgets the way in — both the gate and the invitation
  // receipt the gate stored — and goes back to the door. It does not revoke
  // anything: whoever has the address or the code still has it. It just stops
  // this browser walking straight in.
  var lock = document.querySelector("[data-lock]");
  if (lock) {
    lock.addEventListener("click", function () {
      try {
        window.localStorage.removeItem("bitpoker.gate");
        window.localStorage.removeItem("bitpoker.invite");
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

  // ─────────────────────────────  the faucet  ─────────────────────────────
  //
  // The panel starts hidden and is revealed only once poker-faucetd answers,
  // so a deployment without one — or with one that is down — shows no form at
  // all rather than a button that fails when pressed.
  //
  // The invitation is usually already in hand: the gate stored a ticket when
  // the code was accepted, and that stands in for the code here. Visitors who
  // came in the other way (the passphrase) get the code field instead.

  var config = window.BITPOKER || {};
  var api = (config.api || "").replace(/\/+$/, "");
  var panel = document.querySelector("[data-faucet]");

  if (panel && api) {
    var form = panel.querySelector("[data-faucet-form]");
    var codeField = panel.querySelector("[data-faucet-code-field]");
    var codeInput = panel.querySelector("[data-faucet-code]");
    var addressInput = panel.querySelector("[data-faucet-address]");
    var submit = panel.querySelector("[data-faucet-submit]");
    var terms = panel.querySelector("[data-faucet-terms]");
    var invite = readInvite();

    fetch(api + "/v1/info", { headers: { Accept: "application/json" } })
      .then(function (response) { return response.json(); })
      .then(function (info) {
        if (!info || !info.ok) return;
        panel.hidden = false;
        terms.textContent = describe(info);

        // With a ticket in hand there is nothing to type; without one the
        // code is the only way to prove an invitation.
        if (!info.invite_required || (invite && invite.ticket)) {
          codeField.hidden = true;
        }
        if (info.paused) {
          submit.disabled = true;
          say("The faucet is between top-ups. Try again a little later.", "bad");
        }
      })
      .catch(function () {
        /* no faucet here: the panel stays hidden and the page reads as before */
      });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var address = addressInput.value.trim();
      if (!address) {
        say("Paste the address you want the chips sent to.", "bad");
        addressInput.focus();
        return;
      }

      var body = { address: address };
      if (invite && invite.ticket && codeField.hidden) {
        body.ticket = invite.ticket;
      } else if (codeInput.value.trim()) {
        body.code = codeInput.value.trim();
      }

      submit.disabled = true;
      submit.textContent = "Dealing…";
      say("Asking the faucet…");

      fetch(api + "/v1/faucet/claim", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      })
        .then(function (response) {
          return response.json().then(function (payload) {
            return { ok: response.ok && payload.ok, payload: payload };
          });
        })
        .then(function (result) {
          if (result.ok) {
            paid(result.payload);
          } else {
            refused(result.payload);
          }
        })
        .catch(function () {
          say("Could not reach the faucet. Try again in a moment.", "bad");
        })
        .then(function () {
          submit.disabled = false;
          submit.textContent = "Deal me in";
        });
    });

    // Group an invitation code as it is typed, exactly as the gate does.
    if (codeInput) {
      codeInput.addEventListener("input", function () {
        var stripped = codeInput.value.replace(/[\s\-_.]/g, "").toUpperCase();
        if (!/^[0-9A-Z]{0,12}$/.test(stripped)) return;
        var grouped = stripped.match(/.{1,4}/g);
        codeInput.value = grouped ? grouped.join("-") : "";
      });
    }
  }

  function readInvite() {
    try {
      return JSON.parse(window.localStorage.getItem("bitpoker.invite") || "null");
    } catch (error) {
      return null;
    }
  }

  function forgetInvite() {
    try {
      window.localStorage.removeItem("bitpoker.invite");
    } catch (error) {
      /* nothing was stored */
    }
  }

  function say(message, tone) {
    var note = document.querySelector("[data-faucet-note]");
    if (!note) return;
    note.innerHTML = message;
    note.className = "faucet-note" + (tone ? " " + tone : "");
  }

  function paid(payload) {
    var amount = chip(payload.amount_uchip);
    var message = "<b>" + amount + "</b> on the way.";
    if (payload.dry_run) {
      message = "Approved — but this faucet is in dry-run mode, so nothing was sent.";
    } else if (payload.tx_hash) {
      var explorer = (window.BITPOKER && window.BITPOKER.explorer) || "";
      var hash = payload.tx_hash;
      message += explorer
        ? ' <a href="' + explorer + "/pokerchain/tx/" + hash + '" rel="noopener noreferrer" target="_blank">See it on the explorer</a>.'
        : " <code>" + hash + "</code>";
    }
    say(message, "good");
  }

  function refused(payload) {
    var error = (payload && payload.error) || {};
    var message = error.message || "The faucet said no.";
    if (error.retry_after_seconds > 0) {
      message += " Try again in " + roughly(error.retry_after_seconds) + ".";
    }
    // A ticket the faucet will not honour is worse than no ticket: ask for the
    // code instead of letting every retry fail the same way.
    if (error.code === "ticket_invalid" || error.code === "invite_unknown") {
      forgetInvite();
      var field = document.querySelector("[data-faucet-code-field]");
      if (field) field.hidden = false;
    }
    say(message, "bad");
  }

  function describe(info) {
    var parts = [chip(info.grant_uchip) + " per claim"];
    if (info.address_cooldown_seconds > 0) {
      parts.push("one claim per address every " + roughly(info.address_cooldown_seconds));
    }
    parts.push(info.invite_required ? "invitation required" : "open to everyone");
    if (info.day_budget_uchip) {
      parts.push(chip(info.day_spent_uchip) + " of " + chip(info.day_budget_uchip) + " given out today");
    }
    return parts.join(" · ");
  }

  // uchip are integers; 1 CHIP is 1e6 of them. Kept in string arithmetic
  // rather than parseInt so a large balance cannot lose its last digits.
  function chip(uchip) {
    var digits = String(uchip || "0").replace(/[^0-9]/g, "") || "0";
    var padded = digits.length > 6 ? digits : new Array(7 - digits.length + 1).join("0") + digits;
    var whole = padded.slice(0, padded.length - 6);
    var fraction = padded.slice(padded.length - 6).replace(/0+$/, "");
    return (fraction ? whole + "." + fraction : whole) + " CHIP";
  }

  function roughly(seconds) {
    if (seconds < 90) return Math.max(1, Math.round(seconds)) + " seconds";
    if (seconds < 5400) return Math.round(seconds / 60) + " minutes";
    if (seconds < 172800) return Math.round(seconds / 3600) + " hours";
    return Math.round(seconds / 86400) + " days";
  }
})();
