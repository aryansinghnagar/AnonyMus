"""
Terminal CLI Client for AnonyMus (P2P Architecture).
Provides a command-line REPL shell using cmd.Cmd and the AnonyMus Python SDK.
"""

import os
import sys
import cmd
import time
import getpass
from core.sdk import AnonyMusClient

ASCII_ART = r"""
    ___                            __  ___           
   /   |  ____  ____  ____  __  __/  |/  /_  _______ 
  / /| | / __ \/ __ \/ __ \/ / / / /|_/ / / / / ___/ 
 / ___ |/ / / / /_/ / / / / /_/ / /  / / /_/ (__  )  
/_/  |_/_/ /_/\____/_/ /_/\__, /_/  /_/\__,_/____/   
                         /____/                      
             Terminal Client v0.9.0-beta
"""

class AnonyMusShell(cmd.Cmd):
    intro = 'Welcome to the AnonyMus Terminal Client. Type help or ? to list commands.\n'
    prompt = '(anonymus) '

    def __init__(self, client):
        super().__init__()
        self.client = client
        self.client.on_message(self._on_incoming_message)
        self.client.start_listening()

    def _on_incoming_message(self, sender, text, timestamp):
        # Format timestamp
        local_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp / 1000.0))
        sys.stdout.write(f"\n[{local_time}] Incoming from {sender}:\n  {text}\n")
        sys.stdout.write(self.prompt)
        sys.stdout.flush()

    def do_info(self, arg):
        """Display local node information: info"""
        if not self.client.my_onion:
            print("Not connected to local server or not logged in.")
            return
        print(f"Local Username: {self.client.username}")
        print(f"My Onion Address: {self.client.my_onion}")
        print(f"My Public Key: {self.client.public_key_b64[:30]}...")

    def do_contacts(self, arg):
        """List all contacts, their status, and safety numbers: contacts"""
        try:
            res = self.client.session.get(f"{self.client.base_url}/api/contacts")
            if res.status_code != 200:
                print("Error fetching contacts.")
                return
            contacts = res.json()
            if not contacts:
                print("No contacts found.")
                return
                
            print(f"\n{'Nickname':<15} | {'Onion Address':<60} | {'Status':<18} | {'Safety Number':<25}")
            print("-" * 125)
            for c in contacts:
                onion = c.get("onion_address")
                status = c.get("status")
                safety_num = self.client.session_ids.get(onion, "N/A")
                print(f"{c.get('nickname'):<15} | {onion:<60} | {status:<18} | {safety_num[:25]}")
            print("")
        except Exception as e:
            print(f"Error: {e}")

    def do_connect(self, arg):
        """Initiate handshake invite with a remote P2P onion address: connect <onion_address> <nickname>"""
        parts = arg.split()
        if len(parts) < 2:
            print("Usage: connect <onion_address> <nickname>")
            return
        onion = parts[0].strip().lower()
        nickname = parts[1].strip()
        
        success = self.client.add_contact(onion, nickname)
        if success:
            print(f"Handshake request successfully sent to {onion}!")
        else:
            print("Failed to dispatch handshake request.")

    def do_accept(self, arg):
        """Accept a pending incoming contact handshake request: accept <onion_address>"""
        onion = arg.strip().lower()
        if not onion:
            print("Usage: accept <onion_address>")
            return
        success = self.client.accept_contact(onion)
        if success:
            print(f"Successfully accepted handshake from {onion}!")
        else:
            print("Failed to accept handshake request.")

    def do_send(self, arg):
        """Send an encrypted message to a contact: send <onion_address> <message_text>"""
        parts = arg.split(maxsplit=1)
        if len(parts) < 2:
            print("Usage: send <onion_address> <message_text>")
            return
        onion = parts[0].strip().lower()
        text = parts[1].strip()
        
        success = self.client.send_message(onion, text)
        if success:
            print("Message encrypted and queued for delivery.")
        else:
            print("Failed to send message.")

    def do_history(self, arg):
        """Retrieve historical message logs for a contact: history <onion_address>"""
        onion = arg.strip().lower()
        if not onion:
            print("Usage: history <onion_address>")
            return
        msgs = self.client.get_messages(onion)
        if not msgs:
            print("No messages found or decryption failed.")
            return
            
        print(f"\n--- Chat History with {onion} ---")
        for m in msgs:
            local_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(m['timestamp'] / 1000.0))
            sender_label = "Me" if m['sender'] == 'me' else "Peer"
            print(f"[{local_time}] {sender_label}: {m['text']}")
        print("---------------------------------\n")

    def do_quit(self, arg):
        """Exit the terminal client: quit"""
        print("Goodbye!")
        self.client.disconnect()
        return True

    def do_EOF(self, arg):
        """Exit the terminal client on EOF (Ctrl+D)"""
        print("")
        return self.do_quit(arg)


def main():
    print(ASCII_ART)
    port = os.environ.get('PORT', 5000)
    base_url = f"http://127.0.0.1:{port}"
    
    client = AnonyMusClient(base_url=base_url)
    
    # Simple interactive auth
    print("Welcome! Please log in or register.")
    while True:
        action = input("Choose action (login [l], register [r], quit [q]): ").strip().lower()
        if action in ('l', 'login'):
            username = input("Username: ").strip()
            password = getpass.getpass("Password: ")
            
            print("Authenticating...")
            if client.login(username, password):
                print(f"Logged in successfully as '{username}'!")
                break
            else:
                print("Login failed. Check server status or credentials.")
        elif action in ('r', 'register'):
            username = input("New Username: ").strip()
            password = getpass.getpass("New Password: ")
            confirm = getpass.getpass("Confirm Password: ")
            if password != confirm:
                print("Passwords do not match.")
                continue
                
            print("Registering...")
            res = client.register(username, password)
            if res.get("success"):
                print("Registration successful! You can now log in.")
            else:
                print(f"Registration failed: {res.get('error', 'unknown error')}")
        elif action in ('q', 'quit', 'exit'):
            print("Exiting...")
            sys.exit(0)
        else:
            print("Invalid option.")

    shell = AnonyMusShell(client)
    shell.cmdloop()


if __name__ == '__main__':
    main()
