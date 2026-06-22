# AnonyMus — User Setup & Usage Guide

Welcome to **AnonyMus**, a zero-knowledge, end-to-end encrypted (E2EE) private messaging application. AnonyMus stores no chat logs, exposes no metadata, and keeps your communication completely ephemeral.

This guide will walk you through setting up and using either the **Web Client** or the **Android Mobile App** to establish a secure, private connection with your peer.

---

## 1. Getting Started: Web App vs. Mobile App

You can access AnonyMus in two ways:
*   **Web App:** Open your browser and navigate to the secure URL provided by your server developer (e.g., `https://chat.yourdomain.com`).
*   **Android App:** Sideload the `AnonyMus.apk` onto your Android device.

---

## 2. Using the Android Mobile App

### Step 2.1: Sideload & Install the APK
1. Download the `AnonyMus.apk` file onto your Android device.
2. Tap the file to install it. If prompted with a warning about installing apps from "Unknown Sources," navigate to your settings and toggle **Allow from this source** to proceed.

### Step 2.2: Server Configuration (First Run)
Upon launching the Android app for the first time, you will see the **Server Configuration** screen:
1. **Server Host / IP:** Enter your host/domain name (e.g., `chat.yourdomain.com`). If you are on the same local Wi-Fi network as a locally running server, you can enter the local IP address (e.g., `192.168.1.100`).
2. **Port:** Enter `443` for standard production HTTPS, or `5000` for a local development setup.
3. **Trust Self-Signed Certificates:** If the developer is hosting locally using a self-signed SSL certificate, check this box. If you are connecting to a production site with a valid SSL certificate (like Let's Encrypt), leave it unchecked.
4. **Auto-Detect Server (Optional):** If you are on the same Wi-Fi network as the server, tap **Auto-Detect Local Server (mDNS)** to automatically scan and find the server IP.
5. Tap **Save and Connect**.

### Step 2.3: Register or Log In
Because accounts are tied to your specific physical device for authentication:
1. **Registering a New Account:** If this is your first time, choose a username and password and tap **Register**. 
2. **Logging In:** Enter your registered credentials and tap **Login**.
   > [!IMPORTANT]
   > **Device-Lock Protection**: Once registered, your account is locked to your physical device ID. You cannot log in to your account from another device. If you lose or switch devices, you must register a new username.

---

## 3. Starting a Secure Zero-Knowledge Chat

AnonyMus uses **ECDH Key Agreement** to establish a secure channel. No messages can be sent or read until a direct handshake is performed between two peers.

### Step 3.1: Generating an Invite Link (Host)
If you are starting the conversation:
1. Log in to the application.
2. You will be presented with a **Zero-Knowledge Setup** screen.
3. Copy your secure **Invite Link** or display the **QR Code**.
4. Share the link or QR Code with your peer using a secure channel.
   * *Web Link Format:* `https://chat.yourdomain.com/#q=...&k=...`
   * *Android Link Format:* `anonymus://join?q=...&k=...`

### Step 3.2: Accepting an Invite (Invitee)
If you received an invite link:
*   **On Android:** 
    *   Clicking the `anonymus://join` link will automatically launch the app and connect.
    *   Alternatively, copy the link, open the app, navigate to the **Or Join Peer's Invite** box at the bottom, paste the link (either the web or custom URI format), and tap **Connect to Peer**.
*   **On the Web:**
    *   Open the link in your web browser.
    *   Click the **Accept & Connect** button.

Once both sides connect, the screen will switch to the **Private Chat** screen, showing a status indicator: `[Connected Securely]` or `Peer connected securely.`

---

## 4. Advanced Privacy & Security Features

AnonyMus includes several layers of advanced anti-forensics to protect your device and chat.

### Feature 4.1: Safety Numbers
At the top of your chat screen, you will see a 12-digit **Safety Number** (e.g., `0452-9843-1250`).
*   Verify this safety number with your peer out-of-band (e.g., in person or via voice call).
*   If the numbers match exactly on both devices, it guarantees that no Man-in-the-Middle (MITM) attack is occurring.

### Feature 4.2: Disappearing Messages
*   **How it works:** Tap the timer dropdown at the top right of the screen (on Web or Android) and choose an expiration limit (**15 Seconds** or **60 Seconds**).
*   All subsequent messages sent or received will be automatically erased from both the screen and device memory after the selected period.

### Feature 4.3: Covert Mode (Alt + C / Shield Icon)
If you need to quickly hide your chat in public:
*   **Android:** Tap the **Visibility Off (Eye)** icon at the top. The screen instantly transforms into a fully functional-looking fake **Calculator UI**. To exit Covert Mode and return to your chat, tap the `=` button.
*   **Web Client:** Press **Alt + C** on your keyboard to toggle the calculator overlay.

### Feature 4.4: Clipboard Auto-Clearing
*   If you copy any text from the chat window (on Web or Android), a background timer will automatically clear your system clipboard 30 seconds later, preventing accidental leaks to other apps.

### Feature 4.5: Screen Security (Android Only)
*   The Android app is configured to block system screenshots and hide screen content in the task switcher, preventing forensic screen capture.

### Feature 4.6: Panic Button (Triple-Esc / Warning Icon)
If your physical environment is compromised:
*   **Android:** Tap the **Warning/Panic (Triangle)** icon in the top right.
*   **Web Client:** Quickly press the **Escape** key three times on your keyboard.
*   **Effect:** The application will instantly overwrite session keys in RAM with zeros, clear the system clipboard, delete active chat objects, and force-close/redirect the browser to google.com.
