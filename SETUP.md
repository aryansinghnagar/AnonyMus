# Layman's Setup Guide — AnonyMus Centralized Server

Welcome to AnonyMus! This guide is written for beginners to help you set up and run the centralized chat server. Just follow these steps carefully.

---

## Step 1: Install Python (The Engine)

AnonyMus runs on Python. You need to install Python on your computer.

### For Windows Users:
1. Open your web browser and go to [python.org/downloads](https://www.python.org/downloads/).
2. Click the yellow button that says **Download Python (3.12 or newer)**.
3. Once the installer downloads, double-click it to run it.
4. > [!IMPORTANT]
   > On the first screen of the installer, check the box at the bottom that says **"Add python.exe to PATH"**. If you skip this, the setup will fail!
5. Click **Install Now** and wait for it to finish.

### For macOS Users:
1. Open your browser and go to [python.org/downloads](https://www.python.org/downloads/).
2. Click the download button for macOS.
3. Open the downloaded `.pkg` file and click through the installer.

### For Linux Users:
Open your terminal and run:
- **Ubuntu/Debian:** `sudo apt update && sudo apt install -y python3 python3-pip python3-venv`
- **Fedora/RHEL:** `sudo dnf install python3 python3-pip`

---

## Step 2: Download the AnonyMus Code

1. Download the AnonyMus files. If you are using Git, run:
   ```bash
   git clone https://github.com/aryansinghnagar/AnonyMus.git
   ```
   *(If you don't use Git, you can download the project as a `.zip` file from GitHub, extract it on your Desktop, and open the folder).*

---

## Step 3: Open the Terminal or PowerShell

You need to run a few commands to get everything started.

- **On Windows:** Press the **Windows Key**, type `PowerShell`, and press **Enter**.
- **On macOS:** Press **Cmd + Space**, type `Terminal`, and press **Enter**.
- **On Linux:** Press **Ctrl + Alt + T**.

Next, you need to point your terminal to the folder where you saved AnonyMus. Type `cd` followed by a space, and drag-and-drop the AnonyMus folder from your file manager into the terminal window. It should look something like:
```powershell
cd "C:\Users\YourName\Desktop\AnonyMus"
```
Press **Enter**.

---

## Step 4: Create and Start Your Virtual Environment

A virtual environment is a clean, isolated container on your computer where the app's packages will live.

### 1. Create the container:
Type this command and press **Enter**:
```bash
python -m venv venv
```
*(Wait 10 seconds for it to finish)*

### 2. Turn on the container:
- **On Windows (PowerShell):**
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
  *(If you get a red security error, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` first, then run the activate command again).*
- **On macOS / Linux:**
  ```bash
  source venv/bin/activate
  ```

Once activated, you will see `(venv)` at the beginning of your terminal line.

---

## Step 5: Install the App's Requirements

Type this command and press **Enter**:
```bash
pip install -r requirements.txt
```
*(This will download the Flask web server, cryptographic libraries, and other dependencies. It takes about 30 seconds).*

---

## Step 6: Configure Environment Variables

The server uses an environment configuration file for credentials and security keys.

1. In the AnonyMus folder, find the file named `.env.example`.
2. Duplicate or copy it, and rename the new copy to `.env`.
3. Open the `.env` file in a text editor (like Notepad).
4. Fill in or edit the fields (or leave them as default for local testing). Make sure `FLASK_SECRET_KEY` is a long random string of letters and numbers for safety.

---

## Step 7: Run the Centralized Server!

Type this command and press **Enter**:
```bash
python server.py
```

### What happens now?
- The Flask server will start.
- It will print a line like:
  `* Running on http://127.0.0.1:5000`

Copy `http://127.0.0.1:5000` and paste it into your browser to access the chat login screen!

---

## Step 8: (Optional) Host as a Tor Hidden Service (BROKEN!!!)

If you want people to connect to your server anonymously from outside your local network without doing complex router setup (port forwarding):

1. **Install Tor on your computer:**
   - **Debian/Ubuntu:** `sudo apt install tor`
   - **macOS:** `brew install tor`
   - **Windows:** Download the **Tor Expert Bundle** or the **Tor Browser** from [torproject.org](https://www.torproject.org/).

2. **Configure Tor (`torrc`):**
   Open the Tor configuration file (called `torrc`) in a text editor:
   - **Debian/Ubuntu:** Located at `/etc/tor/torrc`
   - **macOS:** Located at `/usr/local/etc/tor/torrc` or `/opt/homebrew/etc/tor/torrc`
   - **Windows (Tor Browser):** Located at `[Tor Browser Folder]\Browser\TorBrowser\Data\Tor\torrc`
   - **Windows (Tor Expert Bundle):** Located at `[Installation Directory]\Data\Tor\torrc` (or create a file named `torrc` in your installation folder).

   Append the configuration lines at the bottom of the file depending on your operating system:

   **For Linux / macOS:**
   ```text
   HiddenServiceDir /var/lib/tor/anonymus_hidden_service/
   HiddenServicePort 80 127.0.0.1:5000
   ```

   **For Windows:**
   ```text
   HiddenServiceDir C:/Users/Public/anonymus_hidden_service/
   HiddenServicePort 80 127.0.0.1:5000
   ```
   *(Note: On Windows, using a path under `C:/Users/Public/` avoids folder permission errors. Ensure you use forward slashes `/` as shown above).*

3. **Restart Tor:**
   - **Debian/Ubuntu:** Run `sudo systemctl restart tor`
   - **macOS:** Run `brew services restart tor`
   - **Windows:** Completely close and reopen the Tor Browser, or restart the Tor command prompt window/service.

4. **Find your address:**
   Tor will generate a unique `.onion` address for your server. Read the address inside the generated `hostname` file:
   - **Linux / macOS:** Run `sudo cat /var/lib/tor/anonymus_hidden_service/hostname`
   - **Windows:** Open the folder `C:\Users\Public\anonymus_hidden_service\` in File Explorer and open the `hostname` file with Notepad.

   Provide this `.onion` address to your friends. They can open it using the **Tor Browser** to access your chat server securely and anonymously!
