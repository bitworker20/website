// The content-page guard.
//
// The gate (index.html + gate.js) is the only page that knows how to *open*
// the site. Every other page in here is a documentation page with a fixed,
// guessable name, so each one runs this check before showing anything: if
// this browser has not been through the gate — localStorage does not hold
// the verifier the gate stores on entry — bounce back to the door.
//
// Be clear about how little this is worth: it is weaker than the token
// page in front of it. The verifier is not secret (it ships in this file),
// the page names are guessed on the first try, and the check only runs in
// a browser — fetching any of these URLs with curl returns the whole page.
// It keeps the pages out of sight of a visitor poking at the site; it does
// not keep them out of reach of anyone at all. Treat everything on these
// pages as published to whoever knows the host. For access control that
// holds, put the whole site behind an identity proxy — see README.
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

  var passed = false;
  try {
    passed = !!CONFIG.verifier && window.localStorage.getItem(STORE_KEY) === CONFIG.verifier;
  } catch (error) {
    /* storage blocked: treat as not passed — the gate still works over URL */
  }

  if (!passed) {
    window.location.replace("index.html");
  }
})();
