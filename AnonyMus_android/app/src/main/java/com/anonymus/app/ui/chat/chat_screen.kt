package com.anonymus.app.ui.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material.icons.filled.FlashOn
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import com.anonymus.app.LocalChatManager

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen() {
    val chatManager = LocalChatManager.current
    val conversations by chatManager.conversations.collectAsState()
    val messages = conversations["Peer"] ?: emptyList()
    val disappearTimerSeconds by chatManager.disappearTimerSeconds.collectAsState()

    var messageText by remember { mutableStateOf("") }
    var expanded by remember { mutableStateOf(false) }
    var covertMode by remember { mutableStateOf(false) }

    if (covertMode) {
        // Covert Mode Calculator UI
        Scaffold { paddingValues ->
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues)
                    .background(Color.White)
                    .padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text("Calculator", style = MaterialTheme.typography.headlineMedium, color = Color.Black)
                Spacer(modifier = Modifier.height(24.dp))
                OutlinedTextField(
                    value = "0",
                    onValueChange = {},
                    enabled = false,
                    modifier = Modifier.fillMaxWidth().semantics { contentDescription = "Calculator Display" },
                    textStyle = androidx.compose.ui.text.TextStyle(textAlign = TextAlign.End, fontSize = androidx.compose.ui.unit.TextUnit(32f, androidx.compose.ui.unit.TextUnitType.Sp)),
                    colors = OutlinedTextFieldDefaults.colors(
                        disabledTextColor = Color.Black,
                        disabledBorderColor = Color.Gray
                    )
                )
                Spacer(modifier = Modifier.height(24.dp))
                Button(
                    onClick = { covertMode = false }, // Hidden way to exit
                    modifier = Modifier.fillMaxWidth().height(80.dp).semantics { contentDescription = "Calculate" },
                    colors = ButtonDefaults.buttonColors(containerColor = Color.LightGray)
                ) {
                    Text("=", color = Color.Black, style = MaterialTheme.typography.headlineLarge)
                }
            }
        }
        return
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Chat", style = MaterialTheme.typography.titleMedium)
                        Text(
                            "Verification Code: ${chatManager.safetyNumber ?: "Unknown"}",
                            style = MaterialTheme.typography.bodySmall,
                            fontFamily = FontFamily.Monospace,
                            color = MaterialTheme.colorScheme.tertiary,
                            modifier = Modifier.semantics { contentDescription = "Session verification code" }
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary,
                    actionIconContentColor = MaterialTheme.colorScheme.error
                ),
                actions = {
                    // Elven Cloak Button
                    IconButton(
                        onClick = { covertMode = true },
                        modifier = Modifier.semantics { contentDescription = "Activate Covert Mode" }
                    ) {
                        Icon(Icons.Default.VisibilityOff, contentDescription = "Calculator", tint = MaterialTheme.colorScheme.onPrimary)
                    }

                    // Obliviate Button
                    IconButton(
                        onClick = { chatManager.obliviate() },
                        modifier = Modifier.semantics { contentDescription = "Wipe and clear peer session" }
                    ) {
                        Icon(Icons.Default.FlashOn, contentDescription = "Clear Chat Data", tint = Color(0xFF8B5CF6))
                    }

                    // Tears in Rain (Disappearing Messages)
                    Box {
                        TextButton(
                            onClick = { expanded = true },
                            modifier = Modifier.semantics { contentDescription = "Set disappearing messages timer. Current timer: ${if (disappearTimerSeconds == 0) "Keep Messages" else "$disappearTimerSeconds seconds"}" }
                        ) {
                            Text(
                                if (disappearTimerSeconds == 0) "Keep Msgs" else "${disappearTimerSeconds}s",
                                color = MaterialTheme.colorScheme.onPrimary
                            )
                        }
                        DropdownMenu(
                            expanded = expanded,
                            onDismissRequest = { expanded = false }
                        ) {
                            DropdownMenuItem(
                                text = { Text("Off (Session)") },
                                onClick = { chatManager.setDisappearingTimer(0); expanded = false },
                                modifier = Modifier.semantics { contentDescription = "Disappearing messages off" }
                            )
                            DropdownMenuItem(
                                text = { Text("15 Seconds") },
                                onClick = { chatManager.setDisappearingTimer(15); expanded = false },
                                modifier = Modifier.semantics { contentDescription = "Disappearing messages 15 seconds" }
                            )
                            DropdownMenuItem(
                                text = { Text("60 Seconds") },
                                onClick = { chatManager.setDisappearingTimer(60); expanded = false },
                                modifier = Modifier.semantics { contentDescription = "Disappearing messages 60 seconds" }
                            )
                            DropdownMenuItem(
                                text = { Text("5 Minutes") },
                                onClick = { chatManager.setDisappearingTimer(300); expanded = false },
                                modifier = Modifier.semantics { contentDescription = "Disappearing messages 5 minutes" }
                            )
                            DropdownMenuItem(
                                text = { Text("30 Minutes") },
                                onClick = { chatManager.setDisappearingTimer(1800); expanded = false },
                                modifier = Modifier.semantics { contentDescription = "Disappearing messages 30 minutes" }
                            )
                        }
                    }

                    // Infinity Snap (Panic Button)
                    IconButton(
                        onClick = { chatManager.infinitySnap() },
                        modifier = Modifier.semantics { contentDescription = "Emergency Panic Button: Wipe and destroy session" }
                    ) {
                        Icon(Icons.Default.Warning, contentDescription = "Close Chat", tint = Color(0xFFF59E0B))
                    }
                }
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            LazyColumn(
                modifier = Modifier
                    .weight(1f)
                    .padding(horizontal = 16.dp)
                    .semantics { contentDescription = "List of chat messages" },
                reverseLayout = true
            ) {
                // Reverse list for bottom-up scrolling
                items(messages.reversed(), key = { it.id }) { msg ->
                    val isOwn = msg.sender == "You"
                    val isSystem = msg.sender == "System"

                    if (isSystem) {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = msg.text,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.secondary,
                                textAlign = TextAlign.Center,
                                modifier = Modifier.semantics { contentDescription = "System message: ${msg.text}" }
                            )
                        }
                    } else {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            horizontalArrangement = if (isOwn) Arrangement.End else Arrangement.Start
                        ) {
                            Surface(
                                shape = MaterialTheme.shapes.medium,
                                color = if (isOwn) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.secondaryContainer,
                                modifier = Modifier
                                    .widthIn(max = 280.dp)
                                    .semantics {
                                        contentDescription = "${if (isOwn) "Your message" else "Peer's message"}: ${msg.text}${if (msg.remainingSeconds > 0) ", disappears in ${msg.remainingSeconds} seconds" else ""}"
                                    }
                            ) {
                                Column(modifier = Modifier.padding(12.dp)) {
                                    Text(
                                        text = msg.text,
                                        color = if (!msg.isDecryptedSuccessfully) Color.Red else MaterialTheme.colorScheme.onSurface
                                    )
                                    if (msg.remainingSeconds > 0) {
                                        Spacer(modifier = Modifier.height(4.dp))
                                        Row(
                                            verticalAlignment = Alignment.CenterVertically,
                                            horizontalArrangement = Arrangement.End,
                                            modifier = Modifier.fillMaxWidth()
                                        ) {
                                            Text(
                                                text = "${msg.remainingSeconds}s",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = if (isOwn) {
                                                    MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.6f)
                                                } else {
                                                    MaterialTheme.colorScheme.onSecondaryContainer.copy(alpha = 0.6f)
                                                }
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Input Area
            Surface(
                modifier = Modifier.fillMaxWidth(),
                color = MaterialTheme.colorScheme.surfaceVariant
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    OutlinedTextField(
                        value = messageText,
                        onValueChange = { messageText = it },
                        modifier = Modifier
                            .weight(1f)
                            .semantics { contentDescription = "Message text input field" },
                        placeholder = { Text("Type a message...") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(autoCorrect = false)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = {
                            if (messageText.isNotBlank()) {
                                chatManager.sendPrivateMessage(messageText)
                                messageText = ""
                            }
                        },
                        enabled = messageText.isNotBlank(),
                        modifier = Modifier.semantics { contentDescription = "Send message" }
                    ) {
                        Text("Send")
                    }
                }
            }
        }
    }
}
