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
window.BITPOKER = {
  api: "https://api.bitpk.top",
  explorer: "https://explorer.bitpk.top",
  webapp: "https://app.bitpk.top"
};
