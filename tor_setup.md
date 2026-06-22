# Tor Hidden Service Setup for AnonyMus

AnonyMus is designed to be completely metadata-resistant. While it works securely on the local network (via mDNS) or over the open internet (via HTTPS), the ultimate privacy posture requires routing traffic over the Tor network.

Running AnonyMus as a Tor Hidden Service (`.onion` address) ensures:
1. **Server Anonymity:** Your server's IP address and physical location are hidden.
2. **Client Anonymity:** Users connecting to the chat hide their IP addresses from the server.
3. **NAT Traversal:** You don't need to port-forward your router to host a chat server.

## Setup Instructions (Linux/macOS)

1. **Install Tor:**
   ```bash
   sudo apt install tor   # Debian/Ubuntu
   brew install tor       # macOS
   ```

2. **Configure Tor:**
   Open your `torrc` file (usually located at `/etc/tor/torrc` or `/usr/local/etc/tor/torrc`).
   Add the following lines at the bottom:
   ```text
   HiddenServiceDir /var/lib/tor/anonymus_hidden_service/
   HiddenServicePort 80 127.0.0.1:5000
   ```
   *(Note: Ensure you are running the AnonyMus Flask server on port 5000).*

3. **Restart Tor:**
   ```bash
   sudo systemctl restart tor   # Linux
   brew services restart tor    # macOS
   ```

4. **Get Your Onion Address:**
   Tor has generated a unique `.onion` address for your server. Read it by running:
   ```bash
   sudo cat /var/lib/tor/anonymus_hidden_service/hostname
   ```

5. **Access the Chat:**
   - Give the `.onion` address to your participants.
   - They must open the address using the **Tor Browser**.
   - AnonyMus will function identically, but with absolute metadata resistance.
