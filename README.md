# BitPoker website

The English project homepage: what BitPoker is, how a hand actually works, where
to get a client, and how to run a node or a relay.

Rewritten from scratch in August 2026. It is one page, one stylesheet and one
small script — no framework, no build step, no bundler. Everything on it is
sourced from `docs/whitepaper/bitpoker-whitepaper.md` in the monorepo; if the
whitepaper and the page disagree, the whitepaper is right and the page is stale.

```
index.html          the page
styles.css          the only stylesheet
script.js           mobile menu + copy buttons (progressive enhancement)
install.sh          the one-line server installer the page links to
assets/             brand marks, favicons, social card, whitepaper PDF
assets/screenshots/ real captures of the Qt desktop client
tests/test_site.py  contract suite
```

## Preview locally

```sh
python3 -m http.server 8080     # from this directory
```

Then open <http://127.0.0.1:8080>.

## Run checks

From the monorepo root:

```sh
python3 -m unittest discover -s website/tests -v
```

24 tests: page structure and required sections, link-preview metadata, icons,
every local asset actually existing on disk, external-link safety, the install
commands on the page matching the roles `install.sh` accepts, the installer
parsing and rejecting unknown roles, and the accessibility affordances (skip
link, landmarks, menu semantics, screenshot alt text, reduced motion).

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

Three strings are written against hosts that do not exist yet. Each is marked
in place; search for them:

| What | Where | Currently |
|---|---|---|
| Social-card URL | `index.html` `og:image` / `twitter:image` | relative `assets/og-image.png`; some scrapers will not resolve a relative URL — make it absolute once there is a domain |
| Release assets | `index.html` download links, `install.sh` `BITPOKER_REPO` | `github.com/bitworker20/bitpoker/releases/latest/download/…` with assets `bitpoker-android-arm64.apk`, `bitpoker-extension.zip`, `bitpoker-{node,relay}-linux-{amd64,arm64}.tar.gz` and `checksums.txt` — confirm the repo name and publish those asset names |
| Network manifest | `install.sh` `MANIFEST_URL` | `networks/pokerchain-testnet-1.env` in this repository, not yet created |

The APK and the extension zip are **not** committed here; the download buttons
point at GitHub Releases. Only the whitepaper PDF ships with the site, because
it should be readable without leaving the page.

## Deploy

Serve this directory from any static host, keeping the relative paths intact.
No build step.

## Brand

The marks, favicons and social card come from `docs/brand/` in the monorepo and
are copied here — regenerate them there (`docs/brand/render.sh`), then copy, so
the two do not drift.
