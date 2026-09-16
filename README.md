# BitPoker internal engineering site

The internal technical reference for the people who build and run BitPoker:
what the system is, how a hand actually works, why each layer is shaped the
way it is, and what happened when the design met real networks.

Rewritten in September 2026 from the public marketing homepage into an
internal multi-page reference. It keeps the original's constraints — one
stylesheet, no framework, no build step, no bundler — and adds a
documentation shell (sticky TOC, prose measure, callouts, definition
tables, pipeline lists). Content is sourced from
`docs/whitepaper/bitpoker-whitepaper.md` and the ADRs in
`bitpoker/docs/adr/`; where the site and the code disagree, the code is
right and the page is stale.

**The site is invitation only** — see "The invitation gate" below.
`index.html` is the gate; the real site starts at the token page and
continues onto fixed-name pages behind `turnstile.js`, which takes either
the site's passphrase or a day pass bought by paying a toll on chain
("Paying the toll" below).

```
index.html          the invitation gate (self-contained: inline CSS, no hints)
gate.js             both doors: an invitation code, or the site's passphrase
turnstile.js        the content-page check: passphrase or a paid day pass
pay.html            the toll booth (self-contained, outside the turnstile)
pay.js              buys a day pass: challenge, payment, chain check
config.js           the faucet, the explorer, the web client, and the toll
<token>.html        the token page — a stub that forwards to overview.html
overview.html       the landing page: the claim, the architecture, the map
crypto.html         FourQ, joint keys, Barnett–Smart, Neff NIZK, cardkeys,
                  the signed message chain, the RNG problem
protocol.html       coroutine lifecycle, sans-IO state machines, the
                  community-card core, settlement transcript, resync
chain.html          intents, escrow, session lifecycle, the liveness
                  invariant, escalation, governance params, the gas table
adjudication.html   why determinism is the whole problem, the three-layer
                  guard, the pipeline, verdicts and fees, triggers
relay.html          why relays, connection establishment, assignment–
                  answer, service proof, bond and the capped fee market
operations.html     the verification matrix, WASM staging trap,
                  coordinated upgrades, packaging, command reference
lessons.html        the scar tissue: eight failures and the rules they left,
                  plus the open problems stated plainly
testnet.html        how to get on the testnet: client downloads, the browser
                  client, the explorer, how test chips are issued
styles.css          the site's stylesheet (shared by every page)
script.js           mobile menu, copy buttons, "lock this browser"
install.sh          the one-line server installer (kept for ops; no longer
                    advertised on the pages)
robots.txt          disallow everything, all pages
tools/gate.py       rotate the passphrase, inspect or check the current one
assets/             brand marks, favicons, social cards, whitepaper PDF
assets/screenshots/ real captures of the Qt desktop client
tests/test_site.py  contract suite
```

## The page model: one unguessable door, fixed rooms behind it

The gate's address must be unguessable, but cross-page links must be fixed
names that survive a passphrase rotation. Those two requirements conflict,
and the token page is the seam:

- The gate derives the token and lands on `<token>.html`, which is a stub
  that immediately forwards to `overview.html`.
- Every real page has a fixed name (`crypto.html`, `chain.html`, …) and
  starts with `turnstile.js`, which lets the visitor through on either the
  verifier the gate stores on entry or an unexpired day pass. Neither →
  the toll booth, or the door when no toll is configured.
- Rotating the passphrase renames only the stub and rewrites the config
  block in `gate.js` **and** `turnstile.js` together — the fixed pages
  never move, so no link inside the site ever breaks.

`turnstile.js` is **weaker than the token page it sits behind, and it is
the only thing in front of every page except the stub.** A name like
`overview.html` is not stumbled upon, it is guessed on the first try, and
the turnstile only runs in a browser: `curl https://<host>/overview.html`
returns the whole page whatever localStorage holds. So the token page's
name is the one real secret here, and it protects nothing but itself —
everything written on the other pages should be read as published to
anyone who knows the host. For access control that actually holds, put the
whole site behind HTTP basic auth or an identity proxy (Cloudflare Access,
oauth2-proxy) and drop the gate. This is a locked door on a building with
no walls.

## Paying the toll

0.1 CHIP buys 24 hours. `pay.html` shows where the toll goes, the amount,
a twelve-character challenge and a ready-made command; the visitor pays
**with the challenge in the memo**, pastes the transaction hash, and
`pay.js` reads the transaction back out of the chain. A pass is then kept
in `localStorage` until it expires, a day from the block time of the
payment — not from when it was checked.

**The toll funds the chain's community pool**, which is why there is no
address to configure and none to sweep: no account holds it, and nothing
leaves it without a governance proposal. So "who is collecting this?" has
an answer nobody has to be trusted for. The command the booth hands over is

```sh
pokerchaind tx distribution fund-community-pool 100000uchip --note <CHALLENGE> --from <key>
```

Setting `toll.to` to an `xpoker1…` address instead makes the toll an
ordinary transfer to that account, and the booth hands over a
`tx bank send` command. Each destination refuses the other's payment:
funding the pool does not open a site whose toll goes to an account.
Note that a plain transfer to the community pool's *module account* is not
a third option — the chain blocks sends to module accounts outright
(`app.BlockedAddresses`), which is the good failure: the alternative would
be coins that leave the payer, land in the module account, and are never
counted in the pool.

Four things must all hold, and each one is a way this would otherwise be
wrong:

| | |
|---|---|
| `tx_response.code == 0` | Inclusion in a block is not execution. A failed transfer moves nothing, and this is the third place in the tree where trusting the wrong field has cost money (PC-E2E-013, ADR-008 §2.6). |
| memo matches the challenge | Every payment to the toll is public the moment it lands. Without the memo, anyone watching the chain could take someone else's payment for their own pass. |
| ≥ the configured amount, in `uchip`, **in messages that reach this toll** (`MsgFundCommunityPool`, or `MsgSend` to the configured address) | One transaction can carry several messages and several coins; only what actually reached the toll counts. |
| an endpoint answered at all | If nothing did, or the node is still catching up, the card stays face down and the note says the chain could not be read. Telling someone who just paid that they did not is the one failure this page must not have. |

**What this needs from the deployment.** `config.js` carries `toll.to`
(`"community"`, an address, or empty — which switches the turnstile off and
leaves the passphrase as the only door, exactly as before) and
`chainRest`, the LCD endpoints tried in order. The
explorer already proxies one at `/rest`, so nothing new has to be deployed
to read the chain — but it is a different origin, so that proxy must answer
with `Access-Control-Allow-Origin: https://bitpk.top` or the browser drops
the reply. That is one `add_header` line in the explorer's nginx site, and
it is the only server-side change the toll needs. The loopback entry after
it is the fallback for a reader running their own node with CORS enabled.

**What the toll is for.** Not secrecy — see above, the pages are fetchable.
It stops crawlers and drive-by readers, it makes casual link-sharing cost
something, and it leaves a receipt: every entry bought this way is a
transaction on chain, so who paid is auditable afterwards. It does not stop
anyone willing to spend 0.1 CHIP, and a pass copied out of `localStorage`
works elsewhere, the same way a shared password does.

## The invitation gate

One slot on the front page takes two different things, because the site has
two doors and they protect against different problems.

**An invitation code** — twelve Crockford base32 characters,
`K7M2-9QXD-4T8B` — is checked by `poker-faucetd` (see
`docs/faucet/README.md` in the monorepo). The daemon can count codes,
expire them and revoke them, so this is the door that answers *who came in*
and can be shut behind one person. It answers with a ticket, which the page
keeps.

**The site's passphrase** is checked in the page, with no network at all.
A JavaScript check on a static host would be theatre — the real page would
still be sitting in the source, one *view source* away — so the passphrase
is not a password compared against the content; **the passphrase is the
address**.

One PBKDF2-SHA256 derivation (250 000 iterations, random salt) produces
24 bytes that split into two independent halves:

- **verifier** (16 bytes) — what the gate compares against, so a wrong
  passphrase fails locally and silently. No request is made, so nothing on
  the network can confirm a near miss, and there is no error message to
  grind against.
- **token** (8 bytes) — the filename the entry stub lives under. It is not
  linked from anywhere, not named in `index.html`, and cannot be derived
  from the verifier.

Keep the passphrase even once invitations are in use: it is the door that
still opens when the daemon is down, and the only one that works with `api`
unset in `config.js`.

Three ways in:

| | |
|---|---|
| The slot | type or paste either an invitation code or the passphrase; codes are grouped as you type, anything else is left alone |
| Link | `https://<host>/#<code-or-passphrase>` — the hash is stripped from the URL before the redirect |
| Keyboard | type the passphrase anywhere *outside* the slot — nothing is focused, nothing echoes, and a wrong guess looks exactly like an idle page |

A browser that has been through remembers it (`localStorage`) and goes
straight in next time; the *Lock this browser* link in the site footer
forgets all of it — the gate, the faucet ticket, and any day pass bought
at the toll booth.

The card on the gate is not decoration doing nothing: it is the only
feedback there is. It turns over to an ace when a code is accepted, and to
a seven when it is not — but it stays face down when the daemon could not
be *reached*, because a code that was never judged has not been rejected,
and saying "not on the list" there would be a lie.

### What this does and does not protect

It keeps the site **out of sight**, not out of reach:

- The token is committed to this repository. **If this repository is
  public, the address is public.** Rotate the passphrase at deploy time,
  or keep the repo private.
- A host with directory listing enabled defeats it completely. Check yours.
  (Directory listing would reveal the fixed-name pages too — `turnstile.js`
  stops casual reading, not a determined reader with the verifier, which
  ships in the file.)
- **The fixed-name pages are static files anyone can fetch.**
  `turnstile.js` can only redirect a browser, so `curl`, a crawler that
  ignores `robots.txt`, or a caching proxy gets the full page without ever
  passing the gate or paying the toll — and the names are ordinary words,
  not secrets. The gate protects the *address of the stub*; it does not
  protect the content of the pages behind it.
- The derivation uses WebCrypto where it exists and a bundled PBKDF2
  (~0.7 s, sliced across timeouts so the page stays responsive) where it
  does not, so the gate also opens over plain http and `file://`.
  Convenient for testing, but it means an insecure origin is not a barrier
  to anyone either.
- Anyone who gets in can share the URL, and it keeps working until
  rotated. Revoking an invitation stops it funding wallets; it does not
  evict whoever already has the address.

For actual access control, put the site behind HTTP basic auth or an
identity proxy and drop the gate.

### Rotating

```sh
python3 tools/gate.py show                    # salt, iterations, target
python3 tools/gate.py check 'some passphrase' # does it open the gate?
python3 tools/gate.py set 'a new passphrase'  # rotate: renames the stub,
                                            # rewrites gate.js AND
                                            # turnstile.js
```

`set` rewrites the config block in both scripts and renames the token stub
to the new token in one step; commit all three. **The passphrase itself is
stored nowhere** — only the verifier derived from it. Keep it in a password
manager; if it is lost, `set` a new one. Rotating does not touch day
passes: they answer to the toll address, not to the passphrase.

Going public later is one commit: rename the stub back to `index.html`,
delete `gate.js`, `turnstile.js`, `pay.html`, `pay.js`, `tools/gate.py` and
`robots.txt`, and drop the turnstile include from each page.

## config.js

One file, loaded by the gate, by the toll booth and by every content page,
points a deployment at its services:

```js
window.BITPOKER = {
  api: "https://api.bitpk.top",          // poker-faucetd: the gate's code door
  explorer: "https://explorer.bitpk.top",
  webapp: "https://app.bitpk.top",
  toll: { to: "community", uchip: 100000, hours: 24 },
  chainRest: ["https://explorer.bitpk.top/rest", "http://127.0.0.1:1317"]
};
```

Nothing secret belongs in it — it ships in the page, and a toll destination
is public by construction anyway. With `api` empty the gate opens only for
the passphrase. **With `toll.to` empty the turnstile switches off** and the
passphrase is the only door, which is what the site did before the toll
existed — so an unconfigured deployment is not an open one. The internal
pages themselves link the explorer and web client only incidentally; the
operational truth lives in the monorepo docs, not here.

## Preview locally

```sh
python3 -m http.server 8080     # from this directory
```

Then open <http://127.0.0.1:8080>. The gate also works over a LAN address
or by opening `index.html` from disk — `crypto.subtle` is missing outside
a secure context, so it falls back to its own PBKDF2, which takes about a
second. Note that `turnstile.js` reads the same `localStorage` key, so a
browser that passed the gate on `127.0.0.1` also passes the content pages
on the same origin.

**The toll cannot be exercised from a local preview**: the explorer's
`/rest` proxy answers `Access-Control-Allow-Origin` for the deployed site's
origin only, so a page served from `127.0.0.1:8080` gets its replies
dropped by the browser. Either point `chainRest` at a node of your own with
CORS enabled, or test the booth where the site actually lives. The
passphrase door needs none of this, which is the point of keeping it.

## Run checks

From the monorepo root:

```sh
python3 -m unittest discover -s website/tests -v
```

The suite finds the token page the way the gate does, by reading `gate.js`,
so rotating the passphrase does not break it. It covers: page structure
and required sections on every page, link-preview metadata, icons, every
local asset existing on disk, external-link safety, accessibility
affordances (skip link, landmarks, menu semantics, reduced motion), the
TOC anchors resolving on each doc page, that every content page loads
`config.js` then `turnstile.js` before `script.js`, that the gate leaks
neither the address nor the content, that both pages are `noindex`, that
both doors are wired, that an unreachable daemon is not reported as a wrong
code, that the derivation is deterministic and salt-dependent, that the
gate still opens where `crypto.subtle` does not exist, and that a wrong
passphrase is rejected.

For the toll it covers: that the turnstile takes either credential, that a
pass is bound to the toll address that sold it, that the booth is *outside*
the turnstile and names neither the stub nor any room, that the price is
written once (in `config.js`, not copied into `pay.js`), that a payment is
only accepted when it actually executed on chain, and that a chain which
could not be read is never reported as an unpaid toll.

## Screenshots

The captures in `assets/screenshots/` are produced by the real Qt client's
headless hooks, not mocked up in a design tool. To refresh them, from the
monorepo root with `bitpoker-qt` built:

```sh
QT_QPA_PLATFORM=offscreen BITPOKER_QT_MOCK_TABLE=1 \
  BITPOKER_QT_SCREENSHOT=website/assets/screenshots/table.png \
  BITPOKER_QT_SCREENSHOT_PAGE=4 BITPOKER_QT_SCREENSHOT_DELAY_MS=3000 \
  ./build/app/bitpoker-qt
```
