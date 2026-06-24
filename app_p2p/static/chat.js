(() => {
const socket = io({ transports: ['websocket'] });

// Local UI State
let myOnionAddress = null;
let myLocalUsername = null;
let activeContact = null; // Currently selected contact object

// Cryptographic keys and state mapped by contact onion address
let myKeys = null;
let myPublicKeyExported = null;
let writeKeys = {};
let readKeys = {};

// DOM Elements
const myOnionDisplay = document.getElementById('my-onion-display');
const contactsListEl = document.getElementById('contacts-list');
const contactNicknameInput = document.getElementById('contact-nickname');
const contactOnionInput = document.getElementById('contact-onion');
const btnAddContact = document.getElementById('btn-add-contact');

const viewWelcome = document.getElementById('view-welcome');
const viewPendingIncoming = document.getElementById('view-pending-incoming');
const viewPendingOutgoing = document.getElementById('view-pending-outgoing');
const viewChat = document.getElementById('view-chat');

const pendingRequestText = document.getElementById('pending-request-text');
const btnAcceptIncoming = document.getElementById('btn-accept-incoming');
const btnDenyIncoming = document.getElementById('btn-deny-incoming');

const chattingWithName = document.getElementById('chatting-with-name');
const messagesEl = document.getElementById('messages');
const formEl = document.getElementById('message-form');
const inputEl = document.getElementById('message-input');
const uiSafetyNumber = document.getElementById('ui-safety-number');
const disappearTimerSelect = document.getElementById('disappear-timer');

const btnCalculator = document.getElementById('btn-calculator');
const viewCalculator = document.getElementById('view-calculator');
const btnCalculatorExit = document.getElementById('btn-calculator-exit');
const btnCloseChat = document.getElementById('btn-close-chat');
const btnClearCache = document.getElementById('btn-clear-cache');

// -----------------------------------------------------------------
// Visibility & Security Blur
// -----------------------------------------------------------------
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    document.body.classList.add('blurred');
  } else {
    document.body.classList.remove('blurred');
  }
});

// -----------------------------------------------------------------
// Cryptographic Keys Initializer for Local P2P
// -----------------------------------------------------------------
async function initMyMasterKeys() {
  // Try to load or generate local E2EE keys
  if (!myKeys) {
    myKeys = await generateKeyPair();
    myPublicKeyExported = await exportPublicKey(myKeys.publicKey);
  }
}

async function deriveAndStoreSessionKeys(contact) {
  if (!contact.shared_secret || !contact.peer_public_key) return;
  
  try {
    const sharedSecretBits = fromBase64(contact.shared_secret);
    const hkdfKey = await crypto.subtle.importKey(
      'raw',
      sharedSecretBits,
      { name: 'HKDF' },
      false,
      ['deriveKey']
    );

    const salt = new Uint8Array(32);
    const labelClient = new TextEncoder().encode("AnonyMus-Client-To-Server-Key");
    const labelServer = new TextEncoder().encode("AnonyMus-Server-To-Client-Key");

    const clientKey = await crypto.subtle.deriveKey(
      { name: 'HKDF', hash: 'SHA-256', salt: salt, info: labelClient },
      hkdfKey,
      { name: 'AES-GCM', length: 256 },
      false,
      ['encrypt', 'decrypt']
    );

    const serverKey = await crypto.subtle.deriveKey(
      { name: 'HKDF', hash: 'SHA-256', salt: salt, info: labelServer },
      hkdfKey,
      { name: 'AES-GCM', length: 256 },
      false,
      ['encrypt', 'decrypt']
    );

    const isAlice = myPublicKeyExported < contact.peer_public_key;
    writeKeys[contact.onion_address] = isAlice ? clientKey : serverKey;
    readKeys[contact.onion_address] = isAlice ? serverKey : clientKey;
  } catch (err) {
    console.error("Failed to derive keys for contact:", contact.onion_address, err);
  }
}

// -----------------------------------------------------------------
// UI Control & Panel Management
// -----------------------------------------------------------------
function switchPanel(panelId) {
  viewWelcome.style.display = 'none';
  viewPendingIncoming.style.display = 'none';
  viewPendingOutgoing.style.display = 'none';
  viewChat.style.display = 'none';

  if (panelId === 'welcome') viewWelcome.style.display = 'block';
  else if (panelId === 'pending_incoming') viewPendingIncoming.style.display = 'block';
  else if (panelId === 'pending_outgoing') viewPendingOutgoing.style.display = 'block';
  else if (panelId === 'chat') viewChat.style.display = 'flex';
}

// -----------------------------------------------------------------
// Contacts List Loader
// -----------------------------------------------------------------
async function loadContactsList() {
  try {
    const res = await fetch('/api/contacts');
    const contacts = await res.json();
    
    contactsListEl.innerHTML = '';
    
    for (const contact of contacts) {
      // Pre-derive keys if they are accepted and not in memory
      if (contact.status === 'accepted' && !writeKeys[contact.onion_address]) {
        await deriveAndStoreSessionKeys(contact);
      }

      const li = document.createElement('li');
      li.dataset.onion = contact.onion_address;
      if (activeContact && activeContact.onion_address === contact.onion_address) {
        li.className = 'active';
        // Keep active contact updated
        activeContact = contact;
      }

      const nameSpan = document.createElement('span');
      nameSpan.className = 'contact-name';
      nameSpan.textContent = contact.nickname;
      li.appendChild(nameSpan);

      const addressSpan = document.createElement('span');
      addressSpan.className = 'contact-address';
      addressSpan.textContent = contact.onion_address;
      li.appendChild(addressSpan);

      const statusSpan = document.createElement('span');
      statusSpan.className = `contact-status status-${contact.status}`;
      
      let statusText = contact.status;
      if (contact.status === 'pending_outgoing') statusText = 'waiting...';
      if (contact.status === 'pending_incoming') statusText = 'inbound request';
      statusSpan.textContent = statusText;
      li.appendChild(statusSpan);

      li.addEventListener('click', () => selectContact(contact, li));
      contactsListEl.appendChild(li);
    }
  } catch (err) {
    console.error("Failed to load contacts list:", err);
  }
}

async function selectContact(contact, element) {
  // Clear active styling
  document.querySelectorAll('#contacts-list li').forEach(el => el.classList.remove('active'));
  if (element) element.classList.add('active');
  
  activeContact = contact;

  if (contact.status === 'pending_incoming') {
    pendingRequestText.textContent = `${contact.nickname} (${contact.onion_address}) is requesting to chat.`;
    switchPanel('pending_incoming');
  } else if (contact.status === 'pending_outgoing') {
    switchPanel('pending_outgoing');
  } else if (contact.status === 'accepted' || contact.status === 'offline') {
    chattingWithName.textContent = `Chatting with: ${contact.nickname}`;
    if (contact.peer_public_key) {
      uiSafetyNumber.textContent = await computeSafetyNumber(myPublicKeyExported, contact.peer_public_key);
    } else {
      uiSafetyNumber.textContent = "Deriving...";
    }
    switchPanel('chat');
    await loadMessages(contact.onion_address);
  }
}

// -----------------------------------------------------------------
// Message Loading & Rendering
// -----------------------------------------------------------------
async function loadMessages(onion) {
  try {
    const res = await fetch(`/api/messages?onion=${encodeURIComponent(onion)}`);
    const messages = await res.json();
    
    messagesEl.innerHTML = '';
    
    const isAlice = myPublicKeyExported < activeContact.peer_public_key;
    const myRole = isAlice ? 'A' : 'B';
    const theirRole = isAlice ? 'B' : 'A';

    for (const msg of messages) {
      try {
        const parsed = JSON.parse(msg.message);
        let decrypted = null;
        
        if (msg.sender === 'me') {
          decrypted = await decryptMessage(writeKeys[onion], parsed.iv, parsed.ciphertext, myRole, parsed.seq);
        } else {
          decrypted = await decryptMessage(readKeys[onion], parsed.iv, parsed.ciphertext, theirRole, parsed.seq);
        }

        if (decrypted !== null) {
          const envelope = JSON.parse(decrypted);
          if (envelope.type === 'text') {
            addMessageLine(msg.sender === 'me' ? 'You' : activeContact.nickname, envelope.content, msg.timestamp, true);
          }
        } else {
          addMessageLine(msg.sender === 'me' ? 'You' : activeContact.nickname, '[Decryption Failed - Session Desynced]', msg.timestamp, true);
        }
      } catch (err) {
        console.error("Message decrypt/render error:", err);
      }
    }
  } catch (err) {
    console.error("Failed to load messages:", err);
  }
}

function addMessageLine(sender, text, timestamp, isHistorical = false) {
  const row = document.createElement('div');
  row.className = 'message' + (sender === 'You' ? ' message-own' : '');
  
  const senderSpan = document.createElement('span');
  senderSpan.className = 'message-sender';
  senderSpan.textContent = sender + ':';
  row.appendChild(senderSpan);
  
  row.appendChild(document.createTextNode(' ' + text));
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  // Disappearing messages support
  if (!isHistorical) {
    const timerVal = parseInt(disappearTimerSelect.value, 10);
    if (timerVal > 0) {
      setTimeout(() => {
        if (row.parentNode) row.parentNode.removeChild(row);
      }, timerVal * 1000);
    }
  }
}

function addStatusLine(text) {
  const row = document.createElement('div');
  row.className = 'message-status';
  row.textContent = text;
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// -----------------------------------------------------------------
// Handshake & P2P Event Triggers
// -----------------------------------------------------------------
async function addContactSubmit() {
  const nickname = contactNicknameInput.value.trim();
  const onion = contactOnionInput.value.trim().toLowerCase();

  if (!nickname || !onion.endsWith('.onion')) {
    alert("Please enter a valid nickname and .onion address.");
    return;
  }

  btnAddContact.disabled = true;
  await initMyMasterKeys();

  try {
    const res = await fetch('/api/contacts/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        onion_address: onion,
        nickname: nickname,
        my_public_key: myPublicKeyExported
      })
    });
    const data = await res.json();
    if (data.success) {
      contactNicknameInput.value = '';
      contactOnionInput.value = '';
      await loadContactsList();
      alert("Handshake request queued. Connecting via Tor...");
    } else {
      alert("Error: " + data.error);
    }
  } catch (err) {
    console.error("Failed to add contact:", err);
  } finally {
    btnAddContact.disabled = false;
  }
}

async function acceptIncomingRequest() {
  if (!activeContact) return;
  
  btnAcceptIncoming.disabled = true;
  await initMyMasterKeys();

  try {
    const peerPubKey = await importPublicKey(activeContact.peer_public_key);
    
    // Derive raw shared secret bits
    const sharedSecretBits = await crypto.subtle.deriveBits(
      { name: 'ECDH', public: peerPubKey },
      myKeys.privateKey,
      256
    );
    const sharedSecretB64 = toBase64(sharedSecretBits);
    
    const res = await fetch('/api/contacts/accept', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        onion_address: activeContact.onion_address,
        my_public_key: myPublicKeyExported,
        shared_secret: sharedSecretB64
      })
    });
    
    const data = await res.json();
    if (data.success) {
      // Force immediate derivation locally
      await deriveAndStoreSessionKeys({
        onion_address: activeContact.onion_address,
        shared_secret: sharedSecretB64,
        peer_public_key: activeContact.peer_public_key
      });
      
      await loadContactsList();
      // Select the newly accepted contact to open the chat window
      const updatedContact = await (await fetch(`/api/contacts`)).json();
      const match = updatedContact.find(c => c.onion_address === activeContact.onion_address);
      if (match) selectContact(match);
    } else {
      alert("Accept error: " + data.error);
    }
  } catch (err) {
    console.error("Failed to accept request:", err);
  } finally {
    btnAcceptIncoming.disabled = false;
  }
}

async function denyIncomingRequest() {
  if (!activeContact) return;
  if (!confirm("Are you sure you want to deny this request?")) return;

  try {
    await fetch('/api/contacts/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ onion_address: activeContact.onion_address })
    });
    activeContact = null;
    switchPanel('welcome');
    await loadContactsList();
  } catch (err) {
    console.error("Failed to deny request:", err);
  }
}

// -----------------------------------------------------------------
// Message Sending
// -----------------------------------------------------------------
formEl.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = inputEl.value;
  if (!text.trim() || !activeContact || !writeKeys[activeContact.onion_address]) return;

  const onion = activeContact.onion_address;
  const isAlice = myPublicKeyExported < activeContact.peer_public_key;
  const myRole = isAlice ? 'A' : 'B';
  
  // Load and increment sequence number safely
  let sendSeq = parseInt(localStorage.getItem(`sendSeq_${onion}`) || '0', 10);

  try {
    const plaintext = JSON.stringify({ type: 'text', content: text });
    const { iv, ciphertext } = await encryptMessage(writeKeys[onion], plaintext, myRole, sendSeq);
    
    // Save locally
    const res = await fetch('/api/messages/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        onion_address: onion,
        iv: iv,
        ciphertext: ciphertext,
        seq: sendSeq
      })
    });
    
    const data = await res.json();
    if (data.success) {
      addMessageLine('You', text, data.timestamp);
      localStorage.setItem(`sendSeq_${onion}`, sendSeq + 1);
      inputEl.value = '';
    } else {
      alert("Failed to send message: " + data.error);
    }
  } catch (err) {
    console.error("Encryption or transmission failed:", err);
  }
});

// -----------------------------------------------------------------
// WebSockets Event Listeners (Push Notifications)
// -----------------------------------------------------------------
socket.on('incoming_contact_request', async (data) => {
  await loadContactsList();
  addStatusLine(`New incoming contact request from ${data.nickname}`);
});

socket.on('handshake_accepted', async (data) => {
  // Alice receives Bob's public key response. Compute and save shared secret.
  const peerPubKey = await importPublicKey(data.peer_public_key);
  await initMyMasterKeys();

  const sharedSecretBits = await crypto.subtle.deriveBits(
    { name: 'ECDH', public: peerPubKey },
    myKeys.privateKey,
    256
  );
  const sharedSecretB64 = toBase64(sharedSecretBits);

  // Send derived secret back to local python to persist in local node DB
  await fetch('/api/contacts/save_secret', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      onion_address: data.onion_address,
      shared_secret: sharedSecretB64,
      peer_public_key: data.peer_public_key
    })
  });

  await loadContactsList();
  if (activeContact && activeContact.onion_address === data.onion_address) {
    const updated = await (await fetch(`/api/contacts`)).json();
    const match = updated.find(c => c.onion_address === data.onion_address);
    if (match) selectContact(match);
  }
  addStatusLine(`Handshake accepted by peer.`);
});

socket.on('incoming_message', async (data) => {
  const sender = data.sender;
  const seq = data.seq;
  
  const expectedSeq = parseInt(localStorage.getItem(`recvSeq_${sender}`) || '1', 10);
  if (seq < expectedSeq) {
    console.warn(`Dropped replayed or out-of-order message from ${sender}. Expected seq >= ${expectedSeq}, got ${seq}`);
    return;
  }
  localStorage.setItem(`recvSeq_${sender}`, seq + 1);
  
  if (activeContact && activeContact.onion_address === sender) {
    const isAlice = myPublicKeyExported < activeContact.peer_public_key;
    const theirRole = isAlice ? 'B' : 'A';
    
    const plaintext = await decryptMessage(readKeys[sender], data.iv, data.ciphertext, theirRole, seq);
    if (plaintext !== null) {
      const envelope = JSON.parse(plaintext);
      if (envelope.type === 'text') {
        addMessageLine(activeContact.nickname, envelope.content, data.timestamp);
      }
    } else {
      addMessageLine(activeContact.nickname, '[Decryption Failed - Session Desynced]', data.timestamp);
    }
  }
});

socket.on('contact_status_change', (data) => {
  loadContactsList();
});

socket.on('message_delivery_failed', (data) => {
  addStatusLine(`Message failed. Peer may be offline.`);
});

// -----------------------------------------------------------------
// Clear Data & Reset Session
// -----------------------------------------------------------------
function resetSession(hard = false) {
  myKeys = null;
  writeKeys = {};
  readKeys = {};
  activeContact = null;
  localStorage.clear();
  socket.disconnect();
  document.body.innerHTML = '';
  if (hard) {
    window.location.replace("about:blank");
  } else {
    window.location.replace("/");
  }
}

let escCount = 0;
let escTimeout = null;
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    escCount++;
    clearTimeout(escTimeout);
    if (escCount >= 3) {
      if (confirm('Panic button triggered! Are you sure you want to hard self-destruct? All chat state will be lost immediately.')) {
        fetch('/api/reset-data', { method: 'POST' }).then(() => {
          resetSession(true);
        });
      } else {
        escCount = 0;
      }
    }
    escTimeout = setTimeout(() => { escCount = 0; }, 1000);
  }
});

btnCloseChat.addEventListener('click', () => {
  if (confirm('Are you sure you want to close the connection? All chat state will be lost immediately.')) {
    fetch('/api/reset-data', { method: 'POST' }).then(() => {
      resetSession(false);
    });
  }
});

btnClearCache.addEventListener('click', () => {
  if (confirm('Clear connection cache? This will permanently delete contacts and local messages.')) {
    fetch('/api/reset-data', { method: 'POST' }).then(() => {
      loadContactsList();
      switchPanel('welcome');
      alert("Application cache cleared.");
    });
  }
});

// Calculator stealth cover
btnCalculator.addEventListener('click', () => { viewCalculator.style.display = 'flex'; });
btnCalculatorExit.addEventListener('click', () => { viewCalculator.style.display = 'none'; });

// -----------------------------------------------------------------
// App Init & Startup
// -----------------------------------------------------------------
async function initApp() {
  // 1. Fetch info
  const infoRes = await fetch('/api/my_info');
  const info = await infoRes.json();
  
  myOnionAddress = info.onion_address;
  myLocalUsername = info.local_username;

  let lastCopiedOnion = null;
  myOnionDisplay.textContent = myOnionAddress || "Loading Tor...";
  myOnionDisplay.addEventListener('click', () => {
    if (myOnionAddress) {
      lastCopiedOnion = myOnionAddress;
      navigator.clipboard.writeText(myOnionAddress).then(() => {
        alert("Onion address copied to clipboard!");
        setTimeout(async () => {
          try {
            const currentText = await navigator.clipboard.readText();
            if (currentText === lastCopiedOnion) {
              await navigator.clipboard.writeText('');
              console.log("Clipboard auto-cleared for security.");
            }
          } catch (err) {
            console.warn("Clipboard auto-clear failed:", err);
          }
        }, 30000);
      }).catch(err => console.error("Failed to copy onion address:", err));
    }
  });

  // 2. Generate/Load keypair
  await initMyMasterKeys();

  // 3. Load contacts
  await loadContactsList();
}

document.addEventListener('DOMContentLoaded', () => {
  initApp();
  
  btnAddContact.addEventListener('click', addContactSubmit);
  btnAcceptIncoming.addEventListener('click', acceptIncomingRequest);
  btnDenyIncoming.addEventListener('click', denyIncomingRequest);
  
  document.getElementById('btn-logout').addEventListener('click', async () => {
    await fetch('/logout', { method: 'POST' });
    window.location.href = '/';
  });
});
})();
