# AnonyMus Quickstart & User Guide

Welcome to **AnonyMus**! This guide is written for everyone—from first-time privacy enthusiasts to advanced power users.

---

## 1. Getting Started in 3 Steps

### Step 1: Launch AnonyMus
- **Windows**: Right-click `install.ps1` and choose **Run with PowerShell** (or run `python anonymus-launcher.py`).
- **Linux/macOS**: Open a terminal, run `./install.sh`, and then `python3 anonymus-launcher.py`.

Your default web browser will automatically open to `http://127.0.0.1:5001/index.html`.

### Step 2: Create Your Cryptographic Identity
1. Choose a **Username** (e.g. `alice`). This stays local to your node.
2. Enter a strong **Password**.
3. Click **Register & Initialize Keys**.
4. AnonyMus will automatically generate your **Tor v3 Onion Address** (e.g. `k4y7...39za.onion`) and your **Post-Quantum Key Exchange Pre-Keys**.

### Step 3: Connect with Friends
1. Click **My Node Info** to view and copy your Onion Address.
2. Share your Onion Address with your contact over a trusted channel.
3. In AnonyMus, click **Add Contact**, paste your friend's Onion Address, set an optional nickname, and send a connection request!

---

## 2. Key Privacy Features & How to Use Them

### Disappearing Messages
- Inside any chat thread, toggle the **Auto-Burn / Disappearing Timer** (e.g., 5 minutes, 1 hour, 24 hours).
- Once read by the recipient, messages automatically shred themselves using secure SQLite page sanitization.

### Multi-Device LAN Sync (Pairing)
To sync your chats and contacts between your laptop and desktop:
1. On your **Primary Device**: Go to **Settings** > **Device Sync** > **Generate Pairing PIN**.
2. Note the 6-digit PIN and IP displayed on screen.
3. On your **Secondary Device**: Go to **Device Sync** > **Connect to Device**, enter the IP, port, and the 6-digit PIN, and click **Synchronize**.
4. The database is securely encrypted and transferred over your local Wi-Fi.

### Coercion Resistance & Duress Wipe
- If you are ever forced to unlock your device under duress, enter your pre-configured **Duress PIN** instead of your regular password.
- AnonyMus will instantly zero out and delete all local databases, session ratchets, and encryption keys, leaving zero forensic trace.

---

## 3. Frequently Asked Questions (FAQ)

**Q: Do I need to install Tor separately?**
A: If Tor is installed and running on your system, AnonyMus connects to it automatically via port 9050. If Tor is not running, AnonyMus functions seamlessly in local LAN / dev mode.

**Q: Are my messages stored on any server?**
A: No! AnonyMus is strictly serverless in P2P mode. Your messages travel directly from your device to your peer's device over encrypted Tor circuits.

**Q: What happens if my friend is offline?**
A: AnonyMus queues outbound messages and attempts delivery automatically when both peers are online, or pushes an encrypted notification token through your configured notification relay.
