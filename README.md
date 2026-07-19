# BitPoker website

The English project homepage for BitPoker: peer-to-peer poker infrastructure
with encrypted play, on-chain escrow, deterministic adjudication, native
clients, relays, and a live-data explorer.

The site is intentionally dependency-free. It uses semantic HTML, responsive
CSS, and a small progressive JavaScript enhancement for mobile navigation.

## Preview locally

From this directory:

```sh
python3 -m http.server 8080
```

Then open <http://127.0.0.1:8080>.

## Run checks

From the monorepo root:

```sh
python3 -m unittest discover -s website/tests -v
```

The contract suite verifies the page structure, core project language,
metadata, local assets, external-link safety, mobile navigation semantics,
responsive CSS, and reduced-motion support.

## Deploy

Serve the contents of this directory from any static host. Keep `index.html`,
the CSS files, `script.js`, and `assets/` at the same relative paths. No build
step is required.
