// The coming-soon gate.
//
// The passphrase is never stored here. PBKDF2 stretches it into two halves: one
// the gate compares against (so a wrong guess fails locally, silently, with no
// request that could confirm a near miss), and one that *is* the filename of
// the real page. Nothing here names that page, and nothing links to it — the
// passphrase is the address.
//
// Rotate it with tools/gate.py; see that file for what this does and does not
// protect against.

(function () {
  "use strict";

  /* gate:config */ var CONFIG = {
      "salt": "71651cb87e61df4d993b4a6866fd0dbc",
      "iterations": 250000,
      "length": 12,
      "verifier": "c31f973a89eb8315c4e4edf2e21cb40d",
      "target": "1d191d99475b63e3.html"
  };

  var STORE_KEY = "bitpoker.gate";
  var subtle = window.crypto && window.crypto.subtle;

  function hexToBytes(hex) {
    var out = new Uint8Array(hex.length / 2);
    for (var i = 0; i < out.length; i++) {
      out[i] = parseInt(hex.substr(i * 2, 2), 16);
    }
    return out;
  }

  function bytesToHex(bytes) {
    var out = "";
    for (var i = 0; i < bytes.length; i++) {
      out += (bytes[i] < 16 ? "0" : "") + bytes[i].toString(16);
    }
    return out;
  }

  // Constant-time-ish compare. The attack this matters against is not really
  // available in a browser, but the habit costs nothing.
  function equal(a, b) {
    if (a.length !== b.length) return false;
    var diff = 0;
    for (var i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
    return diff === 0;
  }

  function derive(passphrase) {
    var bytes = new TextEncoder().encode(passphrase);
    return subtle
      .importKey("raw", bytes, "PBKDF2", false, ["deriveBits"])
      .then(function (key) {
        return subtle.deriveBits(
          {
            name: "PBKDF2",
            salt: hexToBytes(CONFIG.salt),
            iterations: CONFIG.iterations,
            hash: "SHA-256"
          },
          key,
          192
        );
      })
      .then(function (bits) {
        var all = bytesToHex(new Uint8Array(bits));
        return { verifier: all.slice(0, 32), token: all.slice(32) };
      });
  }

  function enter() {
    try {
      window.localStorage.setItem(STORE_KEY, CONFIG.verifier);
    } catch (error) {
      /* private mode: the visit still works, it just will not be remembered */
    }
    window.location.replace(CONFIG.target);
  }

  function attempt(passphrase) {
    if (!subtle || !CONFIG.verifier) return Promise.resolve(false);
    return derive(passphrase).then(function (derived) {
      if (!equal(derived.verifier, CONFIG.verifier)) return false;
      enter();
      return true;
    });
  }

  // A browser that has been through the gate before goes straight in.
  try {
    if (window.localStorage.getItem(STORE_KEY) === CONFIG.verifier && CONFIG.verifier) {
      window.location.replace(CONFIG.target);
      return;
    }
  } catch (error) {
    /* storage blocked — fall through to the knock */
  }

  document.addEventListener("DOMContentLoaded", function () {
    var mark = document.querySelector("[data-knock]");
    var field = document.querySelector("[data-knock-field]");
    var busy = false;

    // One PBKDF2 run takes long enough that a fast typist can finish the
    // passphrase while the previous keystroke is still being checked. Dropping
    // those would mean the correct suffix is never tested, so the newest
    // candidate waits its turn instead.
    var pending = null;

    function tryPassphrase(value) {
      if (!value) return;
      if (busy) {
        pending = value;
        return;
      }
      busy = true;
      attempt(value).then(
        function (ok) {
          busy = false;
          if (!ok && field) {
            // No message: a failure and an idle page look the same.
            field.value = "";
          }
          var next = pending;
          pending = null;
          if (!ok && next && next !== value) tryPassphrase(next);
        },
        function () {
          busy = false;
          pending = null;
        }
      );
    }

    // A link can carry it: /#passphrase — handy for sending someone in.
    if (window.location.hash.length > 1) {
      var fromHash = decodeURIComponent(window.location.hash.slice(1));
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, "", window.location.pathname);
      }
      tryPassphrase(fromHash);
    }

    // On a keyboard: just type it. Nothing echoes, nothing is focused.
    var buffer = "";
    document.addEventListener("keydown", function (event) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (document.activeElement === field) return;
      if (event.key.length !== 1) return;
      buffer = (buffer + event.key).slice(-64);
      if (CONFIG.length && buffer.length >= CONFIG.length) {
        tryPassphrase(buffer.slice(-CONFIG.length));
      }
    });

    // On a phone there is no keyboard to type into, so five taps on the mark
    // bring up a field. Five, because nobody taps a logo five times by accident.
    if (mark && field) {
      var taps = 0;
      var timer = null;
      mark.addEventListener("click", function () {
        taps += 1;
        window.clearTimeout(timer);
        timer = window.setTimeout(function () { taps = 0; }, 2000);
        if (taps >= 5) {
          taps = 0;
          field.hidden = false;
          field.focus();
        }
      });

      field.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          tryPassphrase(field.value.trim());
        }
      });
    }
  });
})();
