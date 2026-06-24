const socket = io({ transports: ['websocket'] });

const chatSession = {
  myKeys: null,
  myPublicKeyExported: null,
  myQueueId: null,
  theirQueueId: null,
  theirPublicKeyExported: null,
  sendChainKey: null,
  recvChainKey: null,
  sessionId: null, // safety number/hash
  myRole: null, // 'A' or 'B'
  theirRole: null, // 'B' or 'A'
  sendSeq: 0,
  recvSeq: 0,
  lastCopiedInviteUrl: null,
  disappearTimer: 0, // negotiated timer in seconds
  
  reset() {
    this.myKeys = null;
    this.myPublicKeyExported = null;
    this.myQueueId = null;
    this.theirQueueId = null;
    this.theirPublicKeyExported = null;
    this.sendChainKey = null;
    this.recvChainKey = null;
    this.sessionId = null;
    this.myRole = null;
    this.theirRole = null;
    this.sendSeq = 0;
    this.recvSeq = 0;
    this.lastCopiedInviteUrl = null;
    this.disappearTimer = 0;
  }
};

// DOM Elements
const viewSetup = document.getElementById('view-setup');
const viewJoin = document.getElementById('view-join');
const viewChat = document.getElementById('view-chat');

const inviteLinkDisplay = document.getElementById('invite-link-display');
const btnAcceptInvite = document.getElementById('btn-accept-invite');

const messagesEl = document.getElementById('messages');
const formEl = document.getElementById('message-form');
const inputEl = document.getElementById('message-input');
const uiSafetyNumber = document.getElementById('ui-safety-number');
const disappearTimerSelect = document.getElementById('disappear-timer');

const qrcodeEl = document.getElementById('qrcode');
const pasteInviteInput = document.getElementById('paste-invite-input');
const btnPasteConnect = document.getElementById('btn-paste-connect');
const btnCalculator = document.getElementById('btn-calculator');
const viewCalculator = document.getElementById('view-calculator');
const btnCalculatorExit = document.getElementById('btn-calculator-exit');
const btnCloseChat = document.getElementById('btn-close-chat');
const btnClearCache = document.getElementById('btn-clear-cache');

let staticInterval = null;

// -----------------------------------------------------------------
// Screen Security & Panic Action
// -----------------------------------------------------------------
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    document.body.classList.add('blurred');
  } else {
    document.body.classList.remove('blurred');
  }
});

function resetSession() {
  chatSession.reset();
  if (staticInterval) clearTimeout(staticInterval);
  
  socket.disconnect();
  document.body.innerHTML = '';
  
  // Best-effort key material sanitization
  chatSession.writeKey = null;
  chatSession.readKey = null;
  chatSession.myKeys = null;
  chatSession.sendChainKey = null;
  chatSession.recvChainKey = null;

  // Force a minor GC trigger by allocating and releasing a large buffer
  const buf = new ArrayBuffer(16 * 1024 * 1024); // 16MB
  setTimeout(() => {}, 0);

  window.location.replace("about:blank");
}

let escCount = 0;
let escTimeout = null;
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    escCount++;
    clearTimeout(escTimeout);
    if (escCount >= 3) {
      if (confirm('Are you sure you want to close the connection? All chat state will be lost immediately.')) {
        resetSession();
      } else {
        escCount = 0;
      }
    }
    escTimeout = setTimeout(() => { escCount = 0; }, 1000);
  }
});

btnCloseChat.addEventListener('click', () => {
  if (confirm('Are you sure you want to close the connection? All chat state will be lost immediately.')) {
    resetSession();
  }
});

btnClearCache.addEventListener('click', () => {
  if (confirm('Clear connection cache? This will permanently delete the chat history for both you and your peer, and close the session.')) {
    if (chatSession.sendChainKey && chatSession.theirQueueId) {
      const plaintext = JSON.stringify({ type: 'control', action: 'clear' });
      deriveChainKeys(chatSession.sendChainKey).then(({ messageKey, nextChainKey }) => {
        chatSession.sendChainKey = nextChainKey;
        encryptMessage(messageKey, plaintext, chatSession.myRole, chatSession.sendSeq, chatSession.sessionId).then(({iv, ciphertext}) => {
          chatSession.sendSeq++;
          const payload = JSON.stringify({
            type: 'message',
            iv,
            ciphertext
          });
          socket.emit('push_queue', { queue_id: chatSession.theirQueueId, payload });
          resetSession();
        });
      }).catch(err => {
        console.error(err);
        resetSession();
      });
    } else {
      resetSession();
    }
  }
});

btnCalculator.addEventListener('click', () => {
  viewCalculator.style.display = 'flex';
});

btnCalculatorExit.addEventListener('click', () => {
  viewCalculator.style.display = 'none';
});

function startKeepAlive() {
  if (staticInterval) clearTimeout(staticInterval);
  
  async function sendKeepAlive() {
    if (chatSession.sendChainKey && chatSession.theirQueueId) {
      try {
        const { messageKey, nextChainKey } = await deriveChainKeys(chatSession.sendChainKey);
        chatSession.sendChainKey = nextChainKey;
        
        const plaintext = JSON.stringify({ type: 'control', action: 'heartbeat' });
        const { iv, ciphertext } = await encryptMessage(messageKey, plaintext, chatSession.myRole, chatSession.sendSeq, chatSession.sessionId);
        chatSession.sendSeq++;
        const payload = JSON.stringify({
          type: 'message',
          iv,
          ciphertext
        });
        socket.emit('push_queue', { queue_id: chatSession.theirQueueId, payload });
      } catch (err) {
        console.error("KeepAlive error:", err);
      }
    }
    // Web Keep-Alive optimized to 10-30s random interval
    staticInterval = setTimeout(sendKeepAlive, Math.random() * 20000 + 10000);
  }
  
  staticInterval = setTimeout(sendKeepAlive, 2000);
}

function addMessageLine(sender, text, disappearAfter = chatSession.disappearTimer) {
  const row = document.createElement('div');
  row.className = 'message' + (sender === 'You' ? ' message-own' : ' message-other');
  
  const senderSpan = document.createElement('span');
  senderSpan.className = 'message-sender';
  senderSpan.textContent = sender + ':';
  row.appendChild(senderSpan);
  
  const contentNode = document.createTextNode(' ' + text);
  row.appendChild(contentNode);
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  // Disappearing logic with visual countdown
  if (disappearAfter > 0) {
    const timerSpan = document.createElement('span');
    timerSpan.className = 'message-timer';
    timerSpan.textContent = `${disappearAfter}s`;
    row.appendChild(timerSpan);
    
    let remaining = disappearAfter;
    const interval = setInterval(() => {
      remaining--;
      if (remaining <= 0) {
        clearInterval(interval);
        if (row.parentNode) {
          row.classList.add('fading-out');
          setTimeout(() => {
            if (row.parentNode) row.parentNode.removeChild(row);
          }, 500);
        }
      } else {
        timerSpan.textContent = `${remaining}s`;
        if (remaining <= 5) {
          row.classList.add('expiring');
        }
      }
    }, 1000);
  }
  
  // Freeze nodes for best effort dev tools protection
  Object.freeze(row);
  Object.freeze(contentNode);
}

function addStatusLine(text) {
  const row = document.createElement('div');
  row.className = 'message-status';
  row.textContent = text;
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// -----------------------------------------------------------------
// Initialization & Routing
// -----------------------------------------------------------------
socket.on('connect', async () => {
  if (!window.crypto || !window.crypto.subtle) {
    document.getElementById('warning-banner').innerHTML = 'Security Alert: Web Crypto API requires HTTPS or localhost.';
    document.getElementById('warning-banner').style.display = 'block';
    return;
  }

  if (!chatSession.myKeys) {
    chatSession.myKeys = await generateKeyPair();
    chatSession.myPublicKeyExported = await exportPublicKey(chatSession.myKeys.publicKey);
  }
  
  socket.emit('create_queue');
});

socket.on('queue_created', ({ queue_id }) => {
  chatSession.myQueueId = queue_id;
  
  if (chatSession.theirQueueId && chatSession.sendChainKey) {
    // Host queue rotation for invite link single-use (burn-after-reading)
    const payload = JSON.stringify({
      type: 'queue_update',
      new_queue: chatSession.myQueueId
    });
    socket.emit('push_queue', { queue_id: chatSession.theirQueueId, payload });
    
    // Register the new rotated queue with the peer
    socket.emit('register_peer', {
      my_queue: chatSession.myQueueId,
      peer_queue: chatSession.theirQueueId
    });
    return;
  }

  const hashParams = new URLSearchParams(window.location.hash.slice(1));
  if (hashParams.has('q') && hashParams.has('k')) {
    // We are the invitee
    viewSetup.classList.remove('active');
    viewJoin.classList.add('active');
    chatSession.theirQueueId = hashParams.get('q');
    chatSession.theirPublicKeyExported = decodeURIComponent(hashParams.get('k'));
  } else {
    // We are the host
    viewSetup.classList.add('active');
    viewJoin.classList.remove('active');
    const inviteUrl = `${window.location.origin}/#q=${chatSession.myQueueId}&k=${encodeURIComponent(chatSession.myPublicKeyExported)}`;
    inviteLinkDisplay.textContent = inviteUrl;
    if (typeof QRCode !== 'undefined') {
      qrcodeEl.innerHTML = '';
      new QRCode(qrcodeEl, {
        text: inviteUrl,
        width: 200,
        height: 200,
        colorDark : "#000000",
        colorLight : "#ffffff",
        correctLevel : QRCode.CorrectLevel.L
      });
    }
  }
});

socket.on('disconnect', () => {
  addStatusLine('Disconnected from server. Attempting to reconnect...');
});

socket.on('connect_error', (err) => {
  if (err && err.message === "Connection rejected by server") {
    addStatusLine('Session expired. Redirecting to login...');
    setTimeout(() => {
      logoutUser();
    }, 2000);
  }
});

function copyInviteLink() {
  const inviteUrl = inviteLinkDisplay.textContent;
  chatSession.lastCopiedInviteUrl = inviteUrl;
  navigator.clipboard.writeText(inviteUrl).then(() => {
    alert('Invite link copied!');
    setTimeout(async () => {
      try {
        const currentText = await navigator.clipboard.readText();
        if (currentText === chatSession.lastCopiedInviteUrl) {
          await navigator.clipboard.writeText('');
          console.log('Clipboard auto-cleared for security.');
        }
      } catch (err) {
        console.warn('Could not auto-clear clipboard:', err);
      }
    }, 30000);
  }).catch(err => console.error("Failed to copy invite link", err));
}

btnPasteConnect.addEventListener('click', () => {
  const link = pasteInviteInput.value;
  if (!link) return;
  
  btnPasteConnect.disabled = true;
  try {
    const normalized = link.replace("#q=", "?q=").replace("#", "?");
    const url = new URL(normalized);
    const q = url.searchParams.get('q');
    const k = url.searchParams.get('k');
    
    if (q && k) {
      window.location.hash = `#q=${q}&k=${k}`;
      window.location.reload(); 
    } else {
      alert("Invalid invite link.");
      btnPasteConnect.disabled = false;
    }
  } catch (e) {
    alert("Invalid invite link format.");
    btnPasteConnect.disabled = false;
  }
});

// Invitee accepts the invite
btnAcceptInvite.addEventListener('click', async () => {
  btnAcceptInvite.disabled = true;
  try {
    viewJoin.classList.remove('active');
    viewChat.style.display = 'flex';
    
    // Compute Secret & Safety Number
    const theirKey = await importPublicKey(chatSession.theirPublicKeyExported);
    
    const sessionKeys = await deriveSessionKeys(chatSession.myKeys.privateKey, theirKey, chatSession.myPublicKeyExported, chatSession.theirPublicKeyExported);
    chatSession.sendChainKey = sessionKeys.sendChainKey;
    chatSession.recvChainKey = sessionKeys.recvChainKey;
    
    const isAlice = chatSession.myPublicKeyExported < chatSession.theirPublicKeyExported;
    chatSession.myRole = isAlice ? 'A' : 'B';
    chatSession.theirRole = isAlice ? 'B' : 'A';
    chatSession.sendSeq = 0;
    chatSession.recvSeq = 0;
    
    chatSession.sessionId = await computeSafetyNumber(chatSession.myPublicKeyExported, chatSession.theirPublicKeyExported);
    uiSafetyNumber.textContent = chatSession.sessionId;

    // Send Handshake payload to their queue (handshake is unencrypted)
    const payload = JSON.stringify({
      type: 'handshake',
      reply_queue: chatSession.myQueueId,
      public_key: chatSession.myPublicKeyExported
    });
    socket.emit('push_queue', { queue_id: chatSession.theirQueueId, payload });
    
    // Register peer queue ownership for backend verification
    socket.emit('register_peer', {
      my_queue: chatSession.myQueueId,
      peer_queue: chatSession.theirQueueId
    });

    addStatusLine('Connected to peer. Awaiting their response...');
    history.replaceState(null, null, ' ');
    startKeepAlive();
  } catch (err) {
    console.error('Handshake failed:', err);
    alert('Failed to securely connect to peer. Invalid link?');
    btnAcceptInvite.disabled = false;
    viewJoin.classList.add('active');
    viewChat.style.display = 'none';
  }
});

// -----------------------------------------------------------------
// Message Handling
// -----------------------------------------------------------------
socket.on('queue_payload', async ({ queue_id, payload }) => {
  try {
    const data = JSON.parse(payload);
    
    if (data.type === 'handshake') {
      try {
        chatSession.theirQueueId = data.reply_queue;
        chatSession.theirPublicKeyExported = data.public_key;
        
        const theirKey = await importPublicKey(chatSession.theirPublicKeyExported);
        
        const sessionKeys = await deriveSessionKeys(chatSession.myKeys.privateKey, theirKey, chatSession.myPublicKeyExported, chatSession.theirPublicKeyExported);
        chatSession.sendChainKey = sessionKeys.sendChainKey;
        chatSession.recvChainKey = sessionKeys.recvChainKey;
        
        const isAlice = chatSession.myPublicKeyExported < chatSession.theirPublicKeyExported;
        chatSession.myRole = isAlice ? 'A' : 'B';
        chatSession.theirRole = isAlice ? 'B' : 'A';
        chatSession.sendSeq = 0;
        chatSession.recvSeq = 0;
        
        chatSession.sessionId = await computeSafetyNumber(chatSession.myPublicKeyExported, chatSession.theirPublicKeyExported);
        uiSafetyNumber.textContent = chatSession.sessionId;
        
        // Register peer queue ownership for backend verification
        socket.emit('register_peer', {
          my_queue: chatSession.myQueueId,
          peer_queue: chatSession.theirQueueId
        });

        // Rotate our queue to burn the old invite link
        socket.emit('create_queue');

        viewSetup.classList.remove('active');
        viewChat.style.display = 'flex';
        addStatusLine('Peer connected securely.');
        startKeepAlive();
      } catch(err) {
        console.error('Handshake verification failed', err);
        addStatusLine('Handshake verification failed!');
      }
      return;
    }

    if (data.type === 'queue_update') {
       chatSession.theirQueueId = data.new_queue;
       addStatusLine('Peer updated secure channel.');
       return;
    }

    if (data.type === 'message') {
      if (!chatSession.recvChainKey) return;
      try {
        const { messageKey, nextChainKey } = await deriveChainKeys(chatSession.recvChainKey);
        
        const plaintext = await decryptMessage(messageKey, data.iv, data.ciphertext, chatSession.theirRole, chatSession.recvSeq, chatSession.sessionId);
        
        if (plaintext !== null) {
          chatSession.recvChainKey = nextChainKey;
          chatSession.recvSeq++;
          const msgObj = JSON.parse(plaintext);
          
          if (msgObj.type === 'control') {
            if (msgObj.action === 'heartbeat' || msgObj.action === 'static') return;
            if (msgObj.action === 'clear' || msgObj.action === 'obliviate') {
              resetSession();
              alert('Connection closed by peer. Chat history cleared.');
              return;
            }
            if (msgObj.action === 'timer_set') {
              const duration = msgObj.duration_seconds;
              chatSession.disappearTimer = duration;
              disappearTimerSelect.value = duration;
              addStatusLine(`Peer set disappearing messages to ${duration > 0 ? duration + ' seconds' : 'Off'}.`);
              
              // Send timer_ack using send chain
              const { messageKey: sendMsgKey, nextChainKey: nextSendChain } = await deriveChainKeys(chatSession.sendChainKey);
              chatSession.sendChainKey = nextSendChain;
              
              const plaintextAck = JSON.stringify({
                type: 'control',
                action: 'timer_ack',
                duration_seconds: duration,
                mode: 'session'
              });
              const { iv, ciphertext } = await encryptMessage(sendMsgKey, plaintextAck, chatSession.myRole, chatSession.sendSeq, chatSession.sessionId);
              chatSession.sendSeq++;
              
              const payload = JSON.stringify({ type: 'message', iv, ciphertext });
              socket.emit('push_queue', { queue_id: chatSession.theirQueueId, payload });
              return;
            }
            if (msgObj.action === 'timer_ack') {
              const duration = msgObj.duration_seconds;
              chatSession.disappearTimer = duration;
              disappearTimerSelect.value = duration;
              addStatusLine(`Peer confirmed disappearing messages timer: ${duration > 0 ? duration + ' seconds' : 'Off'}.`);
              return;
            }
          } else if (msgObj.type === 'text') {
            addMessageLine('Peer', msgObj.content);
          }
        } else {
          addMessageLine('Peer', '[Decryption Failed - Session Desynced]');
        }
      } catch (err) {
        console.error("Message processing failed:", err);
      }
    }
  } catch (err) {
    console.error("Payload parsing error:", err);
  }
});

socket.on('push_queue_error', ({ queue_id, error }) => {
  if (error === 'recipient_offline') {
    addStatusLine('Message delivery failed: Peer is offline.');
  }
});

formEl.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = inputEl.value;
  if (!text.trim() || !chatSession.sendChainKey || !chatSession.theirQueueId) return;

  try {
    const { messageKey, nextChainKey } = await deriveChainKeys(chatSession.sendChainKey);
    chatSession.sendChainKey = nextChainKey;

    const plaintext = JSON.stringify({ type: 'text', content: text });
    const { iv, ciphertext } = await encryptMessage(messageKey, plaintext, chatSession.myRole, chatSession.sendSeq, chatSession.sessionId);
    chatSession.sendSeq++;
    
    const payload = JSON.stringify({
      type: 'message',
      iv,
      ciphertext
    });
    socket.emit('push_queue', { queue_id: chatSession.theirQueueId, payload });

    addMessageLine('You', text);
    inputEl.value = '';
  } catch (err) {
    console.error("Encryption/Transmission failed:", err);
  }
});

// Dropdown change listener to negotiate timer with peer
disappearTimerSelect.addEventListener('change', async () => {
  const val = parseInt(disappearTimerSelect.value, 10);
  chatSession.disappearTimer = val;
  
  if (chatSession.sendChainKey && chatSession.theirQueueId) {
    try {
      const { messageKey, nextChainKey } = await deriveChainKeys(chatSession.sendChainKey);
      chatSession.sendChainKey = nextChainKey;
      
      const plaintext = JSON.stringify({
        type: 'control',
        action: 'timer_set',
        duration_seconds: val,
        mode: 'session'
      });
      const { iv, ciphertext } = await encryptMessage(messageKey, plaintext, chatSession.myRole, chatSession.sendSeq, chatSession.sessionId);
      chatSession.sendSeq++;
      
      const payload = JSON.stringify({ type: 'message', iv, ciphertext });
      socket.emit('push_queue', { queue_id: chatSession.theirQueueId, payload });
    } catch (err) {
      console.error(err);
    }
  }
});

// -----------------------------------------------------------------
// Logout Functionality
// -----------------------------------------------------------------
async function logoutUser() {
  try {
    await fetch('/logout', { method: 'POST' });
    window.location.href = '/';
  } catch (err) {
    console.error(err);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const btnLogout = document.getElementById('btn-logout');
  if (btnLogout) btnLogout.addEventListener('click', logoutUser);

  const btnCopyInvite = document.getElementById('btn-copy-invite');
  if (btnCopyInvite) btnCopyInvite.addEventListener('click', copyInviteLink);
});
