package com.example.privacychat.ui.chat

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.ExitToApp
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.privacychat.data.ChatManager
import com.example.privacychat.data.ChatMessage
import com.example.privacychat.data.ConnectionStatus

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(
    onResetConfig: () -> Unit
) {
    var activeChatTarget by remember { mutableStateOf<String?>(null) }
    val connectionStatus by ChatManager.connectionStatus.collectAsState()
    val onlineUsers by ChatManager.onlineUsers.collectAsState()
    val conversations by ChatManager.conversations.collectAsState()

    // Harmonious curated dark palette
    val bgSlate900 = Color(0xFF0F172A)
    val bgSlate800 = Color(0xFF1E293B)
    val emeraldAccent = Color(0xFF10B981)
    val amberWarning = Color(0xFFF59E0B)
    val coralError = Color(0xFFEF4444)

    // Trigger connection when screen enters composition
    LaunchedEffect(Unit) {
        ChatManager.connect()
    }

    // Back button behavior: if inside a conversation, return to user list
    BackHandler(enabled = activeChatTarget != null) {
        activeChatTarget = null
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                text = "Anonymouse",
                                fontWeight = FontWeight.Bold,
                                color = Color.White,
                                fontSize = 18.sp
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            // Status indicator badge
                            val badgeColor = when (connectionStatus) {
                                ConnectionStatus.CONNECTED -> emeraldAccent
                                ConnectionStatus.CONNECTING -> amberWarning
                                ConnectionStatus.DISCONNECTED -> Color.Gray
                                ConnectionStatus.ERROR -> coralError
                            }
                            val statusText = when (connectionStatus) {
                                ConnectionStatus.CONNECTED -> "Online"
                                ConnectionStatus.CONNECTING -> "Connecting"
                                ConnectionStatus.DISCONNECTED -> "Offline"
                                ConnectionStatus.ERROR -> "Error"
                            }
                            Box(
                                modifier = Modifier
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(badgeColor.copy(alpha = 0.2f))
                                    .padding(horizontal = 6.dp, vertical = 2.dp)
                            ) {
                                Text(
                                    text = statusText,
                                    color = badgeColor,
                                    fontSize = 10.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                        }
                        Text(
                            text = "Logged in as: ${ChatManager.currentUsername ?: "Anonymous"}",
                            fontSize = 11.sp,
                            color = Color(0xFF94A3B8)
                        )
                    }
                },
                actions = {
                    IconButton(
                        onClick = {
                            ChatManager.resetClient()
                            onResetConfig()
                        }
                    ) {
                        Icon(
                            imageVector = Icons.Default.ExitToApp,
                            contentDescription = "Logout and Reset settings",
                            tint = coralError
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = bgSlate900,
                    titleContentColor = Color.White,
                    actionIconContentColor = Color.White
                )
            )
        },
        containerColor = bgSlate900
    ) { paddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // User List view (shown when no activeChatTarget is selected)
            if (activeChatTarget == null) {
                UserList(
                    users = onlineUsers,
                    onUserSelected = { user ->
                        activeChatTarget = user
                        ChatManager.requestPublicKeyIfNeeded(user)
                    }
                )
            }

            // Message View (overlay slide-in when activeChatTarget is selected)
            AnimatedVisibility(
                visible = activeChatTarget != null,
                enter = slideInHorizontally(initialOffsetX = { it }),
                exit = slideOutHorizontally(targetOffsetX = { it })
            ) {
                activeChatTarget?.let { partner ->
                    val messages = conversations[partner] ?: emptyList()
                    ConversationView(
                        partner = partner,
                        messages = messages,
                        onBack = { activeChatTarget = null },
                        onSendMessage = { text ->
                            ChatManager.sendPrivateMessage(partner, text)
                        }
                    )
                }
            }
        }
    }
}

@Composable
fun UserList(
    users: List<String>,
    onUserSelected: (String) -> Unit
) {
    if (users.isEmpty()) {
        Box(
            modifier = Modifier.fillMaxSize(),
            contentAlignment = Alignment.Center
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(
                    imageVector = Icons.Default.Lock,
                    contentDescription = "Waiting",
                    tint = Color(0xFF475569),
                    modifier = Modifier.size(48.dp)
                )
                Spacer(modifier = Modifier.height(16.dp))
                Text(
                    text = "No other users online",
                    color = Color(0xFF64748B),
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Medium
                )
                Text(
                    text = "Ensure other devices connect to same network",
                    color = Color(0xFF475569),
                    fontSize = 12.sp,
                    modifier = Modifier.padding(top = 4.dp)
                )
            }
        }
    } else {
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            item {
                Text(
                    text = "Online Users",
                    color = Color.White,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(bottom = 6.dp)
                )
            }
            items(users) { username ->
                UserRow(username = username, onClick = { onUserSelected(username) })
            }
        }
    }
}

@Composable
fun UserRow(
    username: String,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() }
            .border(1.dp, Color(0x1AFFFFFF), RoundedCornerShape(16.dp)),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0x0FFFFFFF))
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // User Avatar circle
            Box(
                modifier = Modifier
                    .size(40.dp)
                    .clip(CircleShape)
                    .background(Color(0xFF10B981).copy(alpha = 0.2f)),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = username.take(2).uppercase(),
                    color = Color(0xFF10B981),
                    fontWeight = FontWeight.Bold,
                    fontSize = 14.sp
                )
            }

            Spacer(modifier = Modifier.width(16.dp))

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = username,
                    color = Color.White,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 16.sp
                )
                Text(
                    text = "Tap to chat securely (E2EE)",
                    color = Color(0xFF64748B),
                    fontSize = 12.sp
                )
            }
            
            Icon(
                imageVector = Icons.Default.Lock,
                contentDescription = "Secured",
                tint = Color(0xFF10B981).copy(alpha = 0.5f),
                modifier = Modifier.size(16.dp)
            )
        }
    }
}

@Composable
fun ConversationView(
    partner: String,
    messages: List<ChatMessage>,
    onBack: () -> Unit,
    onSendMessage: (String) -> Boolean
) {
    var messageText by remember { mutableStateOf("") }
    val listState = rememberLazyListState()

    // Auto-scroll to bottom when new messages arrive
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(messages.size - 1)
        }
    }

    val bgSlate900 = Color(0xFF0F172A)
    val bgSlate800 = Color(0xFF1E293B)
    val emeraldAccent = Color(0xFF10B981)

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(bgSlate900)
    ) {
        // Conversation Top Bar
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(bgSlate800)
                .padding(vertical = 12.dp, horizontal = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onBack) {
                Icon(
                    imageVector = Icons.Default.ArrowBack,
                    contentDescription = "Back to list",
                    tint = Color.White
                )
            }

            Box(
                modifier = Modifier
                    .size(36.dp)
                    .clip(CircleShape)
                    .background(emeraldAccent.copy(alpha = 0.2f)),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = partner.take(2).uppercase(),
                    color = emeraldAccent,
                    fontWeight = FontWeight.Bold,
                    fontSize = 13.sp
                )
            }

            Spacer(modifier = Modifier.width(12.dp))

            Column {
                Text(
                    text = partner,
                    color = Color.White,
                    fontWeight = FontWeight.Bold,
                    fontSize = 15.sp
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.Lock,
                        contentDescription = "Encrypted",
                        tint = emeraldAccent,
                        modifier = Modifier.size(10.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = "End-to-End Encrypted",
                        color = emeraldAccent,
                        fontSize = 10.sp
                    )
                }
            }
        }

        // Messages List
        LazyColumn(
            state = listState,
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                Spacer(modifier = Modifier.height(12.dp))
                // Info banner inside the chat
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                        .background(Color(0x0AFFFFFF))
                        .border(1.dp, Color(0x1AFFFFFF), RoundedCornerShape(12.dp))
                        .padding(12.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "Keys exchanged locally via ECDH. Relayed messages are fully encrypted with AES-256-GCM. The server never reads nor stores messages.",
                        color = Color(0xFF64748B),
                        fontSize = 11.sp,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                        lineHeight = 15.sp
                    )
                }
                Spacer(modifier = Modifier.height(12.dp))
            }

            items(messages) { message ->
                MessageBubble(message = message)
            }
            
            item {
                Spacer(modifier = Modifier.height(12.dp))
            }
        }

        // Input Row
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(bgSlate800)
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedTextField(
                value = messageText,
                onValueChange = { messageText = it },
                placeholder = { Text("Type a message…", color = Color(0xFF64748B)) },
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = emeraldAccent,
                    unfocusedBorderColor = Color(0x1AFFFFFF),
                    focusedContainerColor = bgSlate900,
                    unfocusedContainerColor = bgSlate900,
                    focusedTextColor = Color.White,
                    unfocusedTextColor = Color.White
                ),
                shape = RoundedCornerShape(24.dp),
                maxLines = 4,
                modifier = Modifier
                    .weight(1f)
                    .padding(end = 8.dp)
            )

            IconButton(
                onClick = {
                    val trimmed = messageText.trim()
                    if (trimmed.isNotBlank()) {
                        val success = onSendMessage(trimmed)
                        if (success) {
                            messageText = ""
                        }
                    }
                },
                enabled = messageText.trim().isNotBlank(),
                colors = IconButtonDefaults.iconButtonColors(
                    containerColor = emeraldAccent,
                    contentColor = Color.Black,
                    disabledContainerColor = Color(0xFF1E293B),
                    disabledContentColor = Color(0xFF475569)
                ),
                modifier = Modifier.size(48.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.Send,
                    contentDescription = "Send message"
                )
            }
        }
    }
}

@Composable
fun MessageBubble(message: ChatMessage) {
    val isOwn = message.sender == "You"
    val alignment = if (isOwn) Alignment.End else Alignment.Start
    val bubbleBg = if (isOwn) Color(0xFF0F766E) else Color(0xFF1E293B) // Dark Teal vs Slate 800
    val bubbleShape = if (isOwn) {
        RoundedCornerShape(16.dp, 16.dp, 0.dp, 16.dp)
    } else {
        RoundedCornerShape(16.dp, 16.dp, 16.dp, 0.dp)
    }

    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = alignment
    ) {
        // Sender name (only for incoming messages)
        if (!isOwn) {
            Text(
                text = message.sender,
                color = Color(0xFF94A3B8),
                fontSize = 11.sp,
                modifier = Modifier.padding(start = 4.dp, bottom = 2.dp)
            )
        }

        Box(
            modifier = Modifier
                .clip(bubbleShape)
                .background(bubbleBg)
                .border(1.dp, Color(0x0FFFFFFF), bubbleShape)
                .padding(horizontal = 14.dp, vertical = 10.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (!message.isDecryptedSuccessfully) {
                    Icon(
                        imageVector = Icons.Default.Warning,
                        contentDescription = "Decryption failed",
                        tint = Color(0xFFEF4444),
                        modifier = Modifier
                            .size(16.dp)
                            .padding(end = 4.dp)
                    )
                    Text(
                        text = message.text,
                        color = Color(0xFFEF4444),
                        fontSize = 14.sp
                    )
                } else {
                    Text(
                        text = message.text,
                        color = Color.White,
                        fontSize = 14.sp
                    )
                }
            }
        }
    }
}
