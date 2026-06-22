const socket = io({ transports: ['websocket'] });

let myKeys = null;
let myPublicKeyExported = null;
let myQueueId = null;

let theirQueueId = null;
let theirPublicKeyExported = null;
let writeKey = null;
let readKey = null;
let myRole = null; // 'A' or 'B'
let theirRole = null; // 'B' or 'A'
let sendSeq = 0;
let recvSeq = 0;

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
const btnElvenCloak = document.getElementById('btn-elven-cloak');
const viewElvenCloak = document.getElementById('view-elven-cloak');
const btnElvenCloakExit = document.getElementById('btn-elven-cloak-exit');
const btnInfinitySnap = document.getElementById('btn-infinity-snap');
const btnObliviate = document.getElementById('btn-obliviate');

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

function triggerInfinitySnap() {
  myKeys = null;
  writeKey = null;
  readKey = null;
  myRole = null;
  theirRole = null;
  sendSeq = 0;
  recvSeq = 0;
  myPublicKeyExported = null;
  myQueueId = null;
  theirQueueId = null;
  theirPublicKeyExported = null;
  if (staticInterval) clearTimeout(staticInterval);
  
  socket.disconnect();
  document.body.innerHTML = '';
  window.location.replace("about:blank");
}

let escCount = 0;
let escTimeout = null;
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    escCount++;
    clearTimeout(escTimeout);
    if (escCount >= 3) {
      if (confirm('Are you sure you want to trigger Infinity Snap? All chat state will be lost immediately.')) {
        triggerInfinitySnap();
      } else {
        escCount = 0;
      }
    }
    escTimeout = setTimeout(() => { escCount = 0; }, 1000);
  }
});

btnInfinitySnap.addEventListener('click', () => {
  if (confirm('Are you sure you want to trigger Infinity Snap? All chat state will be lost immediately.')) {
    triggerInfinitySnap();
  }
});

btnObliviate.addEventListener('click', () => {
  if (confirm('Cast Obliviate? This will permanently erase the chat history for both you and your peer, and sever the connection instantly.')) {
    if (writeKey && theirQueueId) {
      const plaintext = JSON.stringify({ type: 'control', action: 'obliviate' });
      encryptMessage(writeKey, plaintext, myRole, sendSeq).then(({iv, ciphertext}) => {
        sendSeq++;
        const payload = JSON.stringify({
          type: 'message',
          iv,
          ciphertext
        });
        socket.emit('push_queue', { queue_id: theirQueueId, payload });
        triggerInfinitySnap();
      }).catch(err => console.error(err));
    } else {
      triggerInfinitySnap();
    }
  }
});

btnElvenCloak.addEventListener('click', () => {
  viewElvenCloak.style.display = 'flex';
});

btnElvenCloakExit.addEventListener('click', () => {
  viewElvenCloak.style.display = 'none';
});

function startPsychoHistoricalStatic() {
  if (staticInterval) clearTimeout(staticInterval);
  
  function sendStatic() {
    if (writeKey && theirQueueId) {
      const plaintext = JSON.stringify({ type: 'control', action: 'static' });
      encryptMessage(writeKey, plaintext, myRole, sendSeq).then(({iv, ciphertext}) => {
        sendSeq++;
        const payload = JSON.stringify({
          type: 'message',
          iv,
          ciphertext
        });
        socket.emit('push_queue', { queue_id: theirQueueId, payload });
      }).catch(err => console.error("Static error:", err));
    }
    staticInterval = setTimeout(sendStatic, Math.random() * 5000 + 2000);
  }
  
  staticInterval = setTimeout(sendStatic, 2000);
}

function addMessageLine(sender, text) {
  const row = document.createElement('div');
  row.className = 'message' + (sender === 'You' ? ' message-own' : '');
  const senderSpan = document.createElement('span');
  senderSpan.className = 'message-sender';
  senderSpan.textContent = sender + ':';
  row.appendChild(senderSpan);
  row.appendChild(document.createTextNode(' ' + text));
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  // Disappearing logic
  const timerVal = parseInt(disappearTimerSelect.value, 10);
  if (timerVal > 0) {
    setTimeout(() => {
      if (row.parentNode) row.parentNode.removeChild(row);
    }, timerVal * 1000);
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
// Initialization & Routing
// -----------------------------------------------------------------
socket.on('connect', async () => {
  if (!window.crypto || !window.crypto.subtle) {
    document.getElementById('warning-banner').innerHTML = 'Security Alert: Web Crypto API requires HTTPS or localhost.';
    document.getElementById('warning-banner').style.display = 'block';
    return;
  }

  if (!myKeys) {
    myKeys = await generateKeyPair();
    myPublicKeyExported = await exportPublicKey(myKeys.publicKey);
  }
  
  socket.emit('create_queue');
});

socket.on('queue_created', ({ queue_id }) => {
  myQueueId = queue_id;
  
  if (theirQueueId && writeKey) {
    // We reconnected, inform peer of our new queue
    addStatusLine('Reconnected. Updating secure channel...');
    const payload = JSON.stringify({
      type: 'queue_update',
      new_queue: myQueueId
    });
    socket.emit('push_queue', { queue_id: theirQueueId, payload });
    return;
  }

  const hashParams = new URLSearchParams(window.location.hash.slice(1));
  if (hashParams.has('q') && hashParams.has('k')) {
    // We are the invitee
    viewSetup.classList.remove('active');
    viewJoin.classList.add('active');
    theirQueueId = hashParams.get('q');
    theirPublicKeyExported = decodeURIComponent(hashParams.get('k'));
  } else {
    // We are the host
    viewSetup.classList.add('active');
    viewJoin.classList.remove('active');
    const inviteUrl = `${window.location.origin}/#q=${myQueueId}&k=${encodeURIComponent(myPublicKeyExported)}`;
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
  navigator.clipboard.writeText(inviteUrl).then(() => {
    alert('Invite link copied!');
    setTimeout(() => {
      navigator.clipboard.writeText('');
      console.log('Clipboard auto-cleared for security.');
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
    const theirKey = await importPublicKey(theirPublicKeyExported);
    
    const sessionKeys = await deriveSessionKeys(myKeys.privateKey, theirKey, myPublicKeyExported, theirPublicKeyExported);
    writeKey = sessionKeys.writeKey;
    readKey = sessionKeys.readKey;
    
    const isAlice = myPublicKeyExported < theirPublicKeyExported;
    myRole = isAlice ? 'A' : 'B';
    theirRole = isAlice ? 'B' : 'A';
    sendSeq = 0;
    recvSeq = 0;
    
    uiSafetyNumber.textContent = await computeSafetyNumber(myPublicKeyExported, theirPublicKeyExported);

    // Send Handshake payload to their queue
    const payload = JSON.stringify({
      type: 'handshake',
      reply_queue: myQueueId,
      public_key: myPublicKeyExported
    });
    socket.emit('push_queue', { queue_id: theirQueueId, payload });
    addStatusLine('Connected to peer. Awaiting their response...');
    history.replaceState(null, null, ' ');
    startPsychoHistoricalStatic();
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
        theirQueueId = data.reply_queue;
        theirPublicKeyExported = data.public_key;
        
        const theirKey = await importPublicKey(theirPublicKeyExported);
        
        const sessionKeys = await deriveSessionKeys(myKeys.privateKey, theirKey, myPublicKeyExported, theirPublicKeyExported);
        writeKey = sessionKeys.writeKey;
        readKey = sessionKeys.readKey;
        
        const isAlice = myPublicKeyExported < theirPublicKeyExported;
        myRole = isAlice ? 'A' : 'B';
        theirRole = isAlice ? 'B' : 'A';
        sendSeq = 0;
        recvSeq = 0;
        
        uiSafetyNumber.textContent = await computeSafetyNumber(myPublicKeyExported, theirPublicKeyExported);
        
        viewSetup.classList.remove('active');
        viewChat.style.display = 'flex';
        addStatusLine('Peer connected securely.');
        startPsychoHistoricalStatic();
      } catch(err) {
        console.error('Handshake verification failed', err);
        addStatusLine('Handshake verification failed!');
      }
      return;
    }

    if (data.type === 'queue_update') {
       theirQueueId = data.new_queue;
       addStatusLine('Peer updated secure channel.');
       return;
    }

    if (data.type === 'message') {
      if (!readKey) return;
      const plaintext = await decryptMessage(readKey, data.iv, data.ciphertext, theirRole, recvSeq);
      
      if (plaintext !== null) {
        recvSeq++;
        try {
          const msgObj = JSON.parse(plaintext);
          if (msgObj.type === 'control') {
            if (msgObj.action === 'static') return;
            if (msgObj.action === 'obliviate') {
              triggerInfinitySnap();
              alert('Peer invoked Obliviate. Chat erased and disconnected.');
              return;
            }
          } else if (msgObj.type === 'text') {
            addMessageLine('Peer', msgObj.content);
          }
        } catch (jsonErr) {
          console.error("Failed to parse decrypted message JSON:", jsonErr);
          addMessageLine('Peer', '[Corrupted Message Envelope]');
        }
      } else {
        addMessageLine('Peer', '[Decryption Failed - Session Desynced]');
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
  const text = inputEl.value; // intentionally not trimmed to allow spaces
  if (!text || !writeKey || !theirQueueId) return;

  const plaintext = JSON.stringify({ type: 'text', content: text });
  const { iv, ciphertext } = await encryptMessage(writeKey, plaintext, myRole, sendSeq);
  sendSeq++;
  const payload = JSON.stringify({
    type: 'message',
    iv,
    ciphertext
  });
  socket.emit('push_queue', { queue_id: theirQueueId, payload });

  addMessageLine('You', text);
  inputEl.value = '';
});

// -----------------------------------------------------------------
// Clipboard Auto-Clearing
// -----------------------------------------------------------------
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
