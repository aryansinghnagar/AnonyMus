import os
import sys
import unittest
import threading
import time

# Ensure root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# Set env vars for testing
os.environ['DATABASE_URL'] = ''
os.environ['FLASK_SECRET_KEY'] = 'smoke-test-secret-key'
os.environ['DISABLE_SSL'] = 'True'
os.environ['FLASK_DEBUG'] = 'False'
os.environ['DB_FILE'] = 'test_smoke_users.db'

import app_main.database as database

# Try importing Playwright
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

class TestSmokePlaywright(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Clean test DB
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
            
        # Start Flask-SocketIO server as a subprocess on port 5050
        import subprocess
        python_exe = sys.executable
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        cls.server_proc = subprocess.Popen(
            [python_exe, "app_main/server.py"],
            env={
                **os.environ,
                "PYTHONPATH": project_root,
                "PORT": "5050",
                "DISABLE_SSL": "True",
                "FLASK_DEBUG": "True",
                "FLASK_USE_RELOADER": "False",
                "DISABLE_MDNS": "True",
                "DB_FILE": "test_smoke_users.db",
                "FLASK_SECRET_KEY": "smoke-test-secret-key"
            }
        )
        time.sleep(3.0)  # Wait for server to bind

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'server_proc'):
            cls.server_proc.terminate()
            cls.server_proc.wait()
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)

    @unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "Playwright is not installed")
    def test_two_peer_handshake(self):
        with sync_playwright() as p:
            # Launch headless browser
            browser = p.chromium.launch(headless=True)
            
            # Peer A (Alice)
            context_a = browser.new_context()
            page_a = context_a.new_page()
            page_a.on("console", lambda msg: print(f"ALICE CONSOLE: {msg.text}"))
            
            # Peer B (Bob)
            context_b = browser.new_context()
            page_b = context_b.new_page()
            page_b.on("console", lambda msg: print(f"BOB CONSOLE: {msg.text}"))
            
            # 1. Register & Login Alice
            page_a.goto("http://127.0.0.1:5050/")
            page_a.click("#link-to-register")
            page_a.fill("#reg-username", "alice")
            page_a.fill("#reg-password", "Password123!")
            page_a.click("#btn-register")
            
            # Python-side polling to comply with CSP and avoid eval()
            success_a = page_a.locator("#reg-success")
            for _ in range(50):
                if success_a.inner_text() != "":
                    break
                time.sleep(0.1)
            else:
                self.fail("Alice registration success message not set")
                
            page_a.click("#link-to-login")
            page_a.fill("#login-username", "alice")
            page_a.fill("#login-password", "Password123!")
            page_a.click("#btn-login")
            page_a.wait_for_url("**/chat")
            
            # 2. Register & Login Bob
            page_b.goto("http://127.0.0.1:5050/")
            page_b.click("#link-to-register")
            page_b.fill("#reg-username", "bob")
            page_b.fill("#reg-password", "Password123!")
            page_b.click("#btn-register")
            
            success_b = page_b.locator("#reg-success")
            for _ in range(50):
                if success_b.inner_text() != "":
                    break
                time.sleep(0.1)
            else:
                self.fail("Bob registration success message not set")
                
            page_b.click("#link-to-login")
            page_b.fill("#login-username", "bob")
            page_b.fill("#login-password", "Password123!")
            page_b.click("#btn-login")
            page_b.wait_for_url("**/chat")
            
            # 3. Alice copies invite link
            # Wait for invite link display to change from "Generating..."
            invite_display = page_a.locator("#invite-link-display")
            for _ in range(50):
                text = invite_display.inner_text()
                if text.startswith("http"):
                    break
                time.sleep(0.1)
            else:
                self.fail("Invite link was not generated")
            invite_link = invite_display.inner_text()
            
            # 4. Bob pastes invite link and connects
            page_b.fill("#paste-invite-input", invite_link)
            page_b.click("#btn-paste-connect")
            
            # Bob should see the "Inbound Invitation" view
            page_b.wait_for_selector("#btn-accept-invite", state="visible")
            page_b.click("#btn-accept-invite")
            
            # Both should see active chat view
            page_a.wait_for_selector("#view-chat", state="visible")
            page_b.wait_for_selector("#view-chat", state="visible")
            
            # 5. Alice sends a message
            page_a.fill("#message-input", "Hello Bob, this is encrypted!")
            page_a.click("#send-btn")
            
            # Bob should receive the message
            page_b.wait_for_selector("text=Hello Bob, this is encrypted!")
            
            # 6. Bob replies
            page_b.fill("#message-input", "Hi Alice, got your secure message!")
            page_b.click("#send-btn")
            
            # Alice should receive the reply
            page_a.wait_for_selector("text=Hi Alice, got your secure message!")
            
            browser.close()

if __name__ == '__main__':
    unittest.main()
