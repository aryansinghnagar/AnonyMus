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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.material.icons.filled.FlashOn
import com.anonymus.app.data.ChatManager

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen() {
    val conversations by ChatManager.conversations.collectAsState()
    val messages = conversations["Peer"] ?: emptyList()

    var messageText by remember { mutableStateOf("") }
    var expanded by remember { mutableStateOf(false) }
    var covertMode by remember { mutableStateOf(false) }

    if (covertMode) {
        // Phase 5: Covert Mode Calculator UI
        Scaffold { padding ->
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
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
                    modifier = Modifier.fillMaxWidth(),
                    textStyle = androidx.compose.ui.text.TextStyle(textAlign = TextAlign.End, fontSize = androidx.compose.ui.unit.TextUnit(32f, androidx.compose.ui.unit.TextUnitType.Sp)),
                    colors = OutlinedTextFieldDefaults.colors(
                        disabledTextColor = Color.Black,
                        disabledBorderColor = Color.Gray
                    )
                )
                Spacer(modifier = Modifier.height(24.dp))
                Button(
                    onClick = { covertMode = false }, // Hidden way to exit
                    modifier = Modifier.fillMaxWidth().height(80.dp),
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
                            "Verification Code: ${ChatManager.safetyNumber ?: "Unknown"}",
                            style = MaterialTheme.typography.bodySmall,
                            fontFamily = FontFamily.Monospace,
                            color = MaterialTheme.colorScheme.tertiary
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
                    IconButton(onClick = { covertMode = true }) {
                        Icon(Icons.Default.VisibilityOff, contentDescription = "Calculator", tint = MaterialTheme.colorScheme.onPrimary)
                    }

                    // Obliviate Button
                    IconButton(onClick = { ChatManager.obliviate() }) {
                        Icon(Icons.Default.FlashOn, contentDescription = "Clear Chat Data", tint = Color(0xFF8B5CF6))
                    }

                    // Tears in Rain (Disappearing Messages)
                    Box {
                        TextButton(onClick = { expanded = true }) {
                            Text(
                                if (ChatManager.disappearTimerSeconds == 0) "Keep Msgs" else "${ChatManager.disappearTimerSeconds}s",
                                color = MaterialTheme.colorScheme.onPrimary
                            )
                        }
                        DropdownMenu(
                            expanded = expanded,
                            onDismissRequest = { expanded = false }
                        ) {
                            DropdownMenuItem(text = { Text("Off (Session)") }, onClick = { ChatManager.disappearTimerSeconds = 0; expanded = false })
                            DropdownMenuItem(text = { Text("15 Seconds") }, onClick = { ChatManager.disappearTimerSeconds = 15; expanded = false })
                            DropdownMenuItem(text = { Text("60 Seconds") }, onClick = { ChatManager.disappearTimerSeconds = 60; expanded = false })
                        }
                    }

                    // Infinity Snap (Panic Button)
                    IconButton(onClick = { ChatManager.infinitySnap() }) {
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
                    .padding(horizontal = 16.dp),
                reverseLayout = true
            ) {
                // Reverse list for bottom-up scrolling
                items(messages.reversed()) { msg ->
                    val isOwn = msg.sender == "You"
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp),
                        horizontalArrangement = if (isOwn) Arrangement.End else Arrangement.Start
                    ) {
                        Surface(
                            shape = MaterialTheme.shapes.medium,
                            color = if (isOwn) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.secondaryContainer,
                            modifier = Modifier.widthIn(max = 280.dp)
                        ) {
                            Text(
                                text = msg.text,
                                modifier = Modifier.padding(12.dp),
                                color = if (!msg.isDecryptedSuccessfully) Color.Red else MaterialTheme.colorScheme.onSurface
                            )
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
                        modifier = Modifier.weight(1f),
                        placeholder = { Text("Type a message...") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(autoCorrect = false)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = {
                            if (messageText.isNotBlank()) {
                                ChatManager.sendPrivateMessage(messageText)
                                messageText = ""
                            }
                        },
                        enabled = messageText.isNotBlank()
                    ) {
                        Text("Send")
                    }
                }
            }
        }
    }
}
