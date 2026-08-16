# BitPoker website

The English project homepage: what BitPoker is, how a hand actually works, where
to get a client, and how to run a node or a relay.

Rewritten from scratch in August 2026. It is one page, one stylesheet and one
small script — no framework, no build step, no bundler. Everything on it is
sourced from `docs/whitepaper/bitpoker-whitepaper.md` in the monorepo; if the
whitepaper and the page disagree, the whitepaper is right and the page is stale.

**The site is invitation only** — see below. `index.html` is the gate; the real
page is the `<token>.html` file, named after a token derived from the
passphrase.

```
index.html          the invitation gate (self-contained: inline CSS, no hints)
gate.js             both doors: an invitation code, or the site's passphrase
config.js           where the faucet, the explorer and the web client live
<token>.html        the real site
styles.css          the site's stylesheet
script.js           mobile menu, copy buttons, "lock this browser", the faucet
install.sh          the one-line server installer the page links to
robots.txt          disallow everything, both pages
tools/gate.py       rotate the passphrase, inspect or check the current one
assets/             brand marks, favicons, social cards, whitepaper PDF
assets/screenshots/ real captures of the Qt desktop client
tests/test_site.py  contract suite
```

## The invitation gate

One slot on the front page takes two different things, because the site has two
doors and they protect against different problems.

**An invitation code** — twelve Crockford base32 characters, `K7M2-9QXD-4T8B` —
is checked by `poker-faucetd` (see `docs/faucet/README.md` in the monorepo). The
daemon can count codes, expire them and revoke them, so this is the door that
answers *who came in* and can be shut behind one person. It answers with a
ticket, which the page keeps so the faucet on the other side does not ask for
the code again.

**The site's passphrase** is checked in the page, with no network at all. A
JavaScript check on a static host would be theatre — the real page would still
be sitting in the source, one *view source* away — so the passphrase is not a
password compared against the content; **the passphrase is the address**.

One PBKDF2-SHA256 derivation (250 000 iterations, random salt) produces 24 bytes
that split into two independent halves:

- **verifier** (16 bytes) — what the gate compares against, so a wrong
  passphrase fails locally and silently. No request is made, so nothing on the
  network can confirm a near miss, and there is no error message to grind
  against.
- **token** (8 bytes) — the filename the real page lives under. It is not
  linked from anywhere, not named in `index.html`, and cannot be derived from
  the verifier.

Keep the passphrase even once invitations are in use: it is the door that still
opens when the daemon is down, and the only one that works with `api` unset in
`config.js`.

Three ways in:

| | |
|---|---|
| The slot | type or paste either an invitation code or the passphrase; codes are grouped as you type, anything else is left alone |
| Link | `https://<host>/#<code-or-passphrase>` — the hash is stripped from the URL before the redirect |
| Keyboard | type the passphrase anywhere *outside* the slot — nothing is focused, nothing echoes, and a wrong guess looks exactly like an idle page |

A browser that has been through remembers it (`localStorage`) and goes straight
in next time; the *Lock this browser* link in the site footer forgets both the
gate and the faucet ticket.

The card on the gate is not decoration doing nothing: it is the only feedback
there is. It turns over to an ace when a code is accepted, and to a seven when
it is not — but it stays face down when the daemon could not be *reached*,
because a code that was never judged has not been rejected, and saying "not on
the list" there would be a lie.

### What this does and does not protect

It keeps the site **out of sight**, not out of reach:

- The token is committed to this repository. **If this repository is public, the
  address is public.** Rotate the passphrase at deploy time, or keep the repo
  private.
- A host with directory listing enabled defeats it completely. Check yours.
- The derivation uses WebCrypto where it exists and a bundled PBKDF2 (~0.7 s,
  sliced across timeouts so the page stays responsive) where it does not, so the
  gate also opens over plain http and `file://`. Convenient for testing, but it
  means an insecure origin is not a barrier to anyone either.
- Anyone who gets in can share the URL, and it keeps working until rotated.
  Revoking an invitation stops it funding wallets; it does not evict whoever
  already has the address.

For actual access control, put the site behind HTTP basic auth or an identity
proxy (Cloudflare Access, oauth2-proxy) and drop the gate. This is a locked door
on a building with no walls.

### Rotating

```sh
python3 tools/gate.py show                    # salt, iterations, target
python3 tools/gate.py check 'some passphrase' # does it open the gate?
python3 tools/gate.py set 'a new passphrase'  # rotate: renames the page too
```

`set` rewrites the config block in `gate.js` and renames the real page to the
new token in one step; commit both. **The passphrase itself is stored nowhere** —
only the verifier derived from it. Keep it in a password manager; if it is lost,
`set` a new one.

Going public later is one commit: rename the real page back to `index.html`,
delete `gate.js`, `tools/gate.py` and `robots.txt`, and restore the page's
`og:image` and indexable `robots` meta.

## The testnet section, and config.js

The page's `#testnet` block is the only part of the site that points at
something running rather than at a document: the web client
(`app.bitpk.top`), the block explorer (`explorer.bitpk.top`), and a faucet form
that hands out a starting stack of test chips.

All three addresses live in one file, `config.js`, loaded by both pages:

```js
window.BITPOKER = {
  api: "https://api.bitpk.top",          // poker-faucetd: the gate and the faucet
  explorer: "https://explorer.bitpk.top",
  webapp: "https://app.bitpk.top"
};
```

Nothing secret belongs in it — it ships in the page.

**With `api` empty the site still works.** The gate then opens only for the
passphrase, and the faucet panel stays hidden: it ships with `hidden` set and
`script.js` reveals it only after `/v1/info` answers, because a form that
cannot submit anywhere is worse than no form. The same is true when the daemon
is simply down or its CORS list does not name this origin.

The panel does not ask for an invitation code when the gate already stored a
ticket — which is the usual case, since the visitor got in with one. Visitors
who came through the passphrase door see the code field instead.

Operating the daemon on the other end — limits, invitations, systemd, nginx —
is `docs/faucet/README.md` in the monorepo.

## Preview locally

```sh
python3 -m http.server 8080     # from this directory
```

Then open <http://127.0.0.1:8080>. The gate also works over a LAN address or by
opening `index.html` from disk — `crypto.subtle` is missing outside a secure
context, so it falls back to its own PBKDF2, which takes about a second.

## Run checks

From the monorepo root:

```sh
python3 -m unittest discover -s website/tests -v
```

43 tests: page structure and required sections, link-preview metadata, icons,
every local asset existing on disk, external-link safety, the three release
downloads pointing at asset names that survive a new release, the installer
section staying hidden (no visible install command, no dead `#node` link) and
any command it does show using a role `install.sh` accepts, the installer
parsing and rejecting unknown roles, accessibility affordances (skip link,
landmarks, menu semantics, screenshot alt text, reduced motion).

For the testnet section: that the web client and the explorer are both linked,
that both pages read the same `config.js`, that the faucet panel ships hidden
and its form is labelled, that the faucet endpoint comes from the config rather
than a hard-coded host, and that *Lock this browser* forgets the invitation
ticket as well as the gate.

For the gate: that it leaks neither the address nor the content, that no other
file in the repository names the target, that both pages are `noindex`, that
both doors are wired (the code to the daemon, the passphrase to the local
derivation), that an unreachable daemon is not reported as a wrong code, that
the derivation is deterministic and salt-dependent, that the gate still opens
where `crypto.subtle` does not exist, and that a wrong passphrase is rejected.

The suite finds the real page the way the gate does, by reading `gate.js`, so
rotating the passphrase does not break it.

## Screenshots

The two captures in `assets/screenshots/` are produced by the real Qt client's
headless hooks, not mocked up in a design tool. To refresh them, from the
monorepo root with `bitpoker-qt` built:

```sh
QT_QPA_PLATFORM=offscreen BITPOKER_QT_MOCK_TABLE=1 \
  BITPOKER_QT_SCREENSHOT=website/assets/screenshots/table.png \
  BITPOKER_QT_SCREENSHOT_PAGE=4 BITPOKER_QT_SCREENSHOT_DELAY_MS=3000 \
  build/bitpoker/app/qt/bitpoker-qt --language en

QT_QPA_PLATFORM=offscreen BITPOKER_QT_MOCK_TABLE=1 \
  BITPOKER_QT_MOCK_HAND_RESULT=1 BITPOKER_QT_MOCK_SETTLEMENT=1 \
  BITPOKER_QT_SCREENSHOT=website/assets/screenshots/settlement.png \
  BITPOKER_QT_SCREENSHOT_PAGE=4 BITPOKER_QT_SCREENSHOT_DELAY_MS=3000 \
  build/bitpoker/app/qt/bitpoker-qt --language en
```

`--language en` matters: the client remembers a UI language, and the site is
English.

## install.sh

Served from this repository, so the command on the page is:

```sh
curl -fsSL https://raw.githubusercontent.com/bitworker20/website/main/install.sh | sh -s -- node
curl -fsSL https://raw.githubusercontent.com/bitworker20/website/main/install.sh | sh -s -- relay
```

It installs `pokerchaind` or `poker-relayd` from a GitHub release, creates a
service user, writes a systemd unit and starts it. Every input is an
environment variable with a default (chain id, release tag, repo, data
directory, seeds, genesis URL, relay endpoint) — see the comment block at the
top of the file.

For the network's own values it fetches an optional manifest,
`networks/<chain-id>.env` in this repository, holding `GENESIS_URL=`, `SEEDS=`
and `MIN_GAS_PRICE=`. That directory does not exist yet; the installer says so
and carries on with defaults. **Create it when the public testnet is
genesised** — that way re-genesising the network does not require re-cutting the
script.

## Before this goes live

Five things are written against hosts or events that do not exist yet:

| What | Where | Currently |
|---|---|---|
| The gate | `gate.js` | rotate the passphrase at deploy time, or remove the gate entirely when the site goes public |
| Service addresses | `config.js` | `api.bitpk.top`, `explorer.bitpk.top` and `app.bitpk.top`. The faucet host must also name this site's origin in its `allowed-origins`, or the browser drops the answer and the page concludes there is no faucet |
| Social-card URL | the site page's `og:image` / `twitter:image` | relative `assets/og-image.png`; some scrapers will not resolve a relative URL — make it absolute once there is a domain |
| `install.sh` assets | `install.sh` `BITPOKER_REPO` | it fetches `bitpoker-{node,relay}-linux-{amd64,arm64}.tar.gz`, which the release does not publish — it ships one combined `bitpoker-bin-ubuntu-x64.tar.gz`. Reconcile the two before the installer section goes back on the page |
| Network manifest | `install.sh` `MANIFEST_URL` | `networks/pokerchain-testnet-1.env` in this repository, not yet created |

## Downloads

The client packages are **not** committed here; the buttons point at
`github.com/bitworker20/bitpoker/releases/latest/download/`:

| Button | Asset |
|---|---|
| Download APK | `bitpoker-android-arm64.apk` — Qt/QML mobile wallet, debug-signed |
| Download DMG | `BitPoker-arm64.dmg` — Qt desktop client, Apple Silicon, macOS 12+ |
| Download AppImage | `BitPoker-x86_64.AppImage` — Qt desktop client, self-contained, glibc 2.38+ |
| Download tar.gz | `bitpoker-bin-ubuntu-x64.tar.gz` — pokerchaind, poker-relayd, poker-faucetd, TUI, dispatcher |
| SHA256SUMS.txt | checksums for all of the above |

`latest/download/<name>` only resolves names that stay put between releases,
which is why the AppImage and the DMG are each published twice: once versioned
(`BitPoker-0.2.0-x86_64.AppImage`, `BitPoker-0.2.0-arm64.dmg`) and once under
the stable alias the page links to. `tools/release/publish.sh` in the monorepo
does that.

The DMG is ad-hoc signed, not notarized: Gatekeeper blocks a plain
double-click on a machine that did not build it, and the first launch has to be
right-click → Open. The page says so on the button. Fixing it properly needs an
Apple Developer ID (`CODESIGN_IDENTITY` in `tools/macos/build_dmg.sh`) and a
notarization pass.

Only the whitepaper PDF ships with the site, because it should be readable
without leaving the page.

## The one-line installer is hidden

The `#node` section — "Run it on a Linux server", with the two
`curl … | sh -s -- node|relay` commands — is **commented out**, along with the
"Run a node" links in the header, hero and footer. `install.sh` still lives
here, it is simply not offered: it downloads per-role tarballs the release does
not publish, and wants a network manifest that does not exist yet.

Bringing it back is uncommenting those four places — the test suite checks the
pair, so a restored section with a dead `#node` link, or a command whose role
`install.sh` does not accept, fails.

## Deploy

Serve this directory from any static host, keeping the relative paths intact.
No build step. Serve it over https — not because the gate needs it (it has a
fallback) but because everything else does.

## Brand

The marks, favicons and social cards come from `docs/brand/` in the monorepo and
are copied here — regenerate them there (`docs/brand/render.sh`), then copy, so
the two do not drift.
