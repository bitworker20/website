// Deployment configuration for both pages.
//
// One file, loaded by the gate and by the site, so an operator points this
// deployment at its services in one place. Everything here is public by
// construction — it ships in the page — so nothing secret belongs in it.
//
// api: where poker-faucetd answers. It validates invitation codes and pays out
//      testnet chips. Leave it empty and the site still works: the gate then
//      opens only for the passphrase (see gate.js) and the faucet section
//      hides itself rather than offering a button that cannot work.
//
// toll: what a day pass costs and where it is paid (pay.js, turnstile.js).
//      `to: "community"` funds the chain's community pool — nobody holds it,
//      nobody can quietly spend it, and it takes no account to maintain, so
//      there is nothing to configure and nothing to sweep. An xpoker address
//      instead makes the toll a plain transfer to that account. Empty
//      switches the turnstile off: the passphrase gate becomes the only door
//      again, which is what the site did before the toll existed. Changing
//      the destination invalidates every outstanding pass, because a pass
//      names the toll it paid.
//
// chainRest: LCD endpoints tried in order. The explorer already proxies one
//      at /rest, which is why nothing new has to be deployed to read the
//      chain — but it is a different origin, so it must answer with
//      `Access-Control-Allow-Origin: https://bitpk.top` or the browser drops
//      the reply (see README, "Paying the toll"). The loopback entry is the
//      fallback for a visitor running their own node with CORS enabled.
window.BITPOKER = {
  api: "https://api.bitpk.top",
  explorer: "https://explorer.bitpk.top",
  webapp: "https://app.bitpk.top",
  toll: {
    to: "community",
    uchip: 100000,
    hours: 24
  },
  chainRest: [
    "https://explorer.bitpk.top/rest",
    "http://127.0.0.1:1317"
  ]
};
