/**
 * chat.js — Application controller for AnonyMus (Unified Architecture).
 * Manages Socket.IO handlers, DOM actions, and cryptographic ratchets for Relay and P2P modes.
 */

(() => {
const socket = io({ transports: ['websocket'] });

// ---------------------------------------------------------------------------
// Shared State & DOM Elements
// ---------------------------------------------------------------------------
const warningBanner = document.getElementById('warning-banner');
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

// Stealth Calculator Cover
if (btnCalculator) btnCalculator.addEventListener('click', () => { viewCalculator.style.display = 'flex'; });
if (btnCalculatorExit) btnCalculatorExit.addEventListener('click', () => { viewCalculator.style.display = 'none'; });

// Visibility & Security Blur
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    document.body.classList.add('blurred');
  } else {
    document.body.classList.remove('blurred');
  }
});

// UI Views Switcher
function switchPanel(panelId) {
  // Hide all view containers
  document.querySelectorAll('.view-container').forEach(el => {
    el.classList.remove('active');
    el.style.display = 'none';
  });
  
  // Show target panel
  const panel = document.getElementById('view-' + panelId);
  if (panel) {
    panel.classList.add('active');
    panel.style.display = 'block';
  }
}

// Log status messages helper
function addStatusLine(text) {
  const statusEl = document.createElement('div');
  statusEl.className = 'message-status';
  statusEl.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
  messagesEl.appendChild(statusEl);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// Log chat messages helper
function addMessageLine(sender, text, timestamp = Date.now(), isSystem = false) {
  const msgEl = document.createElement('div');
  msgEl.className = `message ${sender === 'You' || sender === 'me' ? 'message-own' : 'message-other'}`;
  
  const senderSpan = document.createElement('span');
  senderSpan.className = 'message-sender';
  senderSpan.textContent = sender;
  
  const contentSpan = document.createElement('span');
  contentSpan.textContent = text;
  
  msgEl.appendChild(senderSpan);
  msgEl.appendChild(contentSpan);
  
  // Setup disappear timer if enabled
  const timerDuration = parseInt(disappearTimerSelect.value, 10);
  if (timerDuration > 0) {
    const timerSpan = document.createElement('span');
    timerSpan.className = 'message-timer';
    timerSpan.textContent = `⏳ ${timerDuration}s`;
    msgEl.appendChild(timerSpan);
    
    // Countdown and remove
    let timeLeft = timerDuration;
    const interval = setInterval(() => {
      timeLeft--;
      if (timeLeft <= 0) {
        clearInterval(interval);
        msgEl.classList.add('fading-out');
        setTimeout(() => msgEl.remove(), 500);
      } else {
        timerSpan.textContent = `⏳ ${timeLeft}s`;
      }
    }, 1000);
  }
  
  messagesEl.appendChild(msgEl);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}


// ---------------------------------------------------------------------------
// A. CENTRALIZED RELAY MODE LOGIC
// ---------------------------------------------------------------------------
let relaySession = {
  myKeys: null,
  myPublicKeyExported: null,
  theirPublicKeyExported: null,
  myQueueId: null,
  theirQueueId: null,
  sendChainKey: null,
  recvChainKey: null,
  sendSeq: 0,
  recvSeq: 0,
  sessionId: null,
  myRole: null,
  theirRole: null,
  keepAliveInterval: null
};

// Start keepalive heartbeat
function startRelayKeepAlive() {
  if (relaySession.keepAliveInterval) clearInterval(relaySession.keepAliveInterval);
  relaySession.keepAliveInterval = setInterval(async () => {
    if (relaySession.sendChainKey && relaySession.theirQueueId) {
      try {
        const { messageKey, nextChainKey } = await deriveChainKeys(relaySession.sendChainKey);
        relaySession.sendChainKey = nextChainKey;
        
        const heartbeat = JSON.stringify({ type: 'control', action: 'heartbeat' });
        const { iv, ciphertext } = await encryptMessage(messageKey, heartbeat, relaySession.myRole, relaySession.sendSeq, relaySession.sessionId);
        relaySession.sendSeq++;
        
        const payload = JSON.stringify({ type: 'message', iv, ciphertext });
        socket.emit('push_queue', { queue_id: relaySession.theirQueueId, payload });
      } catch (err) {
        console.error(err);
      }
    }
  }, 20000);
}

// Generate invitation link
async function generateRelayInvite() {
  try {
    relaySession.myKeys = await generateKeyPair();
    relaySession.myPublicKeyExported = await exportPublicKey(relaySession.myKeys.publicKey);
    
    socket.emit('create_queue');
  } catch (err) {
    console.error("Invite generation failed:", err);
  }
}

// Accept invite handler
async function acceptRelayInvite() {
  try {
    const inviteLink = pasteInviteInput.value.trim();
    if (!inviteLink) return;
    
    const hashIdx = inviteLink.indexOf('#');
    if (hashIdx === -1) {
      alert("Invalid invite link format.");
      return;
    }
    
    const hashData = JSON.parse(decodeURIComponent(inviteLink.substring(hashIdx + 1)));
    relaySession.theirQueueId = hashData.q;
    relaySession.theirPublicKeyExported = hashData.k;
    
    relaySession.myKeys = await generateKeyPair();
    relaySession.myPublicKeyExported = await exportPublicKey(relaySession.myKeys.publicKey);
    
    // Set up ratchets
    const theirKey = await importPublicKey(relaySession.theirPublicKeyExported);
    const sessionKeys = await deriveSessionKeys(
      relaySession.myKeys.privateKey,
      theirKey,
      relaySession.myPublicKeyExported,
      relaySession.theirPublicKeyExported
    );
    relaySession.sendChainKey = sessionKeys.sendChainKey;
    relaySession.recvChainKey = sessionKeys.recvChainKey;
    
    const isAlice = relaySession.myPublicKeyExported < relaySession.theirPublicKeyExported;
    relaySession.myRole = isAlice ? 'A' : 'B';
    relaySession.theirRole = isAlice ? 'B' : 'A';
    relaySession.sendSeq = 0;
    relaySession.recvSeq = 0;
    
    relaySession.sessionId = await computeSafetyNumber(relaySession.myPublicKeyExported, relaySession.theirPublicKeyExported);
    uiSafetyNumber.textContent = relaySession.sessionId;
    
    // Register queues
    socket.emit('register_peer', {
      my_queue: relaySession.myQueueId,
      peer_queue: relaySession.theirQueueId
    });
    
    // Notify peer of our public key
    const handshakePayload = JSON.stringify({
      type: 'handshake',
      reply_queue: relaySession.myQueueId,
      public_key: relaySession.myPublicKeyExported
    });
    socket.emit('push_queue', { queue_id: relaySession.theirQueueId, payload: handshakePayload });
    
    switchPanel('chat');
    addStatusLine("Connected securely to peer.");
    startRelayKeepAlive();
  } catch (err) {
    console.error("Accept invite failed:", err);
    alert("Connection failed.");
  }
}

// Socket handler for relay queues
function mountRelaySocketEvents() {
  socket.on('queue_created', ({ queue_id }) => {
    relaySession.myQueueId = queue_id;
    
    // Update invite link view
    const inviteLinkDisplay = document.getElementById('invite-link-display');
    const hashObj = { q: queue_id, k: relaySession.myPublicKeyExported };
    const inviteUrl = `${window.location.origin}/#${encodeURIComponent(JSON.stringify(hashObj))}`;
    
    if (inviteLinkDisplay) inviteLinkDisplay.textContent = inviteUrl;
  });
  
  socket.on('queue_payload', async ({ queue_id, payload }) => {
    try {
      const data = JSON.parse(payload);
      
      // Peer Handshake Acceptance
      if (data.type === 'handshake') {
        relaySession.theirQueueId = data.reply_queue;
        relaySession.theirPublicKeyExported = data.public_key;
        
        const theirKey = await importPublicKey(relaySession.theirPublicKeyExported);
        const sessionKeys = await deriveSessionKeys(
          relaySession.myKeys.privateKey,
          theirKey,
          relaySession.myPublicKeyExported,
          relaySession.theirPublicKeyExported
        );
        relaySession.sendChainKey = sessionKeys.sendChainKey;
        relaySession.recvChainKey = sessionKeys.recvChainKey;
        
        const isAlice = relaySession.myPublicKeyExported < relaySession.theirPublicKeyExported;
        relaySession.myRole = isAlice ? 'A' : 'B';
        relaySession.theirRole = isAlice ? 'B' : 'A';
        relaySession.sendSeq = 0;
        relaySession.recvSeq = 0;
        
        relaySession.sessionId = await computeSafetyNumber(relaySession.myPublicKeyExported, relaySession.theirPublicKeyExported);
        uiSafetyNumber.textContent = relaySession.sessionId;
        
        socket.emit('register_peer', {
          my_queue: relaySession.myQueueId,
          peer_queue: relaySession.theirQueueId
        });
        
        // Burn invite
        socket.emit('create_queue');
        
        switchPanel('chat');
        addStatusLine("Peer connected securely.");
        startRelayKeepAlive();
        return;
      }
      
      // Decrypt inbound messages using receiver ratchet
      if (data.type === 'message') {
        if (!relaySession.recvChainKey) return;
        
        const { messageKey, nextChainKey } = await deriveChainKeys(relaySession.recvChainKey);
        const plaintext = await decryptMessage(
          messageKey,
          data.iv,
          data.ciphertext,
          relaySession.theirRole,
          relaySession.recvSeq,
          relaySession.sessionId
        );
        
        if (plaintext !== null) {
          relaySession.recvChainKey = nextChainKey;
          relaySession.recvSeq++;
          const msgObj = JSON.parse(plaintext);
          
          if (msgObj.type === 'text') {
            addMessageLine('Peer', msgObj.content);
          } else if (msgObj.type === 'control') {
            if (msgObj.action === 'timer_set') {
              disappearTimerSelect.value = msgObj.duration_seconds;
              addStatusLine(`Peer updated disappearing messages to ${msgObj.duration_seconds} seconds.`);
            }
          }
        } else {
          addMessageLine('Peer', '[Decryption Failed - Session Desynced]');
        }
      }
    } catch (err) {
      console.error("Error parsing payload:", err);
    }
  });

  socket.on('push_queue_error', ({ error }) => {
    if (error === 'recipient_offline') {
      addStatusLine("Message delivery failed: Peer is offline.");
    }
  });
}


// ---------------------------------------------------------------------------
// B. DECENTRALIZED TOR P2P MODE LOGIC
// ---------------------------------------------------------------------------
let myOnionAddress = null;
let myLocalUsername = null;
let activeContact = null;

let myKeys = null;
let myPublicKeyExported = null;

// Ratchet state mapped by contact onion address
let chainKeys = {};
let sessionIds = {};

async function initMyMasterKeys() {
  if (!myKeys) {
    myKeys = await generateKeyPair();
    myPublicKeyExported = await exportPublicKey(myKeys.publicKey);
  }
}

// Derive and store ratchet chains for a contact on startup/acceptance
async function initSessionKeysForContact(contact) {
  if (!contact.shared_secret || !contact.peer_public_key) return;
  try {
    const sharedSecretBits = fromBase64(contact.shared_secret);
    const hkdfKey = await crypto.subtle.importKey(
      'raw',
      sharedSecretBits,
      { name: 'HKDF' },
      false,
      ['deriveKey', 'deriveBits']
    );

    const salt = new Uint8Array(32);
    const labelClient = new TextEncoder().encode("AnonyMus-Client-To-Server-Key");
    const labelServer = new TextEncoder().encode("AnonyMus-Server-To-Client-Key");

    const clientChainKeyBits = await crypto.subtle.deriveBits(
      { name: 'HKDF', hash: 'SHA-256', salt: salt, info: labelClient },
      hkdfKey,
      256
    );

    const serverChainKeyBits = await crypto.subtle.deriveBits(
      { name: 'HKDF', hash: 'SHA-256', salt: salt, info: labelServer },
      hkdfKey,
      256
    );

    const isAlice = myPublicKeyExported < contact.peer_public_key;
    chainKeys[contact.onion_address] = {
      sendChainKey: isAlice ? clientChainKeyBits : serverChainKeyBits,
      recvChainKey: isAlice ? serverChainKeyBits : clientChainKeyBits
    };
    
    sessionIds[contact.onion_address] = await computeSafetyNumber(myPublicKeyExported, contact.peer_public_key);
  } catch (err) {
    console.error("Failed to initialize session keys for P2P contact:", err);
  }
}

// Render contacts directory
async function loadContactsList() {
  try {
    const res = await fetch('/api/contacts');
    const contacts = await res.json();
    
    contactsListEl.innerHTML = '';
    
    for (const c of contacts) {
      // Lazy initialize keys for accepted peers
      if (c.status === 'accepted' && !chainKeys[c.onion_address]) {
        await initSessionKeysForContact(c);
      }
      
      const li = document.createElement('li');
      if (activeContact && activeContact.onion_address === c.onion_address) {
        li.className = 'active';
      }
      
      const nameSpan = document.createElement('span');
      nameSpan.className = 'contact-name';
      nameSpan.textContent = c.nickname;
      
      const addrSpan = document.createElement('span');
      addrSpan.className = 'contact-address';
      addrSpan.textContent = c.onion_address;
      
      const statusSpan = document.createElement('span');
      statusSpan.className = `contact-status status-${c.status}`;
      statusSpan.textContent = c.status.replace('_', ' ');
      
      li.appendChild(nameSpan);
      li.appendChild(addrSpan);
      li.appendChild(statusSpan);
      
      li.addEventListener('click', () => selectContact(c));
      contactsListEl.appendChild(li);
    }
  } catch (err) {
    console.error("Failed to load contacts directory:", err);
  }
}

// Switch chat panels based on selected contact status
function selectContact(contact) {
  activeContact = contact;
  
  // Highlight in sidebar
  document.querySelectorAll('.contacts-list-p2p li').forEach(el => el.classList.remove('active'));
  loadContactsList();
  
  if (contact.status === 'pending_incoming') {
    switchPanel('pending-incoming');
    pendingRequestText.innerHTML = `<strong>${contact.nickname}</strong> (${contact.onion_address}) is requesting a chat connection.`;
  } else if (contact.status === 'pending_outgoing') {
    switchPanel('pending-outgoing');
  } else if (contact.status === 'accepted') {
    switchPanel('chat');
    chattingWithName.textContent = `Chatting with: ${contact.nickname}`;
    
    const sessionId = sessionIds[contact.onion_address] || '...';
    uiSafetyNumber.textContent = sessionId;
    
    messagesEl.innerHTML = '';
    loadMessagesHistory(contact.onion_address);
  }
}

// Load message history from DB
async function loadMessagesHistory(onion) {
  try {
    const res = await fetch(`/api/messages?onion=${onion}`);
    const msgs = await res.json();
    
    const isAlice = myPublicKeyExported < activeContact.peer_public_key;
    const myRole = isAlice ? 'A' : 'B';
    const theirRole = isAlice ? 'B' : 'A';
    
    let tempRecvSeq = 0;
    let tempSendSeq = 0;
    
    // Make sure we have the initial chains loaded
    const baseSendChain = chainKeys[onion].sendChainKey;
    const baseRecvChain = chainKeys[onion].recvChainKey;
    
    let currentSendChain = baseSendChain;
    let currentRecvChain = baseRecvChain;
    
    for (const m of msgs) {
      try {
        const payload = JSON.parse(m.message);
        let decrypted = null;
        
        const sessionId = sessionIds[onion];
        
        if (m.sender === 'me') {
          const { messageKey, nextChainKey } = await deriveChainKeys(currentSendChain);
          currentSendChain = nextChainKey;
          decrypted = await decryptMessage(messageKey, payload.iv, payload.ciphertext, myRole, tempSendSeq, sessionId);
          tempSendSeq++;
        } else {
          const { messageKey, nextChainKey } = await deriveChainKeys(currentRecvChain);
          currentRecvChain = nextChainKey;
          decrypted = await decryptMessage(messageKey, payload.iv, payload.ciphertext, theirRole, tempRecvSeq, sessionId);
          tempRecvSeq++;
        }
        
        if (decrypted) {
          const envelope = JSON.parse(decrypted);
          if (envelope.type === 'text') {
            addMessageLine(m.sender === 'me' ? 'You' : activeContact.nickname, envelope.content, m.timestamp);
          }
        } else {
          addMessageLine(m.sender === 'me' ? 'You' : activeContact.nickname, '[Decryption Failed]', m.timestamp);
        }
      } catch (err) {
        console.error(err);
      }
    }
    
    // Save current sequence values in localStorage for the active UI session
    localStorage.setItem(`sendSeq_${onion}`, tempSendSeq);
    localStorage.setItem(`recvSeq_${onion}`, tempRecvSeq);
    
  } catch (err) {
    console.error("Failed to load message history:", err);
  }
}

// Add Peer Form Submission
async function addContactSubmit() {
  const nickname = contactNicknameInput.value.trim();
  const onion = contactOnionInput.value.trim();
  
  if (!nickname || !onion) {
    alert("Please fill in nickname and onion fields.");
    return;
  }
  
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
      alert("Handshake request dispatched successfully over Tor.");
    } else {
      alert("Error: " + data.error);
    }
  } catch (err) {
    console.error(err);
  }
}

// Accept incoming contact handshake request
async function acceptIncomingRequest() {
  if (!activeContact) return;
  
  await initMyMasterKeys();
  
  const peerPubKey = await importPublicKey(activeContact.peer_public_key);
  const sharedSecretBits = await crypto.subtle.deriveBits(
    { name: 'ECDH', public: peerPubKey },
    myKeys.privateKey,
    256
  );
  
  const sharedSecretB64 = toBase64(sharedSecretBits);
  
  try {
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
      // Re-fetch contact details containing updated secret and reload UI
      const updated = await (await fetch('/api/contacts')).json();
      const match = updated.find(c => c.onion_address === activeContact.onion_address);
      if (match) {
        await initSessionKeysForContact(match);
        selectContact(match);
      }
    }
  } catch (err) {
    console.error(err);
  }
}

// Deny incoming contact request
async function denyIncomingRequest() {
  if (!activeContact || !confirm("Deny this contact request?")) return;
  try {
    const res = await fetch('/api/contacts/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ onion_address: activeContact.onion_address })
    });
    const data = await res.json();
    if (data.success) {
      activeContact = null;
      switchPanel('welcome');
      loadContactsList();
    }
  } catch (err) {
    console.error(err);
  }
}

// Socket handlers for P2P network
function mountP2PSocketEvents() {
  socket.on('incoming_contact_request', async (data) => {
    await loadContactsList();
    addStatusLine(`New incoming contact request from ${data.nickname}`);
  });
  
  socket.on('handshake_accepted', async (data) => {
    const peerPubKey = await importPublicKey(data.peer_public_key);
    await initMyMasterKeys();
    
    const sharedSecretBits = await crypto.subtle.deriveBits(
      { name: 'ECDH', public: peerPubKey },
      myKeys.privateKey,
      256
    );
    const sharedSecretB64 = toBase64(sharedSecretBits);
    
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
      const updated = await (await fetch('/api/contacts')).json();
      const match = updated.find(c => c.onion_address === data.onion_address);
      if (match) selectContact(match);
    }
    addStatusLine(`Handshake request accepted by peer.`);
  });
  
  socket.on('incoming_message', async (data) => {
    const sender = data.sender;
    const seq = data.seq;
    
    const expectedSeq = parseInt(localStorage.getItem(`recvSeq_${sender}`) || '0', 10);
    if (seq < expectedSeq) {
      console.warn(`Dropped duplicate/out-of-order message from ${sender}.`);
      return;
    }
    
    if (activeContact && activeContact.onion_address === sender) {
      const chainState = chainKeys[sender];
      if (!chainState || !chainState.recvChainKey) return;
      
      const isAlice = myPublicKeyExported < activeContact.peer_public_key;
      const theirRole = isAlice ? 'B' : 'A';
      
      const { messageKey, nextChainKey } = await deriveChainKeys(chainState.recvChainKey);
      chainState.recvChainKey = nextChainKey;
      
      const plaintext = await decryptMessage(messageKey, data.iv, data.ciphertext, theirRole, seq, sessionIds[sender]);
      if (plaintext !== null) {
        chainKeys[sender].recvSeq = seq + 1;
        localStorage.setItem(`recvSeq_${sender}`, seq + 1);
        
        const envelope = JSON.parse(plaintext);
        if (envelope.type === 'text') {
          addMessageLine(activeContact.nickname, envelope.content, data.timestamp);
        }
      } else {
        addMessageLine(activeContact.nickname, '[Decryption Failed]', data.timestamp);
      }
    }
  });
  
  socket.on('contact_status_change', () => {
    loadContactsList();
  });
  
  socket.on('message_delivery_failed', () => {
    addStatusLine("Message delivery failed. Peer may be offline.");
  });
}


// ---------------------------------------------------------------------------
// C. UNIFIED CONTROLLER ENGINE
// ---------------------------------------------------------------------------

// Send chat message (toggled by mode)
formEl.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = inputEl.value;
  if (!text.trim()) return;

  const mode = window.ANONYMUS_MODE || 'relay';
  
  if (mode === 'relay') {
    if (!relaySession.sendChainKey || !relaySession.theirQueueId) return;
    try {
      const { messageKey, nextChainKey } = await deriveChainKeys(relaySession.sendChainKey);
      relaySession.sendChainKey = nextChainKey;
      
      const plaintext = JSON.stringify({ type: 'text', content: text });
      const { iv, ciphertext } = await encryptMessage(
        messageKey,
        plaintext,
        relaySession.myRole,
        relaySession.sendSeq,
        relaySession.sessionId
      );
      relaySession.sendSeq++;
      
      const payload = JSON.stringify({ type: 'message', iv, ciphertext });
      socket.emit('push_queue', { queue_id: relaySession.theirQueueId, payload });
      
      addMessageLine('You', text);
      inputEl.value = '';
    } catch (err) {
      console.error(err);
    }
  } else {
    // P2P Mode message sending
    if (!activeContact || !chainKeys[activeContact.onion_address]) return;
    const onion = activeContact.onion_address;
    
    const isAlice = myPublicKeyExported < activeContact.peer_public_key;
    const myRole = isAlice ? 'A' : 'B';
    
    let sendSeq = parseInt(localStorage.getItem(`sendSeq_${onion}`) || '0', 10);
    const chainState = chainKeys[onion];
    
    try {
      const { messageKey, nextChainKey } = await deriveChainKeys(chainState.sendChainKey);
      chainState.sendChainKey = nextChainKey;
      
      const plaintext = JSON.stringify({ type: 'text', content: text });
      const { iv, ciphertext } = await encryptMessage(messageKey, plaintext, myRole, sendSeq, sessionIds[onion]);
      
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
      console.error(err);
    }
  }
});

// Settings modal changes timer negotiate
disappearTimerSelect.addEventListener('change', async () => {
  const val = parseInt(disappearTimerSelect.value, 10);
  const mode = window.ANONYMUS_MODE || 'relay';
  
  if (mode === 'relay') {
    if (relaySession.sendChainKey && relaySession.theirQueueId) {
      try {
        const { messageKey, nextChainKey } = await deriveChainKeys(relaySession.sendChainKey);
        relaySession.sendChainKey = nextChainKey;
        
        const plaintext = JSON.stringify({ type: 'control', action: 'timer_set', duration_seconds: val });
        const { iv, ciphertext } = await encryptMessage(
          messageKey,
          plaintext,
          relaySession.myRole,
          relaySession.sendSeq,
          relaySession.sessionId
        );
        relaySession.sendSeq++;
        
        socket.emit('push_queue', {
          queue_id: relaySession.theirQueueId,
          payload: JSON.stringify({ type: 'message', iv, ciphertext })
        });
      } catch (err) {
        console.error(err);
      }
    }
  }
});

// App Session Reset / Logout helper
function resetClientSession(hard = false) {
  localStorage.clear();
  socket.disconnect();
  document.body.innerHTML = '';
  window.location.replace(hard ? "about:blank" : "/");
}

async function handleSystemLogout() {
  await fetch('/logout', { method: 'POST' });
  resetClientSession(false);
}

// App startup initializer
async function initApp() {
  const mode = window.ANONYMUS_MODE || 'relay';
  
  // Register unified logout triggers
  const btnLogout = document.getElementById('btn-logout');
  if (btnLogout) btnLogout.addEventListener('click', handleSystemLogout);

  // Close chat or clear cache triggers
  if (btnCloseChat) {
    btnCloseChat.addEventListener('click', () => {
      if (confirm("Reset active session and erase all state?")) {
        if (mode === 'p2p') {
          fetch('/api/reset-data', { method: 'POST' }).then(() => resetClientSession(false));
        } else {
          resetClientSession(false);
        }
      }
    });
  }
  
  if (btnClearCache) {
    btnClearCache.addEventListener('click', () => {
      if (confirm("Clear local cache? Contacts and logs will be permanently deleted.")) {
        if (mode === 'p2p') {
          fetch('/api/reset-data', { method: 'POST' }).then(() => {
            loadContactsList();
            switchPanel('welcome');
            alert("Local storage wiped.");
          });
        } else {
          resetClientSession(false);
        }
      }
    });
  }

  // Dispatch mode configurations
  if (mode === 'relay') {
    mountRelaySocketEvents();
    
    // If client joins using a hash link
    const hasHash = window.location.hash.length > 1;
    if (hasHash) {
      switchPanel('join');
      const btnAcceptInvite = document.getElementById('btn-accept-invite');
      if (btnAcceptInvite) btnAcceptInvite.addEventListener('click', acceptRelayInvite);
    } else {
      switchPanel('setup');
      const btnCopyInvite = document.getElementById('btn-copy-invite');
      if (btnCopyInvite) btnCopyInvite.addEventListener('click', () => {
        const display = document.getElementById('invite-link-display');
        if (display && display.textContent !== "Generating...") {
          navigator.clipboard.writeText(display.textContent).then(() => {
            alert("Invite link copied!");
            // Auto clear clipboard in 30s
            const inviteUrl = display.textContent;
            setTimeout(() => {
              navigator.clipboard.readText().then(val => {
                if (val === inviteUrl) navigator.clipboard.writeText('');
              });
            }, 30000);
          });
        }
      });
      const btnPasteConnect = document.getElementById('btn-paste-connect');
      if (btnPasteConnect) btnPasteConnect.addEventListener('click', acceptRelayInvite);
      const pasteInviteInput = document.getElementById('paste-invite-input');
      
      generateRelayInvite();
    }
  } else {
    // P2P Mode startup
    mountP2PSocketEvents();
    
    const btnAddContact = document.getElementById('btn-add-contact');
    if (btnAddContact) btnAddContact.addEventListener('click', addContactSubmit);
    const btnAcceptIncoming = document.getElementById('btn-accept-incoming');
    if (btnAcceptIncoming) btnAcceptIncoming.addEventListener('click', acceptIncomingRequest);
    const btnDenyIncoming = document.getElementById('btn-deny-incoming');
    if (btnDenyIncoming) btnDenyIncoming.addEventListener('click', denyIncomingRequest);
    
    const myOnionDisplay = document.getElementById('my-onion-display');
    const infoRes = await fetch('/api/my_info');
    const info = await infoRes.json();
    
    myOnionAddress = info.onion_address;
    myLocalUsername = info.local_username;
    
    if (myOnionDisplay) {
      myOnionDisplay.textContent = myOnionAddress || "Loading Tor...";
      myOnionDisplay.addEventListener('click', () => {
        if (myOnionAddress) {
          navigator.clipboard.writeText(myOnionAddress).then(() => {
            alert("My Onion URL copied!");
            setTimeout(() => {
              navigator.clipboard.readText().then(val => {
                if (val === myOnionAddress) navigator.clipboard.writeText('');
              });
            }, 30000);
          });
        }
      });
    }

    await initMyMasterKeys();
    await loadContactsList();
  }
}

initApp();
})();
