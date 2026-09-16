// The content-page turnstile.
//
// Every fixed-name page runs this before anything renders. It lets a visitor
// through on either of two credentials:
//
//   the passphrase  — the verifier the gate (index.html + gate.js) stores on
//                     entry. This is the staff entrance: it still opens when
//                     the chain, the node or the explorer is down, and it is
//                     what tools/gate.py rotates.
//   a day pass      — proof that 0.1 CHIP reached the toll address, bought on
//                     pay.html and kept in localStorage until it expires.
//
// With no toll address configured (config.js), the day pass does not exist and
// the passphrase is the only door — which is exactly what the site did before
// the turnstile was added, so an unconfigured deployment loses nothing.
//
// Be clear about how little this is worth: it is weaker than the token page in
// front of it. The verifier ships in this file, the page names are guessed on
// the first try, and this check only runs in a browser — fetching any of these
// URLs with curl returns the whole page. It keeps the pages out of sight of a
// visitor poking at the site; it does not keep them out of reach of anyone at
// all. Treat everything on these pages as published to whoever knows the host.
// What the toll adds is not secrecy but a receipt: every entry bought this way
// is a transaction on chain, so who paid is auditable after the fact. For
// access control that holds, put the whole site behind an identity proxy —
// see README.
//
// The config block below is kept in lockstep with gate.js by tools/gate.py;
// rotating the passphrase rewrites both.

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
  var PASS_KEY = "bitpoker.pass";

  function stored(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      // Storage blocked: treat as nothing remembered. The gate still works
      // over the URL hash, and the toll can be paid again.
      return null;
    }
  }

  function toll() {
    var config = window.BITPOKER || {};
    var t = config.toll || {};
    return t.to && t.uchip ? t : null;
  }

  // A pass names the toll it paid ("community", or an address), so pointing
  // the site at a different destination invalidates every outstanding pass
  // without touching anything else.
  function hasDayPass(t) {
    var raw = stored(PASS_KEY);
    if (!raw) {
      return false;
    }
    try {
      var pass = JSON.parse(raw);
      return !!pass && pass.v === 1 && pass.to === t.to &&
        typeof pass.expires === "number" && pass.expires * 1000 > Date.now();
    } catch (error) {
      return false;
    }
  }

  function hasPassphrase() {
    return !!CONFIG.verifier && stored(STORE_KEY) === CONFIG.verifier;
  }

  var paid = toll();
  if (hasPassphrase() || (paid && hasDayPass(paid))) {
    return;
  }

  // Where to send them back to afterwards. Only a bare page name is carried
  // through — never a full URL, which would make this an open redirect on a
  // page that anyone can link to.
  var here = window.location.pathname.split("/").pop() || "";
  var next = /^[A-Za-z0-9._-]+\.html$/.test(here) ? here : "overview.html";

  window.location.replace(paid ? "pay.html?next=" + encodeURIComponent(next) : "index.html");
})();
