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
const btnCloseChat = document.getElementById('btn-close-chat');
const btnClearCache = document.getElementById('btn-clear-cache');

// ---------------------------------------------------------------------------
// Covert Calculator Configuration and Functional Implementation
// ---------------------------------------------------------------------------
const CovertCalculatorConfig = {
  // Passcodes that will instantly exit covert mode when typed followed by pressing '='
  exitPasscodes: ['1337', '80085', '7777'],

  // Exit triggers toggle
  enableHeaderDoubleClickExit: true,
  enableEscapeKeyExit: true,

  // Callback when exit is triggered
  defaultTriggerAction: () => {
    if (viewCalculator) viewCalculator.style.display = 'none';
  }
};

let calcState = {
  current: '0',
  previous: '',
  operation: null,
  resetOnNext: false
};

const calcDisplay = document.getElementById('calc-display');
const calcHistory = document.getElementById('calc-display-history');
const calcHeader = document.getElementById('calc-header');
const calcKeypad = document.querySelector('.calc-keypad');
const btnCalcEquals = document.getElementById('btn-calc-equals');

function updateCalcDisplay() {
  if (calcDisplay) calcDisplay.value = calcState.current;
  if (calcHistory) {
    if (calcState.operation) {
      calcHistory.textContent = `${calcState.previous} ${calcState.operation}`;
    } else {
      calcHistory.textContent = '';
    }
  }
}

function handleCalcInput(val) {
  if (!isNaN(val) || val === '.') {
    if (calcState.resetOnNext) {
      calcState.current = val === '.' ? '0.' : val;
      calcState.resetOnNext = false;
    } else {
      if (val === '.') {
        if (!calcState.current.includes('.')) {
          calcState.current += '.';
        }
      } else {
        if (calcState.current === '0') {
          calcState.current = val;
        } else {
          calcState.current += val;
        }
      }
    }
    updateCalcDisplay();
    return;
  }

  switch (val) {
    case 'C':
      calcState.current = '0';
      calcState.previous = '';
      calcState.operation = null;
      calcState.resetOnNext = false;
      break;
    case 'CE':
      calcState.current = '0';
      break;
    case '⌫':
      if (calcState.current.length > 1) {
        calcState.current = calcState.current.slice(0, -1);
      } else {
        calcState.current = '0';
      }
      break;
    case '+/-':
      if (calcState.current !== '0' && calcState.current !== 'Error') {
        calcState.current = (parseFloat(calcState.current) * -1).toString();
      }
      break;
    case '1/x':
      const valNum = parseFloat(calcState.current);
      if (valNum === 0 || isNaN(valNum)) {
        calcState.current = 'Error';
      } else {
        calcState.current = (1 / valNum).toString();
      }
      calcState.resetOnNext = true;
      break;
    case 'x²':
      const valSq = parseFloat(calcState.current);
      calcState.current = isNaN(valSq) ? 'Error' : Math.pow(valSq, 2).toString();
      calcState.resetOnNext = true;
      break;
    case '√x':
      const valSqrt = parseFloat(calcState.current);
      if (isNaN(valSqrt) || valSqrt < 0) {
        calcState.current = 'Error';
      } else {
        calcState.current = Math.sqrt(valSqrt).toString();
      }
      calcState.resetOnNext = true;
      break;
    case '%':
      const valPct = parseFloat(calcState.current);
      calcState.current = isNaN(valPct) ? 'Error' : (valPct / 100).toString();
      calcState.resetOnNext = true;
      break;
    case '+':
    case '−': // Unicode minus
    case '×': // Unicode multiply
    case '÷': // Unicode divide
      if (calcState.operation && !calcState.resetOnNext) {
        evaluateExpression();
      }
      calcState.previous = calcState.current;
      calcState.operation = val;
      calcState.resetOnNext = true;
      break;
  }
  updateCalcDisplay();
}

function evaluateExpression() {
  if (!calcState.operation || calcState.previous === '') return;
  const prev = parseFloat(calcState.previous);
  const curr = parseFloat(calcState.current);
  if (isNaN(prev) || isNaN(curr)) return;

  let result = 0;
  switch (calcState.operation) {
    case '+':
      result = prev + curr;
      break;
    case '−':
      result = prev - curr;
      break;
    case '×':
      result = prev * curr;
      break;
    case '÷':
      if (curr === 0) {
        calcState.current = 'Error';
        calcState.operation = null;
        calcState.previous = '';
        calcState.resetOnNext = true;
        updateCalcDisplay();
        return;
      }
      result = prev / curr;
      break;
  }
  calcState.current = result.toString();
  calcState.operation = null;
  calcState.previous = '';
  calcState.resetOnNext = true;
  updateCalcDisplay();
}

// Stealth Calculator Cover Toggle
if (btnCalculator) {
  btnCalculator.addEventListener('click', () => {
    if (viewCalculator) viewCalculator.style.display = 'flex';
  });
}

// Hook up Equals button click & passcode verification
if (btnCalcEquals) {
  btnCalcEquals.addEventListener('click', () => {
    // Check if passcode is typed
    if (CovertCalculatorConfig.exitPasscodes.includes(calcState.current)) {
      CovertCalculatorConfig.defaultTriggerAction();
      // Reset state for security
      calcState.current = '0';
      calcState.previous = '';
      calcState.operation = null;
      calcState.resetOnNext = false;
      updateCalcDisplay();
      return;
    }
    evaluateExpression();
  });
}

// Keypad event delegation
if (calcKeypad) {
  calcKeypad.addEventListener('click', (e) => {
    const btn = e.target.closest('.calc-btn');
    if (!btn || btn.id === 'btn-calc-equals') return;
    handleCalcInput(btn.textContent.trim());
  });
}

// Double click header to exit covert mode
if (calcHeader && CovertCalculatorConfig.enableHeaderDoubleClickExit) {
  calcHeader.addEventListener('dblclick', () => {
    CovertCalculatorConfig.defaultTriggerAction();
  });
}

// Escape key to exit covert mode
if (CovertCalculatorConfig.enableEscapeKeyExit) {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && viewCalculator && viewCalculator.style.display === 'flex') {
      CovertCalculatorConfig.defaultTriggerAction();
    }
  });
}

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
async function sha256(message) {
  const msgBuffer = new TextEncoder().encode(message);
  const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

let supporterCache = {};

function checkAndRenderSupporterBadge(senderSpan, onion) {
  if (!onion) return;
  onion = onion.toLowerCase();
  if (supporterCache[onion] !== undefined) {
    if (supporterCache[onion]) {
      renderSupporterBadgeIcon(senderSpan);
    }
    return;
  }
  fetch(`/api/profile/supporter_badge/status?onion_address=${onion}`)
    .then(res => res.json())
    .then(data => {
      supporterCache[onion] = data.is_supporter;
      if (data.is_supporter) {
        renderSupporterBadgeIcon(senderSpan);
      }
    });
}

function renderSupporterBadgeIcon(senderSpan) {
  if (senderSpan.querySelector('.supporter-badge')) return;
  const badge = document.createElement('span');
  badge.className = 'supporter-badge';
  badge.textContent = ' 🎗️';
  badge.title = 'Developer Supporter';
  badge.style.color = '#d89b00';
  badge.style.fontWeight = 'bold';
  senderSpan.appendChild(badge);
}

function addMessageLine(sender, text, timestamp = Date.now(), isSystem = false, expiresAt = null, isHistory = false, deliveryState = 'sent', senderOnion = null) {
  let timeLeft = 0;
  if (expiresAt) {
    timeLeft = Math.max(0, Math.round((expiresAt - Date.now()) / 1000));
    if (timeLeft <= 0) {
      return; // Already expired, don't show
    }
  } else if (!isHistory) {
    const timerDuration = parseInt(disappearTimerSelect.value, 10);
    if (timerDuration > 0) {
      timeLeft = timerDuration;
    }
  }

  const msgEl = document.createElement('div');
  msgEl.className = `message ${sender === 'You' || sender === 'me' ? 'message-own' : 'message-other'}`;
  msgEl.dataset.timestamp = timestamp;

  const senderSpan = document.createElement('span');
  senderSpan.className = 'message-sender';
  senderSpan.textContent = sender;

  if (senderOnion) {
    checkAndRenderSupporterBadge(senderSpan, senderOnion);
  } else if (sender === 'You' || sender === 'me') {
    checkAndRenderSupporterBadge(senderSpan, myOnionAddress);
  } else if (activeContact) {
    checkAndRenderSupporterBadge(senderSpan, activeContact.onion_address);
  }

  const contentSpan = document.createElement('span');
  contentSpan.className = 'message-content';
  contentSpan.textContent = text;

  msgEl.appendChild(senderSpan);
  msgEl.appendChild(contentSpan);

  // Render checkmarks for outgoing messages (B4)
  if (!isSystem && (sender === 'You' || sender === 'me')) {
    const statusSpan = document.createElement('span');
    statusSpan.className = 'message-status';
    statusSpan.style.fontSize = '0.75rem';
    statusSpan.style.marginLeft = '6px';
    statusSpan.style.opacity = '0.7';
    if (deliveryState === 'read') {
      statusSpan.textContent = '✓✓';
      statusSpan.style.color = '#0078d4';
    } else if (deliveryState === 'delivered') {
      statusSpan.textContent = '✓✓';
      statusSpan.style.color = '#8a8a8a';
    } else {
      statusSpan.textContent = '✓';
      statusSpan.style.color = '#8a8a8a';
    }
    msgEl.appendChild(statusSpan);

    // Double-click edit (B2)
    contentSpan.style.cursor = 'pointer';
    contentSpan.title = 'Double-click to edit';
    contentSpan.addEventListener('dblclick', () => {
      enterMessageEditMode(msgEl, timestamp, text);
    });

    // Delete message for everyone (B3)
    const deleteBtn = document.createElement('span');
    deleteBtn.className = 'message-delete-btn';
    deleteBtn.innerHTML = ' 🗑️';
    deleteBtn.title = 'Delete message for everyone';
    deleteBtn.style.cursor = 'pointer';
    deleteBtn.style.opacity = '0.5';
    deleteBtn.style.marginLeft = '6px';
    deleteBtn.addEventListener('click', async () => {
      if (confirm('Delete this message for everyone?')) {
        await deleteMessageForEveryone(timestamp);
      }
    });
    msgEl.appendChild(deleteBtn);
  } else if (!isSystem && !isHistory) {
    const reportBtn = document.createElement('span');
    reportBtn.className = 'message-report-btn';
    reportBtn.innerHTML = ' 🚩';
    reportBtn.title = 'Report message';
    reportBtn.style.cursor = 'pointer';
    reportBtn.style.opacity = '0.5';
    reportBtn.style.marginLeft = '6px';
    reportBtn.addEventListener('click', async () => {
      const reason = prompt('Why are you reporting this message as abusive?');
      if (reason) {
        const hash = await sha256(text);
        const res = await fetch('/api/groups/report_message', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message_hash: hash,
            reporter_onion: myOnionAddress,
            reason: reason,
            signature: 'report_attestation_' + Date.now()
          })
        });
        const data = await res.json();
        if (data.success) {
          alert('Message reported successfully. It has been hidden from your view.');
          msgEl.style.display = 'none';
        }
      }
    });
    msgEl.appendChild(reportBtn);
  }

  if (!isSystem) {
    attachReactionPicker(msgEl, timestamp, sender);
  }

  if (timeLeft > 0) {
    const timerSpan = document.createElement('span');
    timerSpan.className = 'message-timer';
    timerSpan.textContent = `⏳ ${timeLeft}s`;
    msgEl.appendChild(timerSpan);

    // Countdown and remove
    let countdown = timeLeft;
    const interval = setInterval(() => {
      countdown--;
      if (countdown <= 0) {
        clearInterval(interval);
        msgEl.classList.add('fading-out');
        setTimeout(() => msgEl.remove(), 500);
      } else {
        timerSpan.textContent = `⏳ ${countdown}s`;
      }
    }, 1000);
  }

  messagesEl.appendChild(msgEl);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function enterMessageEditMode(msgEl, timestamp, originalText) {
  const contentSpan = msgEl.querySelector('.message-content');
  if (!contentSpan || contentSpan.dataset.editing === 'true') return;
  contentSpan.dataset.editing = 'true';

  const input = document.createElement('input');
  input.type = 'text';
  input.value = originalText;
  input.className = 'message-edit-input';
  input.style.width = '80%';
  input.style.padding = '4px';
  input.style.margin = '4px 0';
  input.style.borderRadius = '4px';
  input.style.border = '1px solid #0078d4';
  input.style.background = '#2c2c2c';
  input.style.color = '#fff';

  const oldText = contentSpan.textContent;
  contentSpan.textContent = '';
  contentSpan.appendChild(input);
  input.focus();

  const finishEdit = async (save) => {
    contentSpan.dataset.editing = 'false';
    const newText = input.value.trim();
    if (save && newText && newText !== originalText) {
      const editEnvelope = {
        type: 'x.msg.edit',
        target_timestamp: timestamp,
        content: newText
      };
      const success = await transmitPayload(JSON.stringify(editEnvelope));
      if (success) {
        contentSpan.textContent = newText;
        markMessageAsEdited(msgEl, timestamp);
        if (window.ANONYMUS_MODE === 'p2p' && activeContact) {
          fetch('/api/messages/edit', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              onion_address: activeContact.onion_address,
              timestamp: timestamp,
              message: newText
            })
          });
        }
      } else {
        alert('Failed to transmit message edit.');
        contentSpan.textContent = oldText;
      }
    } else {
      contentSpan.textContent = oldText;
    }
  };

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') finishEdit(true);
    if (e.key === 'Escape') finishEdit(false);
  });

  input.addEventListener('blur', () => {
    setTimeout(() => {
      if (contentSpan.contains(input)) {
        finishEdit(false);
      }
    }, 150);
  });
}

function markMessageAsEdited(msgEl, timestamp) {
  let editedSpan = msgEl.querySelector('.message-edited-label');
  if (!editedSpan) {
    editedSpan = document.createElement('span');
    editedSpan.className = 'message-edited-label';
    editedSpan.textContent = ' (edited)';
    editedSpan.style.fontSize = '0.75rem';
    editedSpan.style.fontStyle = 'italic';
    editedSpan.style.opacity = '0.6';
    editedSpan.style.cursor = 'pointer';
    editedSpan.style.marginLeft = '4px';
    editedSpan.title = 'Click to view edit history';
    editedSpan.addEventListener('click', (e) => {
      e.stopPropagation();
      showEditHistory(timestamp);
    });
    const contentSpan = msgEl.querySelector('.message-content');
    if (contentSpan) {
      contentSpan.appendChild(editedSpan);
    }
  }
}

async function showEditHistory(timestamp) {
  if (!activeContact) return;
  try {
    const res = await fetch(`/api/messages/edits?onion_address=${activeContact.onion_address}&timestamp=${timestamp}`);
    const data = await res.json();
    if (data.edits && data.edits.length > 0) {
      const historyStr = data.edits.map((e, idx) => {
        const d = new Date(e.edit_timestamp);
        return `${idx + 1}. "${e.old_text}" (Edited at ${d.toLocaleTimeString()})`;
      }).join('\n');
      alert(`Edit History for message:\n\n${historyStr}`);
    } else {
      alert('No edit history found.');
    }
  } catch (err) {
    console.error(err);
    alert('Failed to load edit history.');
  }
}

async function deleteMessageForEveryone(timestamp) {
  if (!activeContact) return;
  const deleteEnvelope = {
    type: 'x.msg.delete',
    target_timestamp: timestamp
  };
  const success = await transmitPayload(JSON.stringify(deleteEnvelope));
  if (success) {
    await fetch('/api/messages/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        onion_address: activeContact.onion_address,
        timestamp: timestamp
      })
    });
    const msgEl = document.querySelector(`.message[data-timestamp="${timestamp}"]`);
    if (msgEl) {
      msgEl.classList.add('fading-out');
      setTimeout(() => msgEl.remove(), 500);
    }
  } else {
    alert('Failed to transmit deletion request.');
  }
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
          } else if (msgObj.type === 'x.file.descr') {
            if (!msgObj.timestamp) msgObj.timestamp = Date.now();
            renderFileDownloadMessage('Peer', msgObj);
          } else if (msgObj.type === 'x.msg.live') {
            updateTypingPreview('Peer', msgObj.content);
          } else if (msgObj.type === 'x.msg.reaction') {
            renderReactionInline(msgObj.target_msg_id, msgObj.emoji, 'Peer');
          } else if (msgObj.type === 'webrtc_offer') {
            handleWebRTCOffer(msgObj.sdp);
          } else if (msgObj.type === 'webrtc_answer') {
            handleWebRTCAnswer(msgObj.sdp);
          } else if (msgObj.type === 'webrtc_ice') {
            handleWebRTCIce(msgObj.candidate);
          } else if (msgObj.type === 'webrtc_reject') {
            addStatusLine("Call rejected by peer.");
            stopVideoCall();
          } else if (msgObj.type === 'control') {
            if (msgObj.action === 'timer_set') {
              disappearTimerSelect.value = msgObj.duration_seconds;
              addStatusLine(`Peer updated disappearing messages to ${msgObj.duration_seconds} seconds.`);
              if (relaySession.theirQueueId) {
                await fetch('/api/messages/set_ttl', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ onion_address: relaySession.theirQueueId, ttl_ms: msgObj.duration_seconds * 1000 })
                });
              }
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
let activeProfileId = 'default';
let outgoingBatchBuffer = {};
let batchTimeouts = {};

function getBlockedOnions() {
  try {
    return JSON.parse(localStorage.getItem('blocked_onions') || '[]');
  } catch {
    return [];
  }
}

function blockOnion(onion) {
  const list = getBlockedOnions();
  if (!list.includes(onion.toLowerCase())) {
    list.push(onion.toLowerCase());
    localStorage.setItem('blocked_onions', JSON.stringify(list));
  }
  renderBlockedPeersList();
}

function unblockOnion(onion) {
  let list = getBlockedOnions();
  list = list.filter(item => item !== onion.toLowerCase());
  localStorage.setItem('blocked_onions', JSON.stringify(list));
  renderBlockedPeersList();
}

function renderBlockedPeersList() {
  const container = document.getElementById('blocked-users-list');
  if (!container) return;
  container.innerHTML = '';
  const list = getBlockedOnions();
  if (list.length === 0) {
    container.innerHTML = '<span style="font-size: 0.85rem; color: #605e5c;">No blocked contacts.</span>';
    return;
  }
  list.forEach(onion => {
    const item = document.createElement('div');
    item.style.display = 'flex';
    item.style.justifyContent = 'space-between';
    item.style.alignItems = 'center';
    item.style.fontSize = '0.85rem';
    item.style.padding = '2px 0';

    const span = document.createElement('span');
    span.textContent = onion;
    span.style.fontFamily = 'monospace';
    span.style.wordBreak = 'break-all';

    const unblockBtn = document.createElement('button');
    unblockBtn.className = 'btn';
    unblockBtn.textContent = 'Unblock';
    unblockBtn.style.padding = '2px 6px';
    unblockBtn.style.fontSize = '0.75rem';
    unblockBtn.style.cursor = 'pointer';
    unblockBtn.addEventListener('click', () => {
      unblockOnion(onion);
    });

    item.appendChild(span);
    item.appendChild(unblockBtn);
    container.appendChild(item);
  });
}

async function flushBatch(onion) {
  if (batchTimeouts[onion]) {
    clearTimeout(batchTimeouts[onion]);
    delete batchTimeouts[onion];
  }
  const events = outgoingBatchBuffer[onion] || [];
  delete outgoingBatchBuffer[onion];
  if (events.length === 0) return;
  try {
    const res = await fetch('/api/messages/send_batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        onion_address: onion,
        events: events
      })
    });
    const data = await res.json();
    if (!data.success) {
      console.error("Failed to send batch:", data.error);
    }
  } catch (err) {
    console.error("Error sending batch:", err);
  }
}

let myKeys = null;
let myPublicKeyExported = null;

// Double Ratchet sessions mapped by contact onion address
let drSessions = {};
// Legacy v1 chain keys (for history replay of old messages)
let chainKeys = {};
let sessionIds = {};

async function initMyMasterKeys() {
  if (!myKeys) {
    myKeys = await generateKeyPair();
    myPublicKeyExported = await exportPublicKey(myKeys.publicKey);
  }
}

// Persist the DR session state to the server DB
async function saveDrState(onion) {
  const session = drSessions[onion];
  if (!session) return;
  try {
    const serialized = await serializeSession(session);
    await fetch('/api/contacts/update_dr_state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ onion_address: onion, dr_state: serialized })
    });
  } catch (e) {
    console.warn('Failed to persist DR state:', e);
  }
}

// Initialize v2 Double Ratchet session and legacy v1 chain keys for a contact
async function initSessionKeysForContact(contact) {
  if (!contact.shared_secret || !contact.peer_public_key) return;
  try {
    await initMyMasterKeys();
    const myPub = contact.my_public_key || myPublicKeyExported;
    const isAlice = myPub < contact.peer_public_key;

    // --- v2: Double Ratchet ---
    if (contact.dr_state) {
      // Restore persisted session
      drSessions[contact.onion_address] = await deserializeSession(contact.dr_state);
    } else {
      // Fresh init from shared secret
      const sharedSecretBytes = fromBase64(contact.shared_secret);
      const peerPubBytes = fromBase64(contact.peer_public_key);
      if (isAlice) {
        drSessions[contact.onion_address] = await DoubleRatchetSession.initAlice(sharedSecretBytes, peerPubBytes);
      } else {
        const pkcs8 = await crypto.subtle.exportKey('pkcs8', myKeys.privateKey);
        drSessions[contact.onion_address] = await DoubleRatchetSession.initBob(sharedSecretBytes, pkcs8);
      }
      // Persist new session
      await saveDrState(contact.onion_address);
    }

    // --- v1 legacy chains (kept for history replay) ---
    const sharedSecretBits = fromBase64(contact.shared_secret);
    const hkdfKey = await crypto.subtle.importKey(
      'raw', sharedSecretBits, { name: 'HKDF' }, false, ['deriveKey', 'deriveBits']
    );
    const salt = new Uint8Array(32);
    const clientBits = await crypto.subtle.deriveBits(
      { name: 'HKDF', hash: 'SHA-256', salt, info: new TextEncoder().encode('AnonyMus-Client-To-Server-Key') },
      hkdfKey, 256
    );
    const serverBits = await crypto.subtle.deriveBits(
      { name: 'HKDF', hash: 'SHA-256', salt, info: new TextEncoder().encode('AnonyMus-Server-To-Client-Key') },
      hkdfKey, 256
    );
    chainKeys[contact.onion_address] = {
      sendChainKey: isAlice ? clientBits : serverBits,
      recvChainKey: isAlice ? serverBits : clientBits
    };

    sessionIds[contact.onion_address] = await computeSafetyNumber(myPub, contact.peer_public_key);
  } catch (err) {
    console.error('Failed to initialize session keys for P2P contact:', err);
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
      // Show display_name (incognito pseudonym) if set, else fall back to nickname
      nameSpan.textContent = c.display_name || c.nickname;

      const addrSpan = document.createElement('span');
      addrSpan.className = 'contact-address';
      addrSpan.textContent = c.onion_address.slice(0, 20) + '…';

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
  activeGroup = null;

  // Highlight in sidebar
  document.querySelectorAll('.contacts-list-p2p li').forEach(el => el.classList.remove('active'));
  loadContactsList();

  // Reset Group UI controls
  document.querySelectorAll('.mode-p2p-only').forEach(el => el.style.display = '');
  const groupCtrl = document.getElementById('group-header-controls');
  if (groupCtrl) groupCtrl.style.display = 'none';
  const safetyContainer = document.getElementById('ui-safety-number');
  if (safetyContainer) safetyContainer.parentElement.style.display = '';
  const groupPane = document.getElementById('group-info-pane');
  if (groupPane) groupPane.style.display = 'none';

  // Ensure input fields are enabled when returning to private chat
  const msgInput = document.getElementById('message-input');
  const sendBtn = document.getElementById('send-btn');
  const recordVoiceBtn = document.getElementById('btn-record-voice');
  const recordVideoBtn = document.getElementById('btn-record-video');
  if (msgInput) {
    msgInput.disabled = false;
    msgInput.placeholder = "Type a message...";
  }
  if (sendBtn) sendBtn.disabled = false;
  if (recordVoiceBtn) recordVoiceBtn.disabled = false;
  if (recordVideoBtn) recordVideoBtn.disabled = false;

  // Setup block contact button
  const blockBtn = document.getElementById('btn-block-contact');
  if (blockBtn) {
    blockBtn.style.display = contact.status === 'accepted' ? 'inline-block' : 'none';
    blockBtn.onclick = () => {
      if (confirm(`Are you sure you want to block ${contact.display_name || contact.nickname}?`)) {
        blockOnion(contact.onion_address);
        alert(`${contact.display_name || contact.nickname} has been blocked.`);
        loadContactsList();
      }
    };
  }

  if (contact.status === 'pending_incoming') {
    switchPanel('pending-incoming');
    pendingRequestText.replaceChildren();
    const strongEl = document.createElement('strong');
    strongEl.textContent = contact.nickname;
    pendingRequestText.appendChild(strongEl);
    pendingRequestText.appendChild(document.createTextNode(` (${contact.onion_address}) is requesting a chat connection.`));
  } else if (contact.status === 'pending_outgoing') {
    switchPanel('pending-outgoing');
  } else if (contact.status === 'accepted') {
    switchPanel('chat');
    chattingWithName.textContent = `Chatting with: ${contact.display_name || contact.nickname}`;

    const sessionId = sessionIds[contact.onion_address] || '...';
    uiSafetyNumber.textContent = sessionId;

    if (contact.disappearing_ttl) {
      disappearTimerSelect.value = contact.disappearing_ttl / 1000;
    } else {
      disappearTimerSelect.value = "0";
    }

    const toggle = document.getElementById('receipts-toggle');
    if (toggle) {
      toggle.checked = contact.send_receipts !== 0;
    }

    messagesEl.innerHTML = '';
    loadMessagesHistory(contact.onion_address).then(() => {
      const mode = window.ANONYMUS_MODE || 'relay';
      if (mode === 'p2p' && contact.my_onion_address) {
        const migratedKey = `migrated_${contact.onion_address}`;
        if (!localStorage.getItem(migratedKey)) {
          const payload = JSON.stringify({
            type: 'control',
            action: 'migrate_onion',
            new_onion_address: contact.my_onion_address
          });
          transmitPayload(payload).then(success => {
            if (success) {
              localStorage.setItem(migratedKey, 'true');
              console.log(`Migration initiated for contact ${contact.onion_address}`);
            }
          });
        }
      }
    });
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

    // History replay uses v1 symmetric chain keys (DR sessions are live-only)
    const baseSendChain = chainKeys[onion] && chainKeys[onion].sendChainKey;
    const baseRecvChain = chainKeys[onion] && chainKeys[onion].recvChainKey;

    let currentSendChain = baseSendChain;
    let currentRecvChain = baseRecvChain;
    const contactDisplayName = activeContact.display_name || activeContact.nickname;

    for (const m of msgs) {
      try {
        const payload = JSON.parse(m.message);
        let decrypted = null;

        const sessionId = sessionIds[onion];

        // v2 DR messages are stored with nacl_ciphertext — skip live-session replay for history
        if (payload.nacl_ciphertext) {
          addMessageLine(m.sender === 'me' ? 'You' : contactDisplayName, '[Encrypted — DR v2]', m.timestamp, false, m.expires_at, true);
          continue;
        }

        if (m.sender === 'me') {
          if (!currentSendChain) { tempSendSeq++; continue; }
          const { messageKey, nextChainKey } = await deriveChainKeys(currentSendChain);
          currentSendChain = nextChainKey;
          decrypted = await decryptMessage(messageKey, payload.iv, payload.ciphertext, myRole, tempSendSeq, sessionId);
          tempSendSeq++;
        } else {
          if (!currentRecvChain) { tempRecvSeq++; continue; }
          const { messageKey, nextChainKey } = await deriveChainKeys(currentRecvChain);
          currentRecvChain = nextChainKey;
          decrypted = await decryptMessage(messageKey, payload.iv, payload.ciphertext, theirRole, tempRecvSeq, sessionId);
          tempRecvSeq++;
        }

        if (decrypted) {
          const envelope = JSON.parse(decrypted);
          if (envelope.type === 'text') {
            addMessageLine(m.sender === 'me' ? 'You' : contactDisplayName, envelope.content, m.timestamp, false, m.expires_at, true, m.delivery_state || 'sent');
          } else if (envelope.type === 'x.file.descr') {
            renderFileDownloadMessage(m.sender === 'me' ? 'You' : contactDisplayName, envelope);
          } else if (envelope.type === 'x.msg.reaction') {
            renderReactionInline(envelope.target_msg_id, envelope.emoji, m.sender === 'me' ? 'You' : contactDisplayName);
          } else if (envelope.type === 'x.msg.edit') {
            const targetEl = document.querySelector(`.message[data-timestamp="${envelope.target_timestamp}"]`);
            if (targetEl) {
              const contentSpan = targetEl.querySelector('.message-content');
              if (contentSpan) {
                contentSpan.textContent = envelope.content;
                markMessageAsEdited(targetEl, envelope.target_timestamp);
              }
            }
          } else if (envelope.type === 'x.msg.delete') {
            const targetEl = document.querySelector(`.message[data-timestamp="${envelope.target_timestamp}"]`);
            if (targetEl) {
              targetEl.remove();
            }
          } else if (envelope.type === 'x.msg.receipt') {
            const targetEl = document.querySelector(`.message[data-timestamp="${envelope.target_timestamp}"]`);
            if (targetEl) {
              const statusSpan = targetEl.querySelector('.message-status');
              if (statusSpan) {
                statusSpan.textContent = '✓✓';
                statusSpan.style.color = '#0078d4';
              }
            }
          }
        } else {
          addMessageLine(m.sender === 'me' ? 'You' : contactDisplayName, '[Decryption Failed]', m.timestamp, false, m.expires_at, true);
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

  // X25519 DH shared secret
  const peerPubKey = await importPublicKey(activeContact.peer_public_key);
  const sharedSecretBits = await computeDH(myKeys.privateKey, peerPubKey);
  const sharedSecretB64 = toBase64(sharedSecretBits);

  // Initialize DR session (Bob — we received the handshake)
  const pkcs8 = await crypto.subtle.exportKey('pkcs8', myKeys.privateKey);
  const drSession = await DoubleRatchetSession.initBob(new Uint8Array(sharedSecretBits), pkcs8);
  const drStateStr = await serializeSession(drSession);

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
      // Persist DR state
      await fetch('/api/contacts/update_dr_state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ onion_address: activeContact.onion_address, dr_state: drStateStr })
      });
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
    await initMyMasterKeys();
    const peerPubKey = await importPublicKey(data.peer_public_key);

    // X25519 DH shared secret
    const sharedSecretBits = await computeDH(myKeys.privateKey, peerPubKey);
    const sharedSecretB64 = toBase64(sharedSecretBits);

    // Initialize DR session (Alice — we sent the original handshake)
    const peerPubBytes = fromBase64(data.peer_public_key);
    const drSession = await DoubleRatchetSession.initAlice(new Uint8Array(sharedSecretBits), peerPubBytes);
    const drStateStr = await serializeSession(drSession);

    await fetch('/api/contacts/save_secret', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        onion_address: data.onion_address,
        shared_secret: sharedSecretB64,
        peer_public_key: data.peer_public_key,
        dr_state: drStateStr
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

    if (getBlockedOnions().includes(sender.toLowerCase())) {
      console.log(`Discarding incoming message from blocked peer: ${sender}`);
      return;
    }

    if (activeContact && activeContact.onion_address === sender) {
      const payload = typeof data.payload === 'string' ? JSON.parse(data.payload) : data;
      const isAlice = myPublicKeyExported < activeContact.peer_public_key;
      const theirRole = isAlice ? 'B' : 'A';

      let plaintext = null;

      if (payload.nacl_ciphertext && drSessions[sender]) {
        // v2 Double Ratchet + NaCl box path
        const peerPubKey = await importPublicKey(activeContact.peer_public_key);
        plaintext = await decryptMessageV2(
          drSessions[sender], payload, theirRole, sessionIds[sender],
          myKeys.privateKey, peerPubKey
        );
        if (plaintext !== null) await saveDrState(sender);
      } else {
        // v1 fallback: symmetric chain ratchet
        const chainState = chainKeys[sender];
        if (!chainState || !chainState.recvChainKey) return;
        const { messageKey, nextChainKey } = await deriveChainKeys(chainState.recvChainKey);
        chainState.recvChainKey = nextChainKey;
        plaintext = await decryptMessage(messageKey, data.iv, data.ciphertext, theirRole, seq, sessionIds[sender]);
        if (plaintext !== null) localStorage.setItem(`recvSeq_${sender}`, seq + 1);
      }

      if (plaintext !== null) {

        const envelope = JSON.parse(plaintext);
        const senderDisplayName = activeContact.display_name || activeContact.nickname;
        if (envelope.type === 'text') {
          addMessageLine(senderDisplayName, envelope.content, data.timestamp, false, data.expires_at, false, 'sent');
          if (activeContact && activeContact.send_receipts !== 0) {
            const receiptEnvelope = {
              type: 'x.msg.receipt',
              target_timestamp: data.timestamp,
              state: 'read'
            };
            transmitPayload(JSON.stringify(receiptEnvelope));
          }
        } else if (envelope.type === 'x.grp.invite') {
          if (confirm(`You are invited to join group: ${envelope.name}. Accept invitation?`)) {
            fetch('/api/groups/create', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                name: envelope.name,
                founder_onion: envelope.founder_onion,
                group_id: envelope.group_id,
                is_channel: envelope.is_channel || 0
              })
            }).then(() => {
              const joinEnvelope = {
                type: 'x.grp.join_req',
                group_id: envelope.group_id,
                joiner_onion: myOnionAddress,
                joiner_nickname: myLocalUsername
              };
              transmitPayload(JSON.stringify(joinEnvelope), false, envelope.founder_onion);
              loadGroupsList();
              alert('Invitation accepted! secure connection handshake initiated with group founder.');
            });
          }
        } else if (envelope.type === 'x.grp.join_req') {
          const groupId = envelope.group_id;
          const joinerOnion = envelope.joiner_onion;
          const joinerNickname = envelope.joiner_nickname;

          fetch('/api/groups/add_member', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              group_id: groupId,
              member_onion: joinerOnion,
              nickname: joinerNickname,
              role: 'member'
            })
          }).then(() => {
            fetch(`/api/groups/${groupId}`).then(r => r.json()).then(groupData => {
              const members = groupData.members;
              const memberListEnvelope = {
                type: 'x.grp.member_list',
                group_id: groupId,
                group_name: groupData.group.name,
                founder_onion: groupData.group.founder_onion,
                members: members
              };
              for (const m of members) {
                if (m.member_onion !== myOnionAddress) {
                  transmitPayload(JSON.stringify(memberListEnvelope), false, m.member_onion);
                }
              }
              if (activeGroup && activeGroup.group_id === groupId) {
                loadGroupInfoPane(groupId);
              }
            });
          });
        } else if (envelope.type === 'x.grp.member_list') {
          const groupId = envelope.group_id;
          const name = envelope.group_name;
          const founder = envelope.founder_onion;

          fetch('/api/groups/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              group_id: groupId,
              name: name,
              founder_onion: founder
            })
          }).then(() => {
            envelope.members.forEach(async (m) => {
              await fetch('/api/groups/add_member', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  group_id: groupId,
                  member_onion: m.member_onion,
                  nickname: m.nickname,
                  role: m.role
                })
              });

              const resC = await fetch('/api/contacts');
              const contacts = await resC.json();
              const hasContact = contacts.some(c => c.onion_address === m.member_onion);
              if (m.member_onion !== myOnionAddress && !hasContact) {
                await fetch('/api/contacts/accept_invite', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    invite_onion: m.member_onion,
                    nickname: m.nickname,
                    my_public_key: myPublicKeyExported
                  })
                });
              }
            });
            loadGroupsList();
            if (activeGroup && activeGroup.group_id === groupId) {
              loadGroupInfoPane(groupId);
            }
          });
        } else if (envelope.type === 'x.grp.message') {
          const groupId = envelope.group_id;
          fetch('/api/groups/save_message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              group_id: groupId,
              sender_onion: envelope.sender_onion,
              sender_nickname: envelope.sender_nickname,
              message: envelope.content,
              timestamp: envelope.timestamp
            })
          }).then(() => {
            if (activeGroup && activeGroup.group_id === groupId) {
              const senderDisplayName = envelope.sender_onion === myOnionAddress ? 'You' : envelope.sender_nickname;
              addMessageLine(senderDisplayName, envelope.content, envelope.timestamp);
            }
          });
        } else if (envelope.type === 'x.grp.leave') {
          const groupId = envelope.group_id;
          const leavingOnion = envelope.member_onion;
          fetch('/api/groups/remove_member', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              group_id: groupId,
              member_onion: leavingOnion
            })
          }).then(() => {
            if (activeGroup && activeGroup.group_id === groupId) {
              loadGroupInfoPane(groupId);
            }
          });
        } else if (envelope.type === 'x.grp.vouch') {
          const groupId = envelope.group_id;
          fetch('/api/groups/vouch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              group_id: groupId,
              vouching_member: envelope.vouching_member,
              vouched_member: envelope.vouched_member
            })
          }).then(() => {
            if (activeGroup && activeGroup.group_id === groupId) {
              loadGroupInfoPane(groupId);
            }
          });
        } else if (envelope.type === 'x.file.descr') {
          envelope.timestamp = data.timestamp;
          renderFileDownloadMessage(senderDisplayName, envelope);
        } else if (envelope.type === 'x.msg.live') {
          updateTypingPreview(senderDisplayName, envelope.content);
        } else if (envelope.type === 'x.msg.reaction') {
          renderReactionInline(envelope.target_msg_id, envelope.emoji, senderDisplayName);
        } else if (envelope.type === 'x.msg.edit') {
          const targetEl = document.querySelector(`.message[data-timestamp="${envelope.target_timestamp}"]`);
          if (targetEl) {
            const contentSpan = targetEl.querySelector('.message-content');
            if (contentSpan) {
              contentSpan.textContent = envelope.content;
              markMessageAsEdited(targetEl, envelope.target_timestamp);
            }
          }
          await fetch('/api/messages/edit', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              onion_address: sender,
              timestamp: envelope.target_timestamp,
              message: envelope.content
            })
          });
        } else if (envelope.type === 'x.msg.delete') {
          const targetEl = document.querySelector(`.message[data-timestamp="${envelope.target_timestamp}"]`);
          if (targetEl) {
            targetEl.remove();
          }
          await fetch('/api/messages/delete', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              onion_address: sender,
              timestamp: envelope.target_timestamp
            })
          });
        } else if (envelope.type === 'x.msg.receipt') {
          const targetEl = document.querySelector(`.message[data-timestamp="${envelope.target_timestamp}"]`);
          if (targetEl) {
            const statusSpan = targetEl.querySelector('.message-status');
            if (statusSpan) {
              statusSpan.textContent = '✓✓';
              statusSpan.style.color = '#0078d4';
            }
          }
          await fetch('/api/messages/receipt', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              onion_address: sender,
              timestamp: envelope.target_timestamp,
              state: envelope.state
            })
          });
        } else if (envelope.type === 'webrtc_offer') {
          handleWebRTCOffer(envelope.sdp);
        } else if (envelope.type === 'webrtc_answer') {
          handleWebRTCAnswer(envelope.sdp);
        } else if (envelope.type === 'webrtc_ice') {
          handleWebRTCIce(envelope.candidate);
        } else if (envelope.type === 'webrtc_reject') {
          addStatusLine("Call rejected by peer.");
          stopVideoCall();
        } else if (envelope.type === 'control') {
          if (envelope.action === 'timer_set') {
            disappearTimerSelect.value = envelope.duration_seconds;
            addStatusLine(`Peer updated disappearing messages to ${envelope.duration_seconds} seconds.`);
            await fetch('/api/messages/set_ttl', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ onion_address: sender, ttl_ms: envelope.duration_seconds * 1000 })
            });
          } else if (envelope.action === 'migrate_onion') {
            const oldOnion = sender;
            const newOnion = envelope.new_onion_address;

            // 1. Call local backend to migrate database tables
            const res = await fetch('/api/contacts/migrate', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ old_address: oldOnion, new_address: newOnion })
            });
            const data = await res.json();
            if (data.success) {
              // 2. Swap sequence keys in localStorage
              const sendSeq = localStorage.getItem(`sendSeq_${oldOnion}`);
              const recvSeq = localStorage.getItem(`recvSeq_${oldOnion}`);
              if (sendSeq !== null) localStorage.setItem(`sendSeq_${newOnion}`, sendSeq);
              if (recvSeq !== null) localStorage.setItem(`recvSeq_${newOnion}`, recvSeq);

              // Update in-memory structures
              if (chainKeys[oldOnion]) {
                chainKeys[newOnion] = chainKeys[oldOnion];
                delete chainKeys[oldOnion];
              }
              if (sessionIds[oldOnion]) {
                sessionIds[newOnion] = sessionIds[oldOnion];
                delete sessionIds[oldOnion];
              }

              localStorage.setItem(`migrated_${newOnion}`, 'true');

              // Reply with our own pairwise address if they don't know it yet
              const contactsList = await (await fetch('/api/contacts')).json();
              const match = contactsList.find(c => c.onion_address === newOnion);
              if (match && match.my_onion_address) {
                const replyPayload = JSON.stringify({
                  type: 'control',
                  action: 'migrate_onion',
                  new_onion_address: match.my_onion_address
                });
                await transmitPayload(replyPayload);
              }

              // Reload interface
              await loadContactsList();
              if (activeContact && (activeContact.onion_address === oldOnion || activeContact.onion_address === newOnion)) {
                const updatedMatch = contactsList.find(c => c.onion_address === newOnion);
                if (updatedMatch) selectContact(updatedMatch);
              }
            }
          }
        }
      } else {
        addMessageLine(activeContact.nickname, '[Decryption Failed]', data.timestamp, false, data.expires_at);
      }
    }
  });

  socket.on('contact_status_change', () => {
    loadContactsList();
  });

  socket.on('message_delivery_failed', () => {
    addStatusLine("Message delivery failed. Peer may be offline.");
  });

  socket.on('message_expired', (data) => {
    const msgEl = document.querySelector(`.message[data-timestamp="${data.timestamp}"]`);
    if (msgEl) {
      msgEl.classList.add('fading-out');
      setTimeout(() => msgEl.remove(), 500);
    }
  });

  socket.on('message_deleted', (data) => {
    const msgEl = document.querySelector(`.message[data-timestamp="${data.timestamp}"]`);
    if (msgEl) {
      msgEl.classList.add('fading-out');
      setTimeout(() => msgEl.remove(), 500);
    }
  });
}


// ---------------------------------------------------------------------------
// C. UNIFIED CONTROLLER ENGINE
// ---------------------------------------------------------------------------

// Unified payload sender
async function transmitPayload(plaintext, ephemeral = false, targetOnion = null) {
  const mode = window.ANONYMUS_MODE || 'relay';

  if (mode === 'relay') {
    if (!relaySession.sendChainKey || !relaySession.theirQueueId) return false;
    const { messageKey, nextChainKey } = await deriveChainKeys(relaySession.sendChainKey);
    relaySession.sendChainKey = nextChainKey;

    const { iv, ciphertext } = await encryptMessage(
      messageKey,
      plaintext,
      relaySession.myRole,
      relaySession.sendSeq,
      relaySession.sessionId
    );
    relaySession.sendSeq++;

    const payload = JSON.stringify({ type: 'message', iv, ciphertext, ephemeral });
    socket.emit('push_queue', { queue_id: relaySession.theirQueueId, payload });
    return true;
  } else {
    const onion = targetOnion || (activeContact && activeContact.onion_address);
    if (!onion) return false;

    // Fetch contacts to retrieve key material for targetOnion
    const resContacts = await fetch('/api/contacts');
    const contacts = await resContacts.json();
    const contact = contacts.find(c => c.onion_address === onion);
    if (!contact || contact.status !== 'accepted') return false;

    const isAlice = myPublicKeyExported < contact.peer_public_key;
    const myRole = isAlice ? 'A' : 'B';

    let messagePayload;

    if (drSessions[onion]) {
      // v2: Double Ratchet + NaCl box
      const peerPubKey = await importPublicKey(contact.peer_public_key);
      messagePayload = await encryptMessageV2(
        drSessions[onion], plaintext, myRole, sessionIds[onion],
        myKeys.privateKey, peerPubKey
      );
      await saveDrState(onion);
    } else if (chainKeys[onion]) {
      // v1 fallback
      let sendSeq = parseInt(localStorage.getItem(`sendSeq_${onion}`) || '0', 10);
      const chainState = chainKeys[onion];
      const { messageKey, nextChainKey } = await deriveChainKeys(chainState.sendChainKey);
      chainState.sendChainKey = nextChainKey;
      const { iv, ciphertext } = await encryptMessage(messageKey, plaintext, myRole, sendSeq, sessionIds[onion]);
      messagePayload = { iv, ciphertext, seq: sendSeq };
      localStorage.setItem(`sendSeq_${onion}`, sendSeq + 1);
    } else {
      return false;
    }

    if (!outgoingBatchBuffer[onion]) {
      outgoingBatchBuffer[onion] = [];
    }
    outgoingBatchBuffer[onion].push({
      ephemeral: ephemeral,
      ...messagePayload
    });

    const currentSize = JSON.stringify(outgoingBatchBuffer[onion]).length;
    if (currentSize >= 16384) {
      await flushBatch(onion);
    } else {
      if (!batchTimeouts[onion]) {
        batchTimeouts[onion] = setTimeout(() => {
          flushBatch(onion);
        }, 500);
      }
    }
    return true;
  }
}

// Send chat message
formEl.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = inputEl.value;
  if (!text.trim()) return;

  if (activeGroup) {
    try {
      await sendGroupMessage(activeGroup.group_id, text);
      inputEl.value = '';
      sendTypingDraft('');
    } catch (err) {
      console.error(err);
    }
    return;
  }

  try {
    const success = await transmitPayload(JSON.stringify({ type: 'text', content: text }));
    if (success) {
      addMessageLine('You', text);
      inputEl.value = '';
      sendTypingDraft('');
    }
  } catch (err) {
    console.error(err);
  }
});

// XFTP Chunked Encrypted File Transfer Implementation (10.E.1)
async function uploadFileXFTP(file, progressCallback) {
  const CHUNK_SIZE = 15780;
  const arrayBuffer = await file.arrayBuffer();
  const fileBytes = new Uint8Array(arrayBuffer);
  const masterKey = crypto.getRandomValues(new Uint8Array(32));
  const totalChunks = Math.ceil(fileBytes.length / CHUNK_SIZE);
  const chunkIds = [];
  const mode = window.ANONYMUS_MODE || 'relay';

  for (let i = 0; i < totalChunks; i++) {
    const start = i * CHUNK_SIZE;
    const end = Math.min(start + CHUNK_SIZE, fileBytes.length);
    const chunkSlice = fileBytes.subarray(start, end);
    const info = new TextEncoder().encode("AnonyMus-XFTP-Chunk-" + i);
    const chunkKey = await hkdfDerive256(masterKey, info);
    const encryptedChunk = await encryptChunk(chunkSlice, chunkKey);
    const chunkId = toHex(crypto.getRandomValues(new Uint8Array(16)));

    let uploadUrl = mode === 'p2p' ? `/api/file/upload/${chunkId}` : `/file/upload/${chunkId}`;
    if (mode === 'p2p' && activeContact && activeContact.preferred_file_relay) {
      let relayBase = activeContact.preferred_file_relay.trim();
      if (relayBase.endsWith('/')) {
        relayBase = relayBase.slice(0, -1);
      }
      uploadUrl = `${relayBase}/file/upload/${chunkId}`;
    }

    const res = await fetch(uploadUrl, {
      method: 'POST',
      body: encryptedChunk,
      headers: { 'Content-Type': 'application/octet-stream' }
    });

    if (!res.ok) {
      throw new Error(`Failed to upload chunk ${i + 1}/${totalChunks}`);
    }

    chunkIds.push(chunkId);
    if (progressCallback) {
      progressCallback(i + 1, totalChunks);
    }
  }

  return {
    masterKey: toBase64(masterKey),
    chunks: chunkIds
  };
}

async function downloadFileXFTP(fileName, fileSize, masterKeyB64, chunkIds, senderOnion, relayUrl, progressCallback, triggerDownload = true) {
  const masterKey = fromBase64(masterKeyB64);
  const mode = window.ANONYMUS_MODE || 'relay';
  const chunks = [];

  for (let i = 0; i < chunkIds.length; i++) {
    const chunkId = chunkIds[i];
    let downloadUrl = (mode === 'p2p' && senderOnion)
      ? `/api/file/download/${chunkId}?onion=${senderOnion}`
      : `/file/download/${chunkId}`;

    if (relayUrl) {
      let relayBase = relayUrl.trim();
      if (relayBase.endsWith('/')) {
        relayBase = relayBase.slice(0, -1);
      }
      downloadUrl = `${relayBase}/file/download/${chunkId}`;
    }

    const res = await fetch(downloadUrl);
    if (!res.ok) {
      throw new Error(`Failed to download chunk ${i + 1}/${chunkIds.length}`);
    }

    const encryptedBytes = new Uint8Array(await res.arrayBuffer());
    const info = new TextEncoder().encode("AnonyMus-XFTP-Chunk-" + i);
    const chunkKey = await hkdfDerive256(masterKey, info);
    const decryptedArrayBuffer = await decryptChunk(encryptedBytes, chunkKey);
    chunks.push(new Uint8Array(decryptedArrayBuffer));

    if (progressCallback) {
      progressCallback(i + 1, chunkIds.length);
    }
  }

  const fullBytes = concatenateUint8Arrays(chunks);
  const blob = new Blob([fullBytes]);
  if (triggerDownload) {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = fileName;
    link.click();
  }
  return blob;
}

async function handleFileSelect(e) {
  const file = e.target.files[0];
  if (!file) return;

  if (file.size > 100 * 1024 * 1024) {
    alert("File is too large. Maximum supported size is 100MB.");
    return;
  }

  const mode = window.ANONYMUS_MODE || 'relay';
  const fileInput = document.getElementById('file-input');

  addStatusLine(`Uploading and encrypting "${file.name}" (0%)...`);

  try {
    const result = await uploadFileXFTP(file, (current, total) => {
      const pct = Math.round((current / total) * 100);
      addStatusLine(`Uploading and encrypting "${file.name}" (${pct}%)...`);
    });

    const envelope = {
      type: 'x.file.descr',
      file_name: file.name,
      file_size: file.size,
      master_key: result.masterKey,
      chunks: result.chunks,
      sender_onion: (mode === 'p2p' && activeContact) ? activeContact.my_onion_address : null,
      relay: (mode === 'p2p' && activeContact && activeContact.preferred_file_relay) ? activeContact.preferred_file_relay : null
    };

    const success = await transmitPayload(JSON.stringify(envelope));
    if (success) {
      addStatusLine(`File "${file.name}" uploaded successfully.`);
      renderFileDownloadMessage('You', envelope);
    } else {
      addStatusLine("Failed to transmit file descriptor to peer.");
    }
    if (fileInput) fileInput.value = '';
  } catch (err) {
    console.error(err);
    addStatusLine(`File upload failed: ${err.message}`);
  }
}

function concatenateUint8Arrays(arrays) {
  let totalLength = 0;
  for (const arr of arrays) {
    totalLength += arr.length;
  }
  const result = new Uint8Array(totalLength);
  let offset = 0;
  for (const arr of arrays) {
    result.set(arr, offset);
    offset += arr.length;
  }
  return result;
}

function renderFileDownloadMessage(sender, envelope) {
  const { file_name, file_size, master_key, chunks, sender_onion, relay } = envelope;
  const displaySize = (file_size / (1024 * 1024)).toFixed(2) + " MB";
  const isAudio = file_name.endsWith('.webm') && file_name.startsWith('voice_note');
  const isVideo = file_name.endsWith('.webm') && file_name.startsWith('video_note');

  const msgEl = document.createElement('div');
  msgEl.className = `message ${sender === 'You' || sender === 'me' ? 'message-own' : 'message-other'}`;

  const senderSpan = document.createElement('span');
  senderSpan.className = 'message-sender';
  senderSpan.textContent = sender;

  const bodyDiv = document.createElement('div');
  bodyDiv.style.marginTop = "4px";

  if (isAudio) {
    const audioContainer = document.createElement('div');
    audioContainer.innerHTML = `🎙️ <strong>Voice Note</strong> (${displaySize})`;
    audioContainer.style.marginBottom = "6px";
    bodyDiv.appendChild(audioContainer);

    const playBtn = document.createElement('button');
    playBtn.textContent = "▶️ Listen";
    playBtn.className = "btn";
    playBtn.style.padding = "4px 8px";
    playBtn.style.fontSize = "0.85rem";

    playBtn.addEventListener('click', async () => {
      playBtn.disabled = true;
      playBtn.textContent = "Loading...";
      try {
        const blob = await downloadFileXFTP(file_name, file_size, master_key, chunks, sender_onion, relay, null, false);
        const audioUrl = URL.createObjectURL(blob);

        const audioPlayer = document.createElement('audio');
        audioPlayer.src = audioUrl;
        audioPlayer.controls = true;
        audioPlayer.autoplay = true;
        audioPlayer.style.display = "block";
        audioPlayer.style.marginTop = "6px";

        audioContainer.appendChild(audioPlayer);
        playBtn.remove();
      } catch (err) {
        console.error(err);
        playBtn.disabled = false;
        playBtn.textContent = "❌ Failed. Retry?";
      }
    });
    bodyDiv.appendChild(playBtn);
  } else if (isVideo) {
    const videoContainer = document.createElement('div');
    videoContainer.innerHTML = `📹 <strong>Video Note</strong> (${displaySize})`;
    videoContainer.style.marginBottom = "6px";
    bodyDiv.appendChild(videoContainer);

    const playBtn = document.createElement('button');
    playBtn.textContent = "▶️ Play Video";
    playBtn.className = "btn";
    playBtn.style.padding = "4px 8px";
    playBtn.style.fontSize = "0.85rem";

    playBtn.addEventListener('click', async () => {
      playBtn.disabled = true;
      playBtn.textContent = "Loading...";
      try {
        const blob = await downloadFileXFTP(file_name, file_size, master_key, chunks, sender_onion, relay, null, false);
        const videoUrl = URL.createObjectURL(blob);

        const videoPlayer = document.createElement('video');
        videoPlayer.src = videoUrl;
        videoPlayer.controls = true;
        videoPlayer.autoplay = true;
        videoPlayer.style.display = "block";
        videoPlayer.style.marginTop = "6px";
        videoPlayer.style.maxWidth = "280px";
        videoPlayer.style.borderRadius = "8px";

        videoContainer.appendChild(videoPlayer);
        playBtn.remove();
      } catch (err) {
        console.error(err);
        playBtn.disabled = false;
        playBtn.textContent = "❌ Failed. Retry?";
      }
    });
    bodyDiv.appendChild(playBtn);
  } else {
    const infoSpan = document.createElement('div');
    infoSpan.innerHTML = `📄 <strong>${escapeHTML(file_name)}</strong> (${displaySize})`;
    infoSpan.style.marginBottom = "6px";
    bodyDiv.appendChild(infoSpan);

    if (sender !== 'You' && sender !== 'me') {
      const btn = document.createElement('button');
      btn.textContent = `📥 Download (${displaySize})`;
      btn.style.padding = "4px 8px";
      btn.style.borderRadius = "4px";
      btn.style.border = "none";
      btn.style.background = "#0078d4";
      btn.style.color = "#fff";
      btn.style.cursor = "pointer";
      btn.style.fontSize = "0.85rem";

      btn.addEventListener('click', async () => {
        btn.disabled = true;
        btn.style.background = "#8a8a8a";
        try {
          await downloadFileXFTP(file_name, file_size, master_key, chunks, sender_onion, relay, (current, total) => {
            const pct = Math.round((current / total) * 100);
            btn.textContent = `Downloading ${pct}%...`;
          });
          btn.textContent = "✅ Downloaded";
        } catch (err) {
          console.error(err);
          btn.disabled = false;
          btn.style.background = "#e81123";
          btn.textContent = "❌ Failed. Retry?";
        }
      });
      bodyDiv.appendChild(btn);
    } else {
      const statusSpan = document.createElement('span');
      statusSpan.textContent = "Sent file descriptor";
      statusSpan.style.fontSize = "0.8rem";
      statusSpan.style.color = "#8a8a8a";
      bodyDiv.appendChild(statusSpan);
    }
  }

  msgEl.appendChild(senderSpan);
  msgEl.appendChild(bodyDiv);
  messagesEl.appendChild(msgEl);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function escapeHTML(str) {
  return str.replace(/[&<>'"]/g,
    tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag)
  );
}

// Settings modal changes timer negotiate
disappearTimerSelect.addEventListener('change', async () => {
  const val = parseInt(disappearTimerSelect.value, 10);
  const mode = window.ANONYMUS_MODE || 'relay';
  const onion = mode === 'p2p' && activeContact ? activeContact.onion_address : (relaySession.theirQueueId || null);

  if (onion) {
    await fetch('/api/messages/set_ttl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ onion_address: onion, ttl_ms: val * 1000 })
    });
  }

  const controlPayload = JSON.stringify({ type: 'control', action: 'timer_set', duration_seconds: val });
  await transmitPayload(controlPayload);
});

// App Session Reset / Logout helper
function resetClientSession(hard = false) {
  localStorage.clear();
  socket.disconnect();
  document.body.innerHTML = '';
  window.location.replace(hard ? "about:blank" : "/");
}

// Video / Voice WebRTC Calling Engine
let peerConnection = null;
let localStream = null;

async function startVideoCall() {
  try {
    addStatusLine("Requesting camera/microphone access...");
    localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
    document.getElementById('local-video').srcObject = localStream;
    document.getElementById('video-grid').style.display = 'flex';
    document.getElementById('btn-call').style.display = 'none';
    document.getElementById('btn-hangup').style.display = 'block';

    const config = {
      iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'turn:anonymus.chat:3478', username: 'anonymus', credential: 'turnpassword' }
      ]
    };

    peerConnection = new RTCPeerConnection({
      ...config,
      encodedInsertableStreams: true // Enable Insertable Streams API
    });

    localStream.getTracks().forEach(track => {
      const sender = peerConnection.addTrack(track, localStream);
      setupSenderTransform(sender);
    });

    peerConnection.ontrack = (event) => {
      document.getElementById('remote-video').srcObject = event.streams[0];
      setupReceiverTransform(event.receiver);
    };

    peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        transmitPayload(JSON.stringify({
          type: 'webrtc_ice',
          candidate: event.candidate
        }));
      }
    };

    const offer = await peerConnection.createOffer();
    await peerConnection.setLocalDescription(offer);

    transmitPayload(JSON.stringify({
      type: 'webrtc_offer',
      sdp: offer.sdp
    }));

    addStatusLine("Call initiated. Awaiting response...");
  } catch (err) {
    console.error("Error starting video call:", err);
    addStatusLine("Failed to start video call.");
    stopVideoCall();
  }
}

async function handleWebRTCOffer(offerSdp) {
  try {
    if (peerConnection) return;

    const accept = confirm("Incoming voice/video call request. Accept?");
    if (!accept) {
      transmitPayload(JSON.stringify({ type: 'webrtc_reject' }));
      return;
    }

    addStatusLine("Answering video call...");
    localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
    document.getElementById('local-video').srcObject = localStream;
    document.getElementById('video-grid').style.display = 'flex';
    document.getElementById('btn-call').style.display = 'none';
    document.getElementById('btn-hangup').style.display = 'block';

    const config = {
      iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'turn:anonymus.chat:3478', username: 'anonymus', credential: 'turnpassword' }
      ]
    };

    peerConnection = new RTCPeerConnection({
      ...config,
      encodedInsertableStreams: true
    });

    localStream.getTracks().forEach(track => {
      const sender = peerConnection.addTrack(track, localStream);
      setupSenderTransform(sender);
    });

    peerConnection.ontrack = (event) => {
      document.getElementById('remote-video').srcObject = event.streams[0];
      setupReceiverTransform(event.receiver);
    };

    peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        transmitPayload(JSON.stringify({
          type: 'webrtc_ice',
          candidate: event.candidate
        }));
      }
    };

    await peerConnection.setRemoteDescription(new RTCSessionDescription({ type: 'offer', sdp: offerSdp }));
    const answer = await peerConnection.createAnswer();
    await peerConnection.setLocalDescription(answer);

    transmitPayload(JSON.stringify({
      type: 'webrtc_answer',
      sdp: answer.sdp
    }));

    addStatusLine("Call established.");
  } catch (err) {
    console.error("Error handling offer:", err);
    addStatusLine("Failed to answer incoming call.");
    stopVideoCall();
  }
}

async function handleWebRTCAnswer(answerSdp) {
  if (peerConnection) {
    await peerConnection.setRemoteDescription(new RTCSessionDescription({ type: 'answer', sdp: answerSdp }));
    addStatusLine("Call connected.");
  }
}

async function handleWebRTCIce(candidate) {
  if (peerConnection && candidate) {
    try {
      await peerConnection.addIceCandidate(new RTCIceCandidate(candidate));
    } catch (e) {
      console.error("Error adding ICE candidate:", e);
    }
  }
}

function stopVideoCall() {
  if (peerConnection) {
    peerConnection.close();
    peerConnection = null;
  }
  if (localStream) {
    localStream.getTracks().forEach(track => track.stop());
    localStream = null;
  }

  document.getElementById('local-video').srcObject = null;
  document.getElementById('remote-video').srcObject = null;
  document.getElementById('video-grid').style.display = 'none';
  document.getElementById('btn-call').style.display = 'block';
  document.getElementById('btn-hangup').style.display = 'none';
  addStatusLine("Call disconnected.");
}

function setupSenderTransform(sender) {
  if (!sender.createEncodedStreams) return;
  const senderStreams = sender.createEncodedStreams();
  const readableStream = senderStreams.readable;
  const writableStream = senderStreams.writable;

  const key = getCallEncryptionKey();
  const transformStream = new TransformStream({
    transform(encodedFrame, controller) {
      const data = new Uint8Array(encodedFrame.data);
      const transformed = new Uint8Array(data.length);
      for (let i = 0; i < data.length; i++) {
        transformed[i] = data[i] ^ key[i % key.length];
      }
      encodedFrame.data = transformed.buffer;
      controller.enqueue(encodedFrame);
    }
  });
  readableStream.pipeThrough(transformStream).pipeTo(writableStream);
}

function setupReceiverTransform(receiver) {
  if (!receiver.createEncodedStreams) return;
  const receiverStreams = receiver.createEncodedStreams();
  const readableStream = receiverStreams.readable;
  const writableStream = receiverStreams.writable;

  const key = getCallEncryptionKey();
  const transformStream = new TransformStream({
    transform(encodedFrame, controller) {
      const data = new Uint8Array(encodedFrame.data);
      const transformed = new Uint8Array(data.length);
      for (let i = 0; i < data.length; i++) {
        transformed[i] = data[i] ^ key[i % key.length];
      }
      encodedFrame.data = transformed.buffer;
      controller.enqueue(encodedFrame);
    }
  });
  readableStream.pipeThrough(transformStream).pipeTo(writableStream);
}

function getCallEncryptionKey() {
  const sessionId = relaySession.sessionId || sessionIds[activeContact?.onion_address] || "default_safety_number";
  const encoder = new TextEncoder();
  return encoder.encode(sessionId);
}

async function handleSystemLogout() {
  resetClientSession(false);
}

// App startup initializer
async function initApp() {
  const mode = window.ANONYMUS_MODE || 'relay';

  // Load blocked peers on settings display and setup verify badge button click listener
  const btnSettings = document.getElementById('btn-settings');
  if (btnSettings) {
    btnSettings.addEventListener('click', () => {
      renderBlockedPeersList();
    });
  }

  const btnVerifyBadge = document.getElementById('btn-verify-badge');
  if (btnVerifyBadge) {
    btnVerifyBadge.addEventListener('click', async () => {
      const sig = document.getElementById('supporter-badge-sig').value.trim();
      if (!sig) return;

      const statusMsg = document.getElementById('badge-status-message');
      statusMsg.style.display = 'block';
      statusMsg.style.color = '#8a8886';
      statusMsg.textContent = 'Verifying signature...';

      try {
        const res = await fetch('/api/profile/supporter_badge', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            onion_address: myOnionAddress,
            signature: sig
          })
        });
        const data = await res.json();
        if (data.success) {
          statusMsg.style.color = '#107c41';
          statusMsg.textContent = 'Supporter Badge Activated Successfully! ⭐';
          supporterCache[myOnionAddress.toLowerCase()] = true;
          // Refresh own messages
          document.querySelectorAll('.message-own .message-sender').forEach(el => {
            renderSupporterBadgeIcon(el);
          });
        } else {
          statusMsg.style.color = '#d83b01';
          statusMsg.textContent = data.error || 'Failed to activate badge.';
        }
      } catch (err) {
        statusMsg.style.color = '#d83b01';
        statusMsg.textContent = 'Network error verifying badge.';
      }
    });
  }

  // Register unified logout triggers
  const btnLogout = document.getElementById('btn-logout');
  if (btnLogout) btnLogout.addEventListener('click', handleSystemLogout);

  // Register WebRTC call triggers
  const btnCall = document.getElementById('btn-call');
  const btnHangup = document.getElementById('btn-hangup');
  if (btnCall) btnCall.addEventListener('click', startVideoCall);
  if (btnHangup) btnHangup.addEventListener('click', () => {
    transmitPayload(JSON.stringify({ type: 'webrtc_reject' }));
    stopVideoCall();
  });

  // File attachment listeners
  const attachBtn = document.getElementById('attach-btn');
  const fileInput = document.getElementById('file-input');
  if (attachBtn && fileInput) {
    attachBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', handleFileSelect);
  }

  // Close chat or clear cache triggers
  if (btnCloseChat) {
    btnCloseChat.addEventListener('click', () => {
      if (confirm("Reset active session and erase all state?")) {
        if (mode === 'p2p') {
          fetch('/api/reset-data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm: 'RESET' })
          }).then(() => resetClientSession(false));
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
          fetch('/api/reset-data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm: 'RESET' })
          }).then(() => {
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

    const relayRes = await fetch('/api/settings/preferred_relay');
    const relayData = await relayRes.json();
    const relayInput = document.getElementById('preferred-relay-input');
    if (relayInput && relayData.preferred_file_relay) {
      relayInput.value = relayData.preferred_file_relay;
    }

    const btnSaveRelay = document.getElementById('btn-save-relay');
    if (btnSaveRelay && relayInput) {
      btnSaveRelay.addEventListener('click', async () => {
        const val = relayInput.value.trim();
        const res = await fetch('/api/settings/preferred_relay', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ preferred_file_relay: val })
        });
        const data = await res.json();
        if (data.success) {
          alert('Preferred file relay saved!');
        } else {
          alert('Error: ' + data.error);
        }
      });
    }

    const receiptsToggle = document.getElementById('receipts-toggle');
    if (receiptsToggle) {
      receiptsToggle.addEventListener('change', async () => {
        if (!activeContact) return;
        const checked = receiptsToggle.checked;
        const res = await fetch('/api/contacts/update_receipts', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            onion_address: activeContact.onion_address,
            send_receipts: checked
          })
        });
        const data = await res.json();
        if (data.success) {
          activeContact.send_receipts = checked ? 1 : 0;
        } else {
          alert('Failed to save receipt settings.');
          receiptsToggle.checked = !checked;
        }
      });
    }

    await initMyMasterKeys();
    await loadContactsList();
    await loadGroupsList();
    await loadProfilesList();

    const profileSelect = document.getElementById('profile-select');
    if (profileSelect) profileSelect.addEventListener('change', handleProfileChange);

    const btnCreateProfileModal = document.getElementById('btn-create-profile-modal');
    if (btnCreateProfileModal) {
      btnCreateProfileModal.addEventListener('click', () => {
        document.getElementById('create-profile-modal').style.display = 'flex';
      });
    }
    const btnCancelCreateProfile = document.getElementById('btn-cancel-create-profile');
    if (btnCancelCreateProfile) {
      btnCancelCreateProfile.addEventListener('click', () => {
        document.getElementById('create-profile-modal').style.display = 'none';
      });
    }
    const btnSubmitCreateProfile = document.getElementById('btn-submit-create-profile');
    if (btnSubmitCreateProfile) btnSubmitCreateProfile.addEventListener('click', submitCreateProfile);

    const btnUnlockProfileModal = document.getElementById('btn-unlock-profile-modal');
    if (btnUnlockProfileModal) {
      btnUnlockProfileModal.addEventListener('click', () => {
        document.getElementById('unlock-profile-modal').style.display = 'flex';
      });
    }
    const btnCancelUnlockProfile = document.getElementById('btn-cancel-unlock-profile');
    if (btnCancelUnlockProfile) {
      btnCancelUnlockProfile.addEventListener('click', () => {
        document.getElementById('unlock-profile-modal').style.display = 'none';
      });
    }
    const btnSubmitUnlockProfile = document.getElementById('btn-submit-unlock-profile');
    if (btnSubmitUnlockProfile) btnSubmitUnlockProfile.addEventListener('click', submitUnlockProfile);

    const profileHiddenCheckbox = document.getElementById('profile-hidden-checkbox');
    if (profileHiddenCheckbox) {
      profileHiddenCheckbox.addEventListener('change', (e) => {
        const section = document.getElementById('profile-passphrase-section');
        section.style.display = e.target.checked ? 'block' : 'none';
      });
    }

    const btnRecordVoice = document.getElementById('btn-record-voice');
    if (btnRecordVoice) btnRecordVoice.addEventListener('click', initVoiceRecording);
    const btnCancelRecording = document.getElementById('btn-cancel-recording');
    if (btnCancelRecording) btnCancelRecording.addEventListener('click', cancelVoiceRecording);
    const btnStopRecording = document.getElementById('btn-stop-recording');
    if (btnStopRecording) btnStopRecording.addEventListener('click', stopVoiceRecording);

    const btnRecordVideo = document.getElementById('btn-record-video');
    if (btnRecordVideo) btnRecordVideo.addEventListener('click', initVideoRecording);
    const btnCancelVideoRecord = document.getElementById('btn-cancel-video-record');
    if (btnCancelVideoRecord) btnCancelVideoRecord.addEventListener('click', cancelVideoRecording);
    const btnStartVideoRecord = document.getElementById('btn-start-video-record');
    if (btnStartVideoRecord) btnStartVideoRecord.addEventListener('click', startVideoRecording);
    const btnStopVideoRecord = document.getElementById('btn-stop-video-record');
    if (btnStopVideoRecord) btnStopVideoRecord.addEventListener('click', stopVideoRecording);

    const btnShowCreateGroup = document.getElementById('btn-show-create-group');
    if (btnShowCreateGroup) btnShowCreateGroup.addEventListener('click', openCreateGroupModal);
    const btnCancelCreateGroup = document.getElementById('btn-cancel-create-group');
    if (btnCancelCreateGroup) btnCancelCreateGroup.addEventListener('click', () => {
      document.getElementById('create-group-modal').style.display = 'none';
    });
    const btnSubmitCreateGroup = document.getElementById('btn-submit-create-group');
    if (btnSubmitCreateGroup) btnSubmitCreateGroup.addEventListener('click', submitCreateGroup);

    const btnGroupInfo = document.getElementById('btn-group-info');
    if (btnGroupInfo) {
      btnGroupInfo.addEventListener('click', () => {
        const pane = document.getElementById('group-info-pane');
        if (pane.style.display === 'none') {
          pane.style.display = 'block';
          loadGroupInfoPane(activeGroup.group_id);
        } else {
          pane.style.display = 'none';
        }
      });
    }

    const btnCopyGroupInvite = document.getElementById('btn-copy-group-invite');
    if (btnCopyGroupInvite) {
      btnCopyGroupInvite.addEventListener('click', () => {
        if (activeGroup) copyGroupInviteLink(activeGroup.group_id);
      });
    }

    const btnLeaveGroup = document.getElementById('btn-leave-group');
    if (btnLeaveGroup) {
      btnLeaveGroup.addEventListener('click', async () => {
        if (!activeGroup || !confirm("Are you sure you want to leave this group?")) return;
        const groupId = activeGroup.group_id;
        const envelope = {
          type: 'x.grp.leave',
          group_id: groupId,
          member_onion: myOnionAddress
        };
        const res = await fetch(`/api/groups/${groupId}`);
        const groupData = await res.json();
        for (const m of groupData.members) {
          if (m.member_onion !== myOnionAddress) {
            await transmitPayload(JSON.stringify(envelope), false, m.member_onion);
          }
        }

        await fetch('/api/groups/remove_member', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            group_id: groupId,
            member_onion: myOnionAddress
          })
        });

        activeGroup = null;
        switchPanel('welcome');
        await loadGroupsList();
      });
    }

    socket.on('group_message_saved', (data) => {
      if (getBlockedOnions().includes(data.sender_onion.toLowerCase())) {
        console.log(`Discarding group message from blocked peer: ${data.sender_onion}`);
        return;
      }
      if (activeGroup && activeGroup.group_id === data.group_id && data.sender_onion !== myOnionAddress) {
        addMessageLine(data.sender_nickname, data.message, data.timestamp, false, null, false, 'sent', data.sender_onion);
      }
    });

    socket.on('group_vouch_added', (data) => {
      if (activeGroup && activeGroup.group_id === data.group_id) {
        loadGroupInfoPane(data.group_id);
      }
    });

    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('group_invite') === 'true') {
      const token = urlParams.get('token');
      const founderOnion = urlParams.get('onion');
      const groupId = urlParams.get('group_id');
      const groupName = urlParams.get('name');

      switchPanel('join');
      const acceptBtn = document.getElementById('btn-accept-invite');
      if (acceptBtn) {
        acceptBtn.textContent = `Accept & Join Group: ${groupName}`;
        acceptBtn.onclick = async () => {
          const resContacts = await fetch('/api/contacts');
          const contacts = await resContacts.json();
          const hasContact = contacts.some(c => c.onion_address === founderOnion);
          if (!hasContact) {
            await fetch('/api/contacts/accept_invite', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                invite_onion: founderOnion,
                nickname: `Founder-${groupName.slice(0,6)}`,
                my_public_key: myPublicKeyExported
              })
            });
          }

          const joinEnvelope = {
            type: 'x.grp.join_req',
            group_id: groupId,
            token: token,
            joiner_onion: myOnionAddress,
            joiner_nickname: myLocalUsername
          };

          alert('Establishing connection and sending join request to founder...');
          let sent = false;
          for (let i = 0; i < 5; i++) {
            sent = await transmitPayload(JSON.stringify(joinEnvelope), false, founderOnion);
            if (sent) break;
            await new Promise(r => setTimeout(r, 2000));
          }
          if (sent) {
            alert('Join request sent successfully! Waiting for founder confirmation.');
            window.history.replaceState({}, document.title, "/");
            loadGroupsList();
          } else {
            alert('Could not connect to founder. Please ensure they are online and try again.');
          }
        };
      }
    }

    const btnShowPairing = document.getElementById('btn-show-pairing');
    if (btnShowPairing) btnShowPairing.addEventListener('click', initDevicePairing);

    const btnPushPairing = document.getElementById('btn-push-pairing');
    if (btnPushPairing) {
      btnPushPairing.addEventListener('click', () => {
        document.getElementById('push-sync-modal').style.display = 'flex';
      });
    }

    const btnCancelPushSync = document.getElementById('btn-cancel-push-sync');
    if (btnCancelPushSync) {
      btnCancelPushSync.addEventListener('click', () => {
        document.getElementById('push-sync-modal').style.display = 'none';
      });
    }

    const btnSubmitPushSync = document.getElementById('btn-submit-push-sync');
    if (btnSubmitPushSync) btnSubmitPushSync.addEventListener('click', submitPushSync);
  }
}

// Helper functions for Reactions and Live Messages (10.D.2, 10.D.3)
function renderReactionInline(targetTimestamp, emoji, senderName) {
  const msgEl = document.querySelector(`.message[data-timestamp="${targetTimestamp}"]`);
  if (!msgEl) return;

  let reactionsContainer = msgEl.querySelector('.message-reactions');
  if (!reactionsContainer) {
    reactionsContainer = document.createElement('div');
    reactionsContainer.className = 'message-reactions';
    reactionsContainer.style.display = 'flex';
    reactionsContainer.style.gap = '4px';
    reactionsContainer.style.marginTop = '4px';
    reactionsContainer.style.fontSize = '0.85rem';
    msgEl.appendChild(reactionsContainer);
  }

  const existingKey = `${senderName}-${emoji}`;
  const existingBadge = reactionsContainer.querySelector(`[data-key="${existingKey}"]`);
  if (existingBadge) return;

  const badge = document.createElement('span');
  badge.className = 'reaction-badge';
  badge.dataset.key = existingKey;
  badge.textContent = emoji;
  badge.style.background = 'rgba(255, 255, 255, 0.15)';
  badge.style.padding = '2px 6px';
  badge.style.borderRadius = '10px';
  badge.style.border = '1px solid rgba(255, 255, 255, 0.2)';
  badge.style.cursor = 'pointer';
  badge.style.transition = 'all 0.2s';

  badge.addEventListener('mouseenter', () => {
    badge.style.background = 'rgba(255, 255, 255, 0.3)';
  });
  badge.addEventListener('mouseleave', () => {
    badge.style.background = 'rgba(255, 255, 255, 0.15)';
  });

  reactionsContainer.appendChild(badge);
}

function attachReactionPicker(msgEl, timestamp, sender) {
  msgEl.style.position = 'relative';

  const reactBtn = document.createElement('button');
  reactBtn.className = 'message-react-btn';
  reactBtn.textContent = '➕';
  reactBtn.style.position = 'absolute';
  reactBtn.style.right = (sender === 'You' || sender === 'me') ? 'auto' : '-30px';
  reactBtn.style.left = (sender === 'You' || sender === 'me') ? '-30px' : 'auto';
  reactBtn.style.top = '50%';
  reactBtn.style.transform = 'translateY(-50%)';
  reactBtn.style.background = 'none';
  reactBtn.style.border = 'none';
  reactBtn.style.cursor = 'pointer';
  reactBtn.style.fontSize = '0.9rem';
  reactBtn.style.opacity = '0';
  reactBtn.style.transition = 'opacity 0.2s';
  reactBtn.title = 'React to message';

  msgEl.addEventListener('mouseenter', () => {
    reactBtn.style.opacity = '1';
  });
  msgEl.addEventListener('mouseleave', () => {
    reactBtn.style.opacity = '0';
  });

  reactBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    document.querySelectorAll('.reaction-picker-popover').forEach(el => el.remove());

    const picker = document.createElement('div');
    picker.className = 'reaction-picker-popover';
    picker.style.position = 'absolute';
    picker.style.top = '-35px';
    picker.style.left = (sender === 'You' || sender === 'me') ? '0' : 'auto';
    picker.style.right = (sender === 'You' || sender === 'me') ? 'auto' : '0';
    picker.style.background = 'rgba(30, 30, 30, 0.95)';
    picker.style.backdropFilter = 'blur(10px)';
    picker.style.border = '1px solid rgba(255, 255, 255, 0.2)';
    picker.style.borderRadius = '20px';
    picker.style.padding = '4px 8px';
    picker.style.display = 'flex';
    picker.style.gap = '8px';
    picker.style.zIndex = '1000';
    picker.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';

    const emojis = ['👍', '❤️', '😂', '😮', '😢', '🙏'];
    emojis.forEach(emoji => {
      const emojiSpan = document.createElement('span');
      emojiSpan.textContent = emoji;
      emojiSpan.style.cursor = 'pointer';
      emojiSpan.style.fontSize = '1.1rem';
      emojiSpan.style.transition = 'transform 0.1s';
      emojiSpan.addEventListener('mouseenter', () => {
        emojiSpan.style.transform = 'scale(1.3)';
      });
      emojiSpan.addEventListener('mouseleave', () => {
        emojiSpan.style.transform = 'scale(1)';
      });
      emojiSpan.addEventListener('click', async () => {
        picker.remove();
        const reactionEnvelope = {
          type: 'x.msg.reaction',
          target_msg_id: timestamp,
          emoji: emoji
        };
        const success = await transmitPayload(JSON.stringify(reactionEnvelope));
        if (success) {
          renderReactionInline(timestamp, emoji, 'You');
        }
      });
      picker.appendChild(emojiSpan);
    });

    msgEl.appendChild(picker);

    const dismiss = () => {
      picker.remove();
      document.removeEventListener('click', dismiss);
    };
    setTimeout(() => document.addEventListener('click', dismiss), 0);
  });

  msgEl.appendChild(reactBtn);
}

function updateTypingPreview(senderName, text) {
  let container = document.getElementById('typing-preview-container');

  if (!text || text.trim() === '') {
    if (container) {
      container.remove();
    }
    return;
  }

  if (!container) {
    container = document.createElement('div');
    container.id = 'typing-preview-container';
    container.style.padding = '8px 12px';
    container.style.margin = '8px 0';
    container.style.borderRadius = '8px';
    container.style.fontStyle = 'italic';
    container.style.fontSize = '0.85rem';
    container.style.color = '#8a8a8a';
    container.style.background = 'rgba(255, 255, 255, 0.05)';
    container.style.borderLeft = '3px solid #0078d4';
    container.style.alignSelf = 'flex-start';
    container.style.width = 'fit-content';
    container.style.maxWidth = '80%';
    messagesEl.appendChild(container);
  }

  container.textContent = `${senderName} is typing: ${text}...`;
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

let lastTypingSent = 0;
let typingTimeout = null;

async function sendTypingDraft(text) {
  const mode = window.ANONYMUS_MODE || 'relay';
  if (mode === 'p2p' && !activeContact) return;
  if (mode === 'relay' && (!relaySession.sendChainKey || !relaySession.theirQueueId)) return;

  await transmitPayload(JSON.stringify({
    type: 'x.msg.live',
    content: text
  }), true);
}

// Attach typing keyboard event listener
if (inputEl) {
  inputEl.addEventListener('input', () => {
    const now = Date.now();
    if (now - lastTypingSent > 500) {
      lastTypingSent = now;
      sendTypingDraft(inputEl.value);
    }
    if (typingTimeout) clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => {
      sendTypingDraft(inputEl.value);
    }, 500);
  });
}

// =================================-------------------------------------------
// DECENTRALIZED GROUPS LOGIC (Month 5 Week 19)
// =================================-------------------------------------------
let activeGroup = null;

async function loadGroupsList() {
  const mode = window.ANONYMUS_MODE || 'relay';
  if (mode !== 'p2p') return;
  const groupsListEl = document.getElementById('groups-list');
  if (!groupsListEl) return;
  groupsListEl.replaceChildren();

  try {
    const res = await fetch('/api/groups');
    const groups = await res.json();
    for (const g of groups) {
      const li = document.createElement('li');
      li.dataset.groupId = g.group_id;
      if (activeGroup && activeGroup.group_id === g.group_id) {
        li.className = 'active';
      }

      const nameSpan = document.createElement('span');
      nameSpan.className = 'contact-name';
      nameSpan.textContent = g.name;

      const descSpan = document.createElement('span');
      descSpan.className = 'contact-address';
      descSpan.textContent = "Founder: " + g.founder_onion.slice(0, 10) + '…';

      li.appendChild(nameSpan);
      li.appendChild(descSpan);
      li.addEventListener('click', () => selectGroup(g));
      groupsListEl.appendChild(li);
    }
  } catch (err) {
    console.error("Failed to load groups list:", err);
  }
}

async function selectGroup(group) {
  activeGroup = group;
  activeContact = null;

  // Highlight active sidebar item
  document.querySelectorAll('.contacts-list-p2p li').forEach(el => el.classList.remove('active'));
  const groupLi = Array.from(document.querySelectorAll('#groups-list li')).find(li => li.dataset.groupId === group.group_id);
  if (groupLi) groupLi.classList.add('active');

  switchPanel('chat');
  const isChannel = group.is_channel === 1;
  chattingWithName.textContent = `${isChannel ? 'Channel' : 'Group'}: ${group.name}`;

  // Toggle UI elements
  document.querySelectorAll('.mode-p2p-only').forEach(el => el.style.display = 'none');
  const groupCtrl = document.getElementById('group-header-controls');
  if (groupCtrl) groupCtrl.style.display = 'flex';
  const safetyContainer = document.getElementById('ui-safety-number');
  if (safetyContainer) safetyContainer.parentElement.style.display = 'none';
  const groupPane = document.getElementById('group-info-pane');
  if (groupPane) groupPane.style.display = 'none';

  // Enable/disable input based on channel permissions
  const isFounder = group.founder_onion.toLowerCase() === myOnionAddress.toLowerCase();
  const msgInput = document.getElementById('message-input');
  const sendBtn = document.getElementById('send-btn');
  const recordVoiceBtn = document.getElementById('btn-record-voice');
  const recordVideoBtn = document.getElementById('btn-record-video');

  if (isChannel && !isFounder) {
    if (msgInput) {
      msgInput.disabled = true;
      msgInput.placeholder = "Only the channel creator can send messages";
    }
    if (sendBtn) sendBtn.disabled = true;
    if (recordVoiceBtn) recordVoiceBtn.disabled = true;
    if (recordVideoBtn) recordVideoBtn.disabled = true;
  } else {
    if (msgInput) {
      msgInput.disabled = false;
      msgInput.placeholder = "Type a message...";
    }
    if (sendBtn) sendBtn.disabled = false;
    if (recordVoiceBtn) recordVoiceBtn.disabled = false;
    if (recordVideoBtn) recordVideoBtn.disabled = false;
  }

  messagesEl.replaceChildren();
  await loadGroupMessagesHistory(group.group_id);
}

async function loadGroupMessagesHistory(groupId) {
  try {
    const res = await fetch(`/api/groups/${groupId}/messages`);
    const msgs = await res.json();
    for (const m of msgs) {
      const isMe = m.sender_onion === myOnionAddress;
      const senderName = isMe ? 'You' : m.sender_nickname;
      addMessageLine(senderName, m.message, m.timestamp);
    }
  } catch (err) {
    console.error("Failed to load group message history:", err);
  }
}

async function sendGroupMessage(groupId, text) {
  try {
    const res = await fetch(`/api/groups/${groupId}`);
    const data = await res.json();
    if (!data.group) return;

    const members = data.members;
    const ts = Date.now();

    // Save locally
    await fetch('/api/groups/save_message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        group_id: groupId,
        sender_onion: myOnionAddress,
        sender_nickname: myLocalUsername,
        message: text,
        timestamp: ts
      })
    });

    // Broadcast envelope
    const envelope = {
      type: 'x.grp.message',
      group_id: groupId,
      sender_onion: myOnionAddress,
      sender_nickname: myLocalUsername,
      content: text,
      timestamp: ts
    };

    // Render locally
    addMessageLine('You', text, ts);

    for (const m of members) {
      if (m.member_onion !== myOnionAddress) {
        await transmitPayload(JSON.stringify(envelope), false, m.member_onion);
      }
    }
  } catch (err) {
    console.error("Failed to send group message:", err);
  }
}

// Group Modal creation UI
async function openCreateGroupModal() {
  const modal = document.getElementById('create-group-modal');
  const contactsContainer = document.getElementById('create-group-contacts-list');
  contactsContainer.replaceChildren();

  const res = await fetch('/api/contacts');
  const contacts = await res.json();
  const accepted = contacts.filter(c => c.status === 'accepted');

  if (accepted.length === 0) {
    contactsContainer.textContent = "No accepted contacts to invite.";
  } else {
    for (const c of accepted) {
      const label = document.createElement('label');
      label.style.display = 'flex';
      label.style.alignItems = 'center';
      label.style.gap = '8px';
      label.style.margin = '4px 0';
      label.style.color = 'var(--chat-text)';

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.value = c.onion_address;
      checkbox.dataset.nickname = c.nickname;

      label.appendChild(checkbox);
      label.appendChild(document.createTextNode(c.display_name || c.nickname));
      contactsContainer.appendChild(label);
    }
  }

  modal.style.display = 'flex';
}

async function submitCreateGroup() {
  const nameInput = document.getElementById('new-group-name');
  const name = nameInput.value.trim();
  if (!name) {
    alert("Please enter a group name.");
    return;
  }

  const selectedOnions = Array.from(document.querySelectorAll('#create-group-contacts-list input[type="checkbox"]:checked')).map(cb => cb.value);

  try {
    const isChannelChecked = document.getElementById('new-group-is-channel').checked ? 1 : 0;
    const res = await fetch('/api/groups/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        founder_onion: myOnionAddress,
        is_channel: isChannelChecked
      })
    });
    const data = await res.json();
    if (data.success) {
      const groupId = data.group_id;

      // Save invited members locally
      for (const cb of document.querySelectorAll('#create-group-contacts-list input[type="checkbox"]:checked')) {
        await fetch('/api/groups/add_member', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            group_id: groupId,
            member_onion: cb.value,
            nickname: cb.dataset.nickname,
            role: 'member'
          })
        });
      }

      // Send invite E2EE payload to each member
      const inviteEnvelope = {
        type: 'x.grp.invite',
        group_id: groupId,
        name: name,
        founder_onion: myOnionAddress,
        is_channel: isChannelChecked
      };
      for (const onion of selectedOnions) {
        await transmitPayload(JSON.stringify(inviteEnvelope), false, onion);
      }

      document.getElementById('create-group-modal').style.display = 'none';
      nameInput.value = '';
      await loadGroupsList();
      alert('Group created successfully and invitations sent!');
    }
  } catch (err) {
    console.error("Failed to create group:", err);
  }
}

async function copyGroupInviteLink(groupId) {
  try {
    const resGroup = await fetch(`/api/groups/${groupId}`);
    const data = await resGroup.json();
    const groupName = data.group.name;

    const resToken = await fetch('/api/groups/invite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group_id: groupId })
    });
    const inviteData = await resToken.json();
    if (inviteData.success) {
      const inviteUrl = `${window.location.origin}/?group_invite=true&token=${inviteData.token}&onion=${myOnionAddress}&group_id=${groupId}&name=${encodeURIComponent(groupName)}`;
      navigator.clipboard.writeText(inviteUrl).then(() => {
        alert('Group invite link copied to clipboard!');
      });
    }
  } catch (err) {
    console.error("Failed to generate group invite:", err);
  }
}

async function loadGroupInfoPane(groupId) {
  const listContainer = document.getElementById('group-members-list');
  listContainer.replaceChildren();

  try {
    const res = await fetch(`/api/groups/${groupId}`);
    const data = await res.json();
    const members = data.members;

    const resVouches = await fetch(`/api/groups/${groupId}/vouches`);
    const vouches = await resVouches.json();

    for (const m of members) {
      const item = document.createElement('div');
      item.style.display = 'flex';
      item.style.justifyContent = 'space-between';
      item.style.alignItems = 'center';
      item.style.padding = '4px 8px';
      item.style.background = 'rgba(255, 255, 255, 0.05)';
      item.style.borderRadius = '4px';

      const details = document.createElement('div');

      const name = document.createElement('strong');
      name.textContent = m.nickname;
      name.style.color = 'var(--chat-text)';

      const roleBadge = document.createElement('span');
      roleBadge.textContent = ` [${m.role}]`;
      roleBadge.style.fontSize = '0.75rem';
      roleBadge.style.color = '#0078d4';

      // Vouch stats
      const memberVouches = vouches.filter(v => v.vouched_member === m.member_onion);
      const vouchCount = memberVouches.length;

      const vouchText = document.createElement('span');
      vouchText.textContent = ` (Vouched: ${vouchCount})`;
      vouchText.style.fontSize = '0.8rem';
      vouchText.style.color = '#8a8a8a';

      details.appendChild(name);
      details.appendChild(roleBadge);
      details.appendChild(vouchText);

      item.appendChild(details);

      // If not me and we haven't vouched for them yet, show Vouch button
      const hasVouched = vouches.some(v => v.vouching_member === myOnionAddress && v.vouched_member === m.member_onion);
      if (m.member_onion !== myOnionAddress && !hasVouched) {
        const btnVouch = document.createElement('button');
        btnVouch.textContent = "Vouch";
        btnVouch.className = "btn";
        btnVouch.style.padding = "2px 6px";
        btnVouch.style.fontSize = "0.75rem";
        btnVouch.addEventListener('click', async () => {
          await fetch('/api/groups/vouch', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              group_id: groupId,
              vouching_member: myOnionAddress,
              vouched_member: m.member_onion
            })
          });

          // Broadcast vouch E2EE payload to all members
          const vouchEnvelope = {
            type: 'x.grp.vouch',
            group_id: groupId,
            vouching_member: myOnionAddress,
            vouched_member: m.member_onion
          };
          for (const mem of members) {
            if (mem.member_onion !== myOnionAddress) {
              await transmitPayload(JSON.stringify(vouchEnvelope), false, mem.member_onion);
            }
          }

          loadGroupInfoPane(groupId);
        });
        item.appendChild(btnVouch);
      }

      listContainer.appendChild(item);
    }
  } catch (err) {
    console.error("Failed to load group info pane:", err);
  }
}


// =================================-------------------------------------------
// AUDIO / VIDEO MESSAGE RECORDING UTILITIES (Month 5 Week 20)
// =================================-------------------------------------------
let mediaRecorder = null;
let recordingChunks = [];
let recordingStartTime = 0;
let recordingTimerInterval = null;
let recordingStream = null;

function startRecordingTimer(timerEl) {
  recordingStartTime = Date.now();
  if (recordingTimerInterval) clearInterval(recordingTimerInterval);
  recordingTimerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
    const mins = Math.floor(elapsed / 60);
    const secs = elapsed % 60;
    timerEl.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
  }, 1000);
}

function stopRecordingTimer() {
  if (recordingTimerInterval) {
    clearInterval(recordingTimerInterval);
    recordingTimerInterval = null;
  }
}

// Voice note recording
async function initVoiceRecording() {
  try {
    recordingStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recordingChunks = [];

    mediaRecorder = new MediaRecorder(recordingStream, { mimeType: 'audio/webm' });
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) recordingChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(recordingChunks, { type: 'audio/webm' });
      const file = new File([audioBlob], `voice_note_${Date.now()}.webm`, { type: 'audio/webm' });
      await uploadAndSendMediaMessage(file);
      cleanupRecordingStream();
    };

    // UI changes
    document.getElementById('recording-overlay').style.display = 'flex';
    document.getElementById('message-input').style.display = 'none';
    document.getElementById('btn-record-voice').style.display = 'none';
    document.getElementById('btn-record-video').style.display = 'none';
    document.getElementById('send-btn').style.display = 'none';

    startRecordingTimer(document.getElementById('recording-timer'));
    mediaRecorder.start();
  } catch (err) {
    console.error("Failed to start voice recording:", err);
    alert("Microphone access denied or unsupported.");
  }
}

function cancelVoiceRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.onstop = () => {
      cleanupRecordingStream();
    };
    mediaRecorder.stop();
  }
  resetRecordingUI();
}

function stopVoiceRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
  resetRecordingUI();
}

function resetRecordingUI() {
  stopRecordingTimer();
  document.getElementById('recording-overlay').style.display = 'none';
  document.getElementById('message-input').style.display = 'block';
  document.getElementById('btn-record-voice').style.display = 'block';
  document.getElementById('btn-record-video').style.display = 'block';
  document.getElementById('send-btn').style.display = 'block';
  document.getElementById('recording-timer').textContent = "0:00";
}

function cleanupRecordingStream() {
  if (recordingStream) {
    recordingStream.getTracks().forEach(track => track.stop());
    recordingStream = null;
  }
}

// Video note recording
let videoRecordingStream = null;
let videoMediaRecorder = null;
let videoChunks = [];

async function initVideoRecording() {
  const modal = document.getElementById('video-record-modal');
  const preview = document.getElementById('video-record-preview');

  try {
    videoRecordingStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
    preview.srcObject = videoRecordingStream;

    document.getElementById('btn-start-video-record').style.display = 'block';
    document.getElementById('btn-stop-video-record').style.display = 'none';
    document.getElementById('video-record-timer').textContent = "0:00";

    modal.style.display = 'flex';
  } catch (err) {
    console.error("Failed to access camera/mic for video note:", err);
    alert("Camera/Microphone access denied or unsupported.");
  }
}

function startVideoRecording() {
  videoChunks = [];
  videoMediaRecorder = new MediaRecorder(videoRecordingStream, { mimeType: 'video/webm' });
  videoMediaRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) videoChunks.push(e.data);
  };

  videoMediaRecorder.onstop = async () => {
    const videoBlob = new Blob(videoChunks, { type: 'video/webm' });
    const file = new File([videoBlob], `video_note_${Date.now()}.webm`, { type: 'video/webm' });
    await uploadAndSendMediaMessage(file);
    cleanupVideoRecording();
  };

  document.getElementById('btn-start-video-record').style.display = 'none';
  document.getElementById('btn-stop-video-record').style.display = 'block';

  startRecordingTimer(document.getElementById('video-record-timer'));
  videoMediaRecorder.start();
}

function stopVideoRecording() {
  if (videoMediaRecorder && videoMediaRecorder.state !== 'inactive') {
    videoMediaRecorder.stop();
  }
  document.getElementById('video-record-modal').style.display = 'none';
}

function cancelVideoRecording() {
  cleanupVideoRecording();
  document.getElementById('video-record-modal').style.display = 'none';
}

function cleanupVideoRecording() {
  stopRecordingTimer();
  if (videoRecordingStream) {
    videoRecordingStream.getTracks().forEach(track => track.stop());
    videoRecordingStream = null;
  }
  const preview = document.getElementById('video-record-preview');
  if (preview) preview.srcObject = null;
}

// Media upload and E2EE dispatch
async function uploadAndSendMediaMessage(file) {
  addStatusLine(`Uploading media note "${file.name}"...`);

  try {
    const result = await uploadFileXFTP(file, (current, total) => {
      const pct = Math.round((current / total) * 100);
      addStatusLine(`Uploading media note (${pct}%)...`);
    });

    const envelope = {
      type: 'x.file.descr',
      file_name: file.name,
      file_size: file.size,
      master_key: result.masterKey,
      chunks: result.chunkIds,
      sender_onion: myOnionAddress,
      relay: activeContact ? activeContact.preferred_file_relay : null
    };

    const success = await transmitPayload(JSON.stringify(envelope));
    if (success) {
      renderFileDownloadMessage('You', envelope);
      addStatusLine("Media note sent successfully!");
    } else {
      addStatusLine("Failed to transmit media note descriptor.");
    }
  } catch (err) {
    console.error("Failed to upload/send media message:", err);
    addStatusLine("Failed to upload media message.");
  }
}


// =================================-------------------------------------------
// PROFILE MANAGEMENT UTILITIES (Month 6 Week 21)
// =================================-------------------------------------------
async function loadProfilesList() {
  const select = document.getElementById('profile-select');
  if (!select) return;

  try {
    const res = await fetch('/api/profiles');
    const profiles = await res.json();

    select.innerHTML = '';

    const optDefault = document.createElement('option');
    optDefault.value = 'default';
    optDefault.textContent = 'Default Profile';
    select.appendChild(optDefault);

    profiles.forEach(p => {
      if (p.profile_id !== 'default') {
        const opt = document.createElement('option');
        opt.value = p.profile_id;
        opt.textContent = p.display_name;
        select.appendChild(opt);
      }
    });

    const activeRes = await fetch('/api/profiles/active');
    const activeProf = await activeRes.json();
    activeProfileId = activeProf.profile_id;

    if (activeProf.hidden) {
      const optHidden = document.createElement('option');
      optHidden.value = activeProf.profile_id;
      optHidden.textContent = `🔒 ${activeProf.display_name}`;
      select.appendChild(optHidden);
    }

    select.value = activeProfileId;
  } catch (err) {
    console.error("Failed to load profiles:", err);
  }
}

async function handleProfileChange(e) {
  const profileId = e.target.value;
  try {
    const res = await fetch('/api/profiles/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile_id: profileId })
    });
    const data = await res.json();
    if (data.success) {
      activeProfileId = profileId;
      addStatusLine(`Switched to profile: ${profileId === 'default' ? 'Default' : profileId}`);

      activeContact = null;
      activeGroup = null;
      document.getElementById('chat-header-title').textContent = 'Select a peer or group to start chatting';
      document.getElementById('messages').innerHTML = '';

      await loadContactsList();
      await loadGroupsList();
      await loadProfilesList();
    } else {
      alert("Failed to switch profile: " + data.error);
      loadProfilesList();
    }
  } catch (err) {
    console.error(err);
    loadProfilesList();
  }
}

async function submitCreateProfile() {
  const name = document.getElementById('new-profile-name').value.trim();
  const makeHidden = document.getElementById('profile-hidden-checkbox').checked;
  const passphrase = document.getElementById('new-profile-passphrase').value.trim();

  if (!name) {
    alert("Profile display name is required.");
    return;
  }
  if (makeHidden && !passphrase) {
    alert("Passphrase is required for hidden profiles.");
    return;
  }

  try {
    const res = await fetch('/api/profiles/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        display_name: name,
        hidden: makeHidden ? 1 : 0,
        passphrase: passphrase
      })
    });
    const data = await res.json();
    if (data.success) {
      document.getElementById('create-profile-modal').style.display = 'none';
      document.getElementById('new-profile-name').value = '';
      document.getElementById('profile-hidden-checkbox').checked = false;
      document.getElementById('new-profile-passphrase').value = '';
      document.getElementById('profile-passphrase-section').style.display = 'none';

      addStatusLine(`Created profile: ${name}`);
      await loadProfilesList();
    } else {
      alert("Failed to create profile: " + data.error);
    }
  } catch (err) {
    console.error(err);
  }
}

async function submitUnlockProfile() {
  const passphrase = document.getElementById('unlock-profile-passphrase').value.trim();
  if (!passphrase) {
    alert("Passphrase is required.");
    return;
  }

  try {
    const res = await fetch('/api/profiles/unlock', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ passphrase: passphrase })
    });
    const data = await res.json();
    if (data.success) {
      document.getElementById('unlock-profile-modal').style.display = 'none';
      document.getElementById('unlock-profile-passphrase').value = '';

      activeProfileId = data.profile.profile_id;
      addStatusLine(`Unlocked hidden profile: ${data.profile.display_name}`);

      activeContact = null;
      activeGroup = null;
      document.getElementById('chat-header-title').textContent = 'Select a peer or group to start chatting';
      document.getElementById('messages').innerHTML = '';

      await loadContactsList();
      await loadGroupsList();
      await loadProfilesList();
    } else {
      alert("Incorrect passphrase.");
    }
  } catch (err) {
    console.error(err);
    alert("Incorrect passphrase.");
  }
}

async function initDevicePairing() {
  try {
    const res = await fetch('/api/sync/pair', { method: 'POST' });
    if (res.status !== 200) {
      alert("Failed to initialize pairing broker.");
      return;
    }
    const data = await res.json();
    if (data.success) {
      document.getElementById('pairing-info-section').style.display = 'block';
      document.getElementById('pairing-payload-text').textContent = JSON.stringify(data, null, 2);
    } else {
      alert("Error: " + data.error);
    }
  } catch (err) {
    alert("Pairing request failed: " + err);
  }
}

async function submitPushSync() {
  const payloadStr = document.getElementById('push-pairing-payload').value.trim();
  if (!payloadStr) {
    alert("Please paste the partner pairing payload.");
    return;
  }

  let payload;
  try {
    payload = JSON.parse(payloadStr);
  } catch (e) {
    alert("Invalid credentials format. Must be JSON.");
    return;
  }

  try {
    const res = await fetch('/api/sync/push', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (res.status === 200 && data.success) {
      alert("Database backup successfully synchronized with partner device!");
      document.getElementById('push-sync-modal').style.display = 'none';
      document.getElementById('push-pairing-payload').value = '';
    } else {
      alert("Sync failed: " + (data.error || data.message));
    }
  } catch (err) {
    alert("Network sync failed: " + err);
  }
}


initApp();
})();
