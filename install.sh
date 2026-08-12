#!/bin/sh
# BitPoker one-line installer.
#
#   curl -fsSL https://raw.githubusercontent.com/bitworker20/website/main/install.sh | sh -s -- node
#   curl -fsSL https://raw.githubusercontent.com/bitworker20/website/main/install.sh | sh -s -- relay
#
# Installs one of two roles on a systemd Linux host:
#
#   node   pokerchaind — full node / validator candidate. Carries the C++
#          adjudication engine that consensus calls on disputed sessions.
#   relay  poker-relayd — forwards session traffic and earns rake from the pots
#          it carried, paid on bilateral receipts from both players.
#
# It downloads a release binary, creates a service user, writes a systemd unit
# and starts it. It does not open firewall ports, obtain TLS certificates, fund
# an account, or register a validator — those are yours to do, and the script
# prints what is left at the end.
#
# Every setting is an environment variable with a default, so nothing here has
# to be edited to be reused:
#
#   BITPOKER_CHAIN_ID    chain id to join            (pokerchain-testnet-1)
#   BITPOKER_RELEASE     release tag or "latest"     (latest)
#   BITPOKER_REPO        GitHub repo holding releases (bitworker20/bitpoker)
#   BITPOKER_HOME        data directory              (/var/lib/pokerchain)
#   BITPOKER_USER        service user                (pokerchain)
#   BITPOKER_MONIKER     node moniker                (the hostname)
#   BITPOKER_SEEDS       comma-separated seed peers  (from the network manifest)
#   BITPOKER_GENESIS_URL genesis.json URL            (from the network manifest)
#   BITPOKER_ENDPOINT    relay only: public wss:// URL to register on chain
#   BITPOKER_NO_START    set to 1 to install without starting the service
#
# Re-running it is safe: it upgrades the binary and rewrites the unit, and
# leaves the data directory and any keys alone.

set -eu

ROLE="${1:-}"

CHAIN_ID="${BITPOKER_CHAIN_ID:-pokerchain-testnet-1}"
RELEASE="${BITPOKER_RELEASE:-latest}"
REPO="${BITPOKER_REPO:-bitworker20/bitpoker}"
HOME_DIR="${BITPOKER_HOME:-/var/lib/pokerchain}"
SVC_USER="${BITPOKER_USER:-pokerchain}"
MONIKER="${BITPOKER_MONIKER:-$(hostname -s 2>/dev/null || echo bitpoker-node)}"
BIN_DIR="${BITPOKER_BIN_DIR:-/usr/local/bin}"
DENOM="uchip"

# The network manifest carries the genesis hash, seeds and the minimum gas
# price for the current testnet, so this script does not have to be re-cut every
# time the network is re-genesised.
MANIFEST_URL="${BITPOKER_MANIFEST_URL:-https://raw.githubusercontent.com/bitworker20/website/main/networks/${CHAIN_ID}.env}"

RED=''; BOLD=''; DIM=''; OFF=''
if [ -t 1 ]; then RED='\033[31m'; BOLD='\033[1m'; DIM='\033[2m'; OFF='\033[0m'; fi

say()  { printf '%b\n' "${BOLD}==>${OFF} $*"; }
info() { printf '%b\n' "${DIM}    $*${OFF}"; }
die()  { printf '%b\n' "${RED}error:${OFF} $*" >&2; exit 1; }

usage() {
  cat <<'EOF'
usage: install.sh <node|relay>

  node    install pokerchaind (full node / validator candidate)
  relay   install poker-relayd (session relay, earns rake)

See the comments at the top of this file for the environment variables that
override chain id, release, data directory and service user.
EOF
}

# ── preflight ────────────────────────────────────────────────────────────────

case "$ROLE" in
  node|relay) ;;
  ""|-h|--help|help) usage; exit 0 ;;
  *) usage >&2; die "unknown role: $ROLE" ;;
esac

[ "$(id -u)" -eq 0 ] || die "run as root (or: curl … | sudo sh -s -- $ROLE)"

command -v systemctl >/dev/null 2>&1 || die "systemd is required"
command -v curl >/dev/null 2>&1 || die "curl is required"
command -v tar >/dev/null 2>&1 || die "tar is required"

case "$(uname -s)" in
  Linux) ;;
  *) die "Linux only (found $(uname -s))" ;;
esac

case "$(uname -m)" in
  x86_64|amd64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) die "unsupported architecture: $(uname -m) — build from source instead" ;;
esac

if [ "$ROLE" = node ]; then
  BIN=pokerchaind
  SERVICE=pokerchaind
else
  BIN=poker-relayd
  SERVICE=poker-relayd
fi

say "BitPoker ${BOLD}${ROLE}${OFF} · ${CHAIN_ID} · linux/${ARCH}"

# ── network manifest (optional, best effort) ─────────────────────────────────

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM

GENESIS_URL="${BITPOKER_GENESIS_URL:-}"
SEEDS="${BITPOKER_SEEDS:-}"
MIN_GAS_PRICE="${BITPOKER_MIN_GAS_PRICE:-0.001${DENOM}}"

if curl -fsSL "$MANIFEST_URL" -o "$TMP/network.env" 2>/dev/null; then
  # The manifest is a plain KEY=value file; only these keys are read, and an
  # explicit environment variable always wins over it.
  for key in GENESIS_URL SEEDS MIN_GAS_PRICE; do
    value="$(sed -n "s/^${key}=//p" "$TMP/network.env" | head -n 1 | tr -d '\r"')"
    [ -n "$value" ] || continue
    case "$key" in
      GENESIS_URL) [ -n "$GENESIS_URL" ] || GENESIS_URL="$value" ;;
      SEEDS) [ -n "$SEEDS" ] || SEEDS="$value" ;;
      MIN_GAS_PRICE) [ -n "${BITPOKER_MIN_GAS_PRICE:-}" ] || MIN_GAS_PRICE="$value" ;;
    esac
  done
  info "network manifest: $MANIFEST_URL"
else
  info "no network manifest for ${CHAIN_ID}; using defaults and any BITPOKER_* overrides"
fi

# ── download ─────────────────────────────────────────────────────────────────

ASSET="bitpoker-${ROLE}-linux-${ARCH}.tar.gz"
if [ "$RELEASE" = latest ]; then
  BASE="https://github.com/${REPO}/releases/latest/download"
else
  BASE="https://github.com/${REPO}/releases/download/${RELEASE}"
fi

say "downloading ${ASSET}"
curl -fsSL "${BASE}/${ASSET}" -o "$TMP/$ASSET" \
  || die "download failed: ${BASE}/${ASSET}"

# Checksums ship next to the asset. A missing file is a warning, not a failure —
# a mismatch is always fatal.
if curl -fsSL "${BASE}/checksums.txt" -o "$TMP/checksums.txt" 2>/dev/null; then
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$TMP" && grep " ${ASSET}\$" checksums.txt | sha256sum -c -) >/dev/null 2>&1 \
      || die "checksum mismatch for ${ASSET} — refusing to install"
    info "checksum verified"
  fi
else
  info "no checksums.txt in this release — skipping verification"
fi

tar -xzf "$TMP/$ASSET" -C "$TMP"
[ -f "$TMP/$BIN" ] || die "archive does not contain ${BIN}"

install -m 0755 "$TMP/$BIN" "${BIN_DIR}/${BIN}"
say "installed ${BIN_DIR}/${BIN} — $("${BIN_DIR}/${BIN}" version 2>/dev/null || echo 'version unknown')"

# ── service user and data directory ──────────────────────────────────────────

if ! id "$SVC_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$HOME_DIR" --shell /usr/sbin/nologin "$SVC_USER"
  info "created service user ${SVC_USER}"
fi

mkdir -p "$HOME_DIR"
chown -R "$SVC_USER:$SVC_USER" "$HOME_DIR"

# ── role setup ───────────────────────────────────────────────────────────────

run_as() { su -s /bin/sh "$SVC_USER" -c "$*"; }

if [ "$ROLE" = node ]; then
  if [ ! -f "$HOME_DIR/config/genesis.json" ]; then
    say "initialising node home"
    run_as "${BIN_DIR}/${BIN} init '${MONIKER}' --chain-id '${CHAIN_ID}' --home '${HOME_DIR}'" >/dev/null

    if [ -n "$GENESIS_URL" ]; then
      curl -fsSL "$GENESIS_URL" -o "$TMP/genesis.json" || die "cannot fetch genesis: $GENESIS_URL"
      install -o "$SVC_USER" -g "$SVC_USER" -m 0644 "$TMP/genesis.json" "$HOME_DIR/config/genesis.json"
      info "genesis installed from $GENESIS_URL"
    else
      info "no genesis URL — the node was initialised with a local genesis; replace"
      info "$HOME_DIR/config/genesis.json before joining a network"
    fi
  else
    info "existing node home at $HOME_DIR — keeping genesis and keys"
  fi

  CONFIG="$HOME_DIR/config/config.toml"
  APP="$HOME_DIR/config/app.toml"
  [ -n "$SEEDS" ] && sed -i "s|^seeds *=.*|seeds = \"${SEEDS}\"|" "$CONFIG"
  sed -i "s|^minimum-gas-prices *=.*|minimum-gas-prices = \"${MIN_GAS_PRICE}\"|" "$APP"

  EXEC="${BIN_DIR}/${BIN} start --home ${HOME_DIR}"
  AFTER_TEXT="pokerchaind is syncing. Watch it with:
    journalctl -fu ${SERVICE}
    ${BIN} status --home ${HOME_DIR} | head

  To become a validator: fund an account, then
    ${BIN} tx staking create-validator --home ${HOME_DIR} --chain-id ${CHAIN_ID} …"
else
  ENDPOINT="${BITPOKER_ENDPOINT:-}"
  LISTEN="${BITPOKER_LISTEN:-127.0.0.1:18080}"
  CHAIN_GRPC="${BITPOKER_CHAIN_GRPC:-127.0.0.1:9090}"
  CHAIN_NODE="${BITPOKER_CHAIN_NODE:-tcp://127.0.0.1:26657}"

  mkdir -p "$HOME_DIR/config"
  chown -R "$SVC_USER:$SVC_USER" "$HOME_DIR"

  # The relay identity is an ed25519 key the daemon generates on first use; the
  # on-chain relay id is derived from it, so this file is the thing to back up.
  #
  # It binds loopback and speaks plain HTTP: TLS belongs to the reverse proxy in
  # front, which is the only thing that can reach it. A self-signed certificate
  # served by the daemon itself cannot be used by browser wallets at all.
  EXEC="${BIN_DIR}/${BIN} serve --home ${HOME_DIR} --listen ${LISTEN} \
--chain-id ${CHAIN_ID} --chain-grpc ${CHAIN_GRPC} --chain-node ${CHAIN_NODE} \
--fees 2000${DENOM}"
  [ -n "$ENDPOINT" ] && EXEC="$EXEC --endpoint ${ENDPOINT} --auto-register"

  AFTER_TEXT="poker-relayd is serving on ${LISTEN} (loopback, plain HTTP).
    journalctl -fu ${SERVICE}
    curl -sS http://${LISTEN}/health

  Two things are still missing before anyone can play through it:

    1. TLS. Put nginx in front, terminate wss:// there, and proxy to
       ${LISTEN}. The full configuration — WebSocket upgrade, timeouts,
       wildcard certificate, front pool — is in docs/relay/deployment.md.
    2. A registration on chain, with a bond:
         ${BIN} register --home ${HOME_DIR}
       or set BITPOKER_ENDPOINT to your public wss:// URL and re-run this
       script to have the daemon register itself on start.

  It also needs a reachable pokerchain node (--chain-grpc ${CHAIN_GRPC}).

  Back up ${HOME_DIR}/config/relay_node_key.json — your relay identity, and the
  rewards owed to it, derive from that key."
fi

# ── systemd unit ─────────────────────────────────────────────────────────────

say "writing /etc/systemd/system/${SERVICE}.service"
cat > "/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=BitPoker ${ROLE} (${BIN})
After=network-online.target
Wants=network-online.target

[Service]
User=${SVC_USER}
Group=${SVC_USER}
ExecStart=${EXEC}
Restart=on-failure
RestartSec=5
LimitNOFILE=65535
WorkingDirectory=${HOME_DIR}

# The service needs nothing outside its own data directory.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=${HOME_DIR}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE}" >/dev/null 2>&1 || true

if [ "${BITPOKER_NO_START:-0}" = "1" ]; then
  say "installed; not started (BITPOKER_NO_START=1)"
  info "start it with: systemctl start ${SERVICE}"
else
  systemctl restart "${SERVICE}"
  say "${SERVICE} started"
fi

printf '\n%b\n\n' "${AFTER_TEXT}"
