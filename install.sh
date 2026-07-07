#!/usr/bin/env bash
# =============================================================================
# AnonyMus Relay — One-Command Install Script
# Supports: Ubuntu 22.04 / 24.04 (x86_64, arm64)
# Usage:    curl -fsSL https://raw.githubusercontent.com/your-org/AnonyMus/main/install.sh | bash
# Or:       bash install.sh [--onion-only] [--domain example.com] [--port 5001]
# =============================================================================

set -euo pipefail

REPO_URL="https://github.com/your-org/AnonyMus"
INSTALL_DIR="/opt/anonymus-relay"
SERVICE_NAME="anonymus-relay"
RELAY_USER="anonymus"
RELAY_PORT="${RELAY_PORT:-5001}"
DOMAIN="${DOMAIN:-}"
ONION_ONLY="${ONION_ONLY:-false}"

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[AnonyMus]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}    $*"; }
error() { echo -e "${RED}[ERROR]${NC}   $*"; exit 1; }

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --onion-only) ONION_ONLY=true; shift ;;
    --domain)     DOMAIN="$2"; shift 2 ;;
    --port)       RELAY_PORT="$2"; shift 2 ;;
    *) warn "Unknown flag: $1"; shift ;;
  esac
done

[[ $EUID -ne 0 ]] && error "Run as root or with sudo."

. /etc/os-release 2>/dev/null || true
[[ "${ID:-}" != "ubuntu" ]] && warn "Tested on Ubuntu; proceed with caution on ${ID:-unknown}."

info "Updating package lists..."
apt-get update -qq

info "Installing system dependencies..."
apt-get install -y -qq git curl ca-certificates gnupg python3 python3-pip python3-venv tor

if [[ "$ONION_ONLY" == "false" ]]; then
  if ! command -v caddy &>/dev/null; then
    info "Installing Caddy..."
    curl -1sLf "https://dl.cloudsmith.io/public/caddy/stable/gpg.key" \
      | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf "https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt" \
      | tee /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq && apt-get install -y -qq caddy
  fi
fi

if ! id "$RELAY_USER" &>/dev/null; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$RELAY_USER"
fi

if [[ -d "$INSTALL_DIR/.git" ]]; then
  git -C "$INSTALL_DIR" pull --ff-only
else
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

ENV_FILE="$INSTALL_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  FLASK_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  cat > "$ENV_FILE" <<EOF
FLASK_SECRET_KEY=${FLASK_SECRET}
RELAY_PORT=${RELAY_PORT}
RELAY_MODE=relay
RELAY_AS_ONION=${ONION_ONLY}
EOF
  [[ -n "$DOMAIN" ]] && echo "RELAY_DOMAIN=${DOMAIN}" >> "$ENV_FILE"
fi
chown "$RELAY_USER:$RELAY_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=AnonyMus Relay Server
After=network-online.target tor.service
Wants=network-online.target

[Service]
Type=simple
User=${RELAY_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${INSTALL_DIR}/venv/bin/python server.py --relay-only
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=${INSTALL_DIR}
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF

if [[ "$ONION_ONLY" == "false" && -n "$DOMAIN" ]]; then
  cat > "/etc/caddy/Caddyfile" <<EOF
${DOMAIN} {
    reverse_proxy 127.0.0.1:${RELAY_PORT}
    encode gzip
}
EOF
  systemctl reload caddy 2>/dev/null || systemctl start caddy
fi

if [[ "$ONION_ONLY" == "true" ]]; then
  HS_DIR="/var/lib/tor/anonymus_relay"
  mkdir -p "$HS_DIR"
  chown debian-tor:debian-tor "$HS_DIR" 2>/dev/null || chown tor:tor "$HS_DIR" 2>/dev/null || true
  chmod 700 "$HS_DIR"
  if ! grep -q "anonymus_relay" /etc/tor/torrc; then
    printf "\nHiddenServiceDir %s\nHiddenServicePort 80 127.0.0.1:%s\n" "$HS_DIR" "$RELAY_PORT" >> /etc/tor/torrc
  fi
  systemctl restart tor
  sleep 3
  ONION_ADDR=$(cat "$HS_DIR/hostname" 2>/dev/null || echo "pending...")
  echo "RELAY_ONION_ADDRESS=${ONION_ADDR}" >> "$ENV_FILE"
  info "Tor hidden service address: $ONION_ADDR"
fi

chown -R "$RELAY_USER:$RELAY_USER" "$INSTALL_DIR"
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"

echo ""
info "AnonyMus Relay installed successfully!"
info "  Service : systemctl status ${SERVICE_NAME}"
info "  Logs    : journalctl -u ${SERVICE_NAME} -f"
