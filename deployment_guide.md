# AnonyMus Developer \& Deployment Guide (Global Production Release)

> \*\*AGPLv3 License Notice\*\*: AnonyMus is distributed under the \*\*GNU Affero General Public License v3 (AGPLv3)\*\*. If you run a modified version of this application as a service over the network, you \*\*must\*\* make your modified source code available to your users.

To make AnonyMus globally accessible while protecting your backend server IP and ensuring strict End-to-End Encryption transport requirements (Web Crypto API requires HTTPS), follow this step-by-step production deployment guide.

\---

## Architecture Overview

```mermaid
graph TD
    A\[Android Client / Web Browser] -->|HTTPS / WSS| B(Cloudflare Proxy)
    B -->|Encrypted Tunnel / HTTPS| C(Render PaaS Backend)
    C -->|SQL Queries| D\[(Supabase / Neon PostgreSQL)]
    C -.->|Tor Ephemeral Service| E((Tor Network))
```

1. **Application Server:** Python Flask-SocketIO app hosted on Render (Free Tier).
2. **Database:** Supabase or Neon PostgreSQL (Free Tier) to store device registration hashes.
3. **DNS, SSL \& Security:** Cloudflare Proxy (Free Tier) to mask origin IP and provide DDoS / WAF protection.
4. **Android Client:** Pointed to your custom Cloudflare-proxied domain.

\---

## Step 1: Setup a Persistent Production Database

Render's free tier uses an ephemeral file system, meaning the default local SQLite `users.db` is deleted every time the server restarts or goes to sleep. We have built dynamic database switching into `database.py`. If a `DATABASE\_URL` is detected, the server automatically connects to PostgreSQL.

1. Sign up for a free account at [Supabase](https://supabase.com) or [Neon PostgreSQL](https://neon.tech).
2. Create a new project.
3. Retrieve your **Connection String**. Select the **URI/Connection Pooler** format (looks like: `postgres://username:password@host:port/database`).
4. Save this URI. You will enter it as an environment variable in Render.

\---

## Step 2: Deploying the Server on Render

[Render](https://render.com) is ideal for hosting Flask-SocketIO because it supports WebSockets out-of-the-box and has a free tier.

1. Push your AnonyMus codebase (with the updated `requirements.txt` and `database.py`) to a **private** GitHub repository.
2. Sign up or log in to **Render**.
3. In the Render Dashboard, click **New +** and select **Web Service**.
4. Connect your GitHub repository.
5. Configure the Web Service settings:

   * **Name:** `anonymus-relay` (or any unique name)
   * **Environment:** `Python 3`
   * **Region:** Choose the region closest to your user base.
   * **Branch:** `main`
   * **Build Command:** `pip install -r requirements.txt`
   * **Start Command:** `gunicorn --worker-class eventlet -w 1 server:app`
6. Click **Advanced** and add the following **Environment Variables**:

   * `SECRET\_KEY`: Generate a secure random string (e.g., `openssl rand -hex 32`).
   * `DATABASE\_URL`: Paste the PostgreSQL connection string from Step 1.
   * `FLASK\_DEBUG`: `False` (forces secure production headers and logging).
7. Click **Create Web Service**.

*Render will build your app, start it on a free subdomain (e.g., `https://anonymus-relay.onrender.com`), and automatically provision a Let's Encrypt SSL certificate.*

\---

## Step 3: Custom Domain \& Privacy Protection via Cloudflare

To hide the fact that you are using Render, mitigate DDoS attacks, and enforce secure transport policies:

1. Register a domain. You can use free subdomain providers like [FreeDNS.afraid.org](https://freedns.afraid.org) or [EU.org](https://eu.org), or register a standard TLD.
2. Sign up for a free account at [Cloudflare](https://dash.cloudflare.com).
3. Add your domain to Cloudflare and change your domain registrar's name servers to point to the Cloudflare nameservers provided.
4. In the Cloudflare DNS dashboard, add a **CNAME** record:

   * **Type:** `CNAME`
   * **Name:** `@` (or a subdomain like `chat`)
   * **Target:** `anonymus-relay.onrender.com`
   * **Proxy Status:** **Proxied (Orange Cloud ON)**.
5. In Cloudflare, navigate to **SSL/TLS** -> **Overview** and set the encryption mode to **Full (Strict)**. This ensures traffic between Cloudflare and Render is fully encrypted using Render's SSL cert.
6. Navigate to **SSL/TLS** -> **Edge Certificates** and toggle **Always Use HTTPS** to ON.
7. Navigate to **Network** and ensure **WebSockets** and **Onion Routing** are enabled. Onion routing allows Tor browser users to access your site securely without triggering annoying Cloudflare CAPTCHAs.

\---

## Step 4: Compiling \& Configuring the Android App

Once the web server is live at `https://yourdomain.com`:

### Step 4.1: Configure Server URL

1. Open the Android project in Android Studio (or text editor).
2. Open [ConfigScreen.kt](file:///c:/Users/Aryan/OneDrive/Desktop/Coding%20Projects/1-Custom%20Chat%20App/AnonyMus/AnonyMus_android/app/src/main/java/com/example/privacychat/ui/config/ConfigScreen.kt).
3. Set the default fallback host and port on lines 20-21:

```kotlin
   var host by remember { mutableStateOf(prefs.host ?: "yourdomain.com") }
   var port by remember { mutableStateOf(prefs.port?.toString() ?: "443") }
   ```

4. Set `trustSelfSigned` default value to `false` since you are deploying on a production domain with a valid Let's Encrypt/Cloudflare certificate.

### Step 4.2: Build and Sign the Release APK

To build a production-ready APK:

1. Open a terminal in the `AnonyMus\_android` directory.
2. Run the Gradle build command:

```powershell
   ./gradlew assembleRelease
   ```

3. This generates an unsigned release APK at `app/build/outputs/apk/release/app-release-unsigned.apk`.
4. Sign the APK using `apksigner` (from Android SDK Build Tools) to install it on real devices:

```powershell
   # Generate a private key if you don't have one
   keytool -genkey -v -keystore anonymus-release.keystore -alias anonymus-key -keyalg RSA -keysize 2048 -validity 10000
   
   # Align the APK
   zipalign -v 4 app-release-unsigned.apk anonymus-release.apk
   
   # Sign the APK
   apksigner sign --keystore anonymus-release.keystore --out AnonyMus.apk anonymus-release.apk
   ```

5. Distribute the final `AnonyMus.apk` to your users.

\---

## Step 5: Tor Onion Service (Self-Hosted/Raspberry Pi Route)

For complete metadata resistance and server location masking, you can run the server on local hardware (e.g., a Raspberry Pi) and expose it as a Tor Onion Service:

1. Install Tor on the host system:

```bash
   sudo apt update \&\& sudo apt install tor -y
   ```

2. Open `/etc/tor/torrc` in a text editor:

```text
   HiddenServiceDir /var/lib/tor/anonymus\_onion/
   HiddenServicePort 80 127.0.0.1:5000
   ```

3. Restart the Tor daemon:

```bash
   sudo systemctl restart tor
   ```

4. Read your public `.onion` address:

```bash
   sudo cat /var/lib/tor/anonymus\_onion/hostname
   ```

5. Share this hostname with users.

> \[!NOTE]
   > Android users accessing the Onion service must run \[Orbot: Tor for Android](https://orbot.app) and configure it to proxy traffic for the AnonyMus application.

