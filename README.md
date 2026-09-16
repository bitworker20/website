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
continues onto fixed-name pages behind `guard.js`.

```
index.html          the invitation gate (self-contained: inline CSS, no hints)
gate.js             both doors: an invitation code, or the site's passphrase
guard.js            the content-page guard: no gate pass, no page
config.js           where the faucet, the explorer and the web client live
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
  starts with `guard.js`, which checks that this browser's localStorage
  holds the verifier the gate stores on entry. No pass → back to the door.
- Rotating the passphrase renames only the stub and rewrites the config
  block in `gate.js` **and** `guard.js` together — the fixed pages never
  move, so no link inside the site ever breaks.

`guard.js` is **weaker than the token page it sits behind, and it is the
only thing in front of every page except the stub.** A name like
`overview.html` is not stumbled upon, it is guessed on the first try, and
the guard only runs in a browser: `curl https://<host>/overview.html`
returns the whole page whatever localStorage holds. So the token page's
name is the one real secret here, and it protects nothing but itself —
everything written on the other pages should be read as published to
anyone who knows the host. For access control that actually holds, put the
whole site behind HTTP basic auth or an identity proxy (Cloudflare Access,
oauth2-proxy) and drop the gate. This is a locked door on a building with
no walls.

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
forgets both the gate and the faucet ticket.

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
  (Directory listing would reveal the fixed-name pages too — `guard.js`
  stops casual reading, not a determined reader with the verifier, which
  ships in the file.)
- **The fixed-name pages are static files anyone can fetch.** `guard.js`
  can only redirect a browser, so `curl`, a crawler that ignores
  `robots.txt`, or a caching proxy gets the full page without ever passing
  the gate — and the names are ordinary words, not secrets. The gate
  protects the *address of the stub*; it does not protect the content of
  the pages behind it.
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
                                            # rewrites gate.js AND guard.js
```

`set` rewrites the config block in both scripts and renames the token stub
to the new token in one step; commit all three. **The passphrase itself is
stored nowhere** — only the verifier derived from it. Keep it in a password
manager; if it is lost, `set` a new one.

Going public later is one commit: rename the stub back to `index.html`,
delete `gate.js`, `guard.js`, `tools/gate.py` and `robots.txt`, and make
each page's guard include optional.

## config.js

One file, loaded by the gate, points a deployment at its services:

```js
window.BITPOKER = {
  api: "https://api.bitpk.top",          // poker-faucetd: the gate's code door
  explorer: "https://explorer.bitpk.top",
  webapp: "https://app.bitpk.top"
};
```

Nothing secret belongs in it — it ships in the page. With `api` empty the
gate opens only for the passphrase. The internal pages themselves link the
explorer and web client only incidentally; the operational truth lives in
the monorepo docs, not here.

## Preview locally

```sh
python3 -m http.server 8080     # from this directory
```

Then open <http://127.0.0.1:8080>. The gate also works over a LAN address
or by opening `index.html` from disk — `crypto.subtle` is missing outside
a secure context, so it falls back to its own PBKDF2, which takes about a
second. Note that `guard.js` reads the same `localStorage` key, so a
browser that passed the gate on `127.0.0.1` also passes the content pages
on the same origin.

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
`guard.js` before `script.js`, that the gate leaks neither the address nor
the content, that both pages are `noindex`, that both doors are wired,
that an unreachable daemon is not reported as a wrong code, that the
derivation is deterministic and salt-dependent, that the gate still opens
where `crypto.subtle` does not exist, and that a wrong passphrase is
rejected.

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
