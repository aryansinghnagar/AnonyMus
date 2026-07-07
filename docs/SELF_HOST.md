# Self-Hosting an AnonyMus Relay

AnonyMus relays are **blind** — they store no message content, no usernames, and no passwords. All message content is E2E-encrypted before it ever reaches the relay. If your server is seized, there is nothing to disclose.

---

## Quick-start (Ubuntu 22.04 / 24.04)

### Option A — Clearnet with automatic TLS (Caddy)

```bash
curl -fsSL https://raw.githubusercontent.com/your-org/AnonyMus/main/install.sh \
  | sudo bash -s -- --domain relay.example.com
```

Point your DNS `A` record at the server IP **before** running this command so Caddy can obtain a Let's Encrypt certificate automatically.

### Option B — Tor-only (.onion, no IP address)

```bash
curl -fsSL https://raw.githubusercontent.com/your-org/AnonyMus/main/install.sh \
  | sudo bash -s -- --onion-only
```

After installation the `.onion` address is printed and stored in `/opt/anonymus-relay/.env`. Share it with users who want to connect through your relay.

### Option C — Docker Compose

```bash
git clone https://github.com/your-org/AnonyMus
cd AnonyMus

# Copy and configure environment
cp .env.example .env
# Edit .env: set FLASK_SECRET_KEY, RELAY_DOMAIN

# Clearnet + TLS mode
docker compose --profile clearnet up -d

# Tor onion-only mode
docker compose --profile onion up -d
```

---

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `FLASK_SECRET_KEY` | **required** | 64-char hex secret for session signing |
| `RELAY_PORT` | `5001` | Internal port the relay listens on |
| `RELAY_DOMAIN` | _(empty)_ | Your public domain (needed for Caddy TLS) |
| `RELAY_AS_ONION` | `false` | Set `true` for Tor-only deployment |
| `REDIS_URL` | _(empty)_ | Optional Redis URL for offline message buffering |

---

## What the relay stores

| Data | Stored | Notes |
|---|---|---|
| Queue IDs (UUID) | ✅ In memory | Ephemeral, lost on restart |
| Message content | ❌ Never | E2E encrypted, relay is blind |
| Sender identity | ❌ Never | Tor circuit masks IP |
| Recipient identity | ❌ Never | Only queue UUID is known |
| Offline message payloads | ✅ Temporarily | Deleted immediately on delivery; max 500 per queue, 24 hr TTL |

---

## Keeping the relay updated

```bash
# Systemd install
sudo systemctl stop anonymus-relay
sudo git -C /opt/anonymus-relay pull
sudo /opt/anonymus-relay/venv/bin/pip install -r /opt/anonymus-relay/requirements.txt
sudo systemctl start anonymus-relay

# Docker
docker compose pull && docker compose up -d
```

---

## Transparency template

As an operator, you are encouraged to publish a transparency report. See [TRANSPARENCY.md](TRANSPARENCY.md) for a template.

---

## Uninstalling

```bash
sudo systemctl disable --now anonymus-relay
sudo rm -rf /opt/anonymus-relay /etc/systemd/system/anonymus-relay.service
sudo userdel anonymus
sudo systemctl daemon-reload
```
