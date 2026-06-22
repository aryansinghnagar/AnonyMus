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

---

## Setup Instructions (Windows)

1. **Install Tor:**
   Download the **Tor Expert Bundle** or the **Tor Browser** from [torproject.org](https://www.torproject.org/).

2. **Configure Tor:**
   Open the Tor configuration file (called `torrc`) in a text editor:
   - **If using Tor Browser:** Located at `[Tor Browser Folder]\Browser\TorBrowser\Data\Tor\torrc`
   - **If using Tor Expert Bundle:** Located at `[Installation Directory]\Data\Tor\torrc` (or create a file named `torrc` in the installation folder).
   
   Add the following lines at the bottom:
   ```text
   HiddenServiceDir C:/Users/Public/anonymus_hidden_service/
   HiddenServicePort 80 127.0.0.1:5000
   ```
   *(Note: Using a path under `C:/Users/Public/` avoids folder permission errors on Windows. Ensure you use forward slashes `/` as shown above. The AnonyMus server must be running on port 5000).*

3. **Restart Tor:**
   Completely close and reopen the Tor Browser, or restart the Tor command prompt window/service.

4. **Get Your Onion Address:**
   Tor has generated a unique `.onion` address for your server. Locate and open the generated `hostname` file:
   - Open the directory `C:\Users\Public\anonymus_hidden_service\` in File Explorer.
   - Open the `hostname` file with Notepad to copy your new `.onion` address.

---

## Access the Chat

- Give the `.onion` address to your participants.
- They must open the address using the **Tor Browser**.
- AnonyMus will function identically, but with absolute metadata resistance.
