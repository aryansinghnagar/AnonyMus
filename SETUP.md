# Layman's Setup Guide — AnonyMus P2P

Welcome to AnonyMus P2P! This guide is written for absolute beginners. You do **not** need to be a software developer or have command-line experience to set up and run your own private, serverless chat node. Just follow these steps carefully.

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
*(This will download the Flask web server, cryptographic libraries, and networking tools needed to talk over the Tor network. It takes about 30 seconds).*

---

## Step 6: Start Your Chat Node!

Type this command and press **Enter**:
```bash
python server.py
```

### What happens now?
- The app will automatically detect your operating system.
- It will automatically download the official **Tor Expert Bundle** in the background (you do **not** need to install Tor manually!).
- It will start Tor, generate your unique `.onion` address, and run the Flask local server.
- The terminal will print a line like:
  `Flask running local control panel on http://127.0.0.1:8080`

---

## Step 7: How to Chat (P2P Walkthrough)

1. **Open the App:** Copy the link `http://127.0.0.1:8080` (or whatever port was printed) and paste it into any web browser.
2. **Create Your Account:** Choose a username (e.g. `alice`) and a strong master password. This password encrypts your local database. Click **Initialize**.
3. **Log In:** Log in with the credentials you just created.
4. **Copy Your Onion Address:** Click on the profile icon or Settings in the chat window. You will see a long address ending in `.onion`. This is your unique identity. Copy and share it with your friend.
5. **Add a Friend:** Get your friend's `.onion` address. Paste it in the "Add Contact" field, give them a nickname, and click **Add**.
6. **Accept the Request:** When your friend opens their app, they will see a notification of a pending request from you. Once they click **Accept**, the two browsers will securely negotiate a secret key.
7. **Start Chatting:** Tap your friend's name and send a message! Your messages are encrypted in your browser and sent directly to your friend's computer over the Tor network.
