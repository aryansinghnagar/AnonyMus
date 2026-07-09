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
import androidx.compose.foundation.clickable
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.BorderStroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

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
    val typingPreview by chatManager.typingPreview.collectAsState()
    var showReactionPickerForMsg by remember { mutableStateOf<ChatMessage?>(null) }

    if (covertMode) {
        var currentVal by remember { mutableStateOf("0") }
        var previousVal by remember { mutableStateOf("") }
        var operation by remember { mutableStateOf<String?>(null) }
        var resetOnNext by remember { mutableStateOf(false) }

        // Configuration
        val exitPasscodes = listOf("1337", "80085", "7777")

        fun evaluate() {
            if (operation == null || previousVal.isEmpty()) return
            val prev = previousVal.toDoubleOrNull() ?: return
            val curr = currentVal.toDoubleOrNull() ?: return
            val result = when (operation) {
                "+" -> prev + curr
                "−" -> prev - curr
                "×" -> prev * curr
                "÷" -> {
                    if (curr == 0.0) {
                        currentVal = "Error"
                        operation = null
                        previousVal = ""
                        resetOnNext = true
                        return
                    }
                    prev / curr
                }
                else -> return
            }
            currentVal = if (result % 1.0 == 0.0) {
                result.toLong().toString()
            } else {
                result.toString()
            }
            operation = null
            previousVal = ""
            resetOnNext = true
        }

        fun handleInput(btn: String) {
            if (btn.toDoubleOrNull() != null || btn == ".") {
                if (resetOnNext) {
                    currentVal = if (btn == ".") "0." else btn
                    resetOnNext = false
                } else {
                    if (btn == ".") {
                        if (!currentVal.contains(".")) {
                            currentVal += "."
                        }
                    } else {
                        if (currentVal == "0") {
                            currentVal = btn
                        } else {
                            currentVal += btn
                        }
                    }
                }
                return
            }

            when (btn) {
                "C" -> {
                    currentVal = "0"
                    previousVal = ""
                    operation = null
                    resetOnNext = false
                }
                "CE" -> {
                    currentVal = "0"
                }
                "⌫" -> {
                    if (currentVal.length > 1) {
                        currentVal = currentVal.dropLast(1)
                    } else {
                        currentVal = "0"
                    }
                }
                "+/-" -> {
                    if (currentVal != "0" && currentVal != "Error") {
                        val v = currentVal.toDoubleOrNull()
                        if (v != null) {
                            val inv = v * -1
                            currentVal = if (inv % 1.0 == 0.0) inv.toLong().toString() else inv.toString()
                        }
                    }
                }
                "1/x" -> {
                    val v = currentVal.toDoubleOrNull()
                    if (v == null || v == 0.0) {
                        currentVal = "Error"
                    } else {
                        val res = 1.0 / v
                        currentVal = if (res % 1.0 == 0.0) res.toLong().toString() else res.toString()
                    }
                    resetOnNext = true
                }
                "x²" -> {
                    val v = currentVal.toDoubleOrNull()
                    if (v == null) {
                        currentVal = "Error"
                    } else {
                        val res = v * v
                        currentVal = if (res % 1.0 == 0.0) res.toLong().toString() else res.toString()
                    }
                    resetOnNext = true
                }
                "√x" -> {
                    val v = currentVal.toDoubleOrNull()
                    if (v == null || v < 0.0) {
                        currentVal = "Error"
                    } else {
                        val res = kotlin.math.sqrt(v)
                        currentVal = if (res % 1.0 == 0.0) res.toLong().toString() else res.toString()
                    }
                    resetOnNext = true
                }
                "%" -> {
                    val v = currentVal.toDoubleOrNull()
                    if (v == null) {
                        currentVal = "Error"
                    } else {
                        val res = v / 100.0
                        currentVal = res.toString()
                    }
                    resetOnNext = true
                }
                "+", "−", "×", "÷" -> {
                    if (operation != null && !resetOnNext) {
                        evaluate()
                    }
                    previousVal = currentVal
                    operation = btn
                    resetOnNext = true
                }
                "=" -> {
                    if (exitPasscodes.contains(currentVal)) {
                        covertMode = false
                        currentVal = "0"
                        previousVal = ""
                        operation = null
                        resetOnNext = false
                        return
                    }
                    evaluate()
                }
            }
        }

        Scaffold { paddingValues ->
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues)
                    .background(Color(0xFF0B0F19))
            ) {
                // Background Grid Canvas
                Canvas(modifier = Modifier.fillMaxSize()) {
                    val width = size.width
                    val height = size.height
                    val gridSpacing = 40.dp.toPx()

                    var x = 0f
                    while (x < width) {
                        drawLine(
                            color = Color.White.copy(alpha = 0.03f),
                            start = androidx.compose.ui.geometry.Offset(x, 0f),
                            end = androidx.compose.ui.geometry.Offset(x, height),
                            strokeWidth = 1f
                        )
                        x += gridSpacing
                    }
                    var y = 0f
                    while (y < height) {
                        drawLine(
                            color = Color.White.copy(alpha = 0.03f),
                            start = androidx.compose.ui.geometry.Offset(0f, y),
                            end = androidx.compose.ui.geometry.Offset(width, y),
                            strokeWidth = 1f
                        )
                        y += gridSpacing
                    }
                }

                // Floating STEM formulas
                Text(
                    text = "iℏ ∂/∂t Ψ(r,t) = ĤΨ(r,t)",
                    color = Color(0xFF6366F1).copy(alpha = 0.12f),
                    fontSize = 18.sp,
                    fontFamily = FontFamily.Serif,
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .padding(start = 24.dp, top = 80.dp)
                        .rotate(-10f)
                )
                Text(
                    text = "e^(iπ) + 1 = 0",
                    color = Color(0xFFA855F7).copy(alpha = 0.1f),
                    fontSize = 20.sp,
                    fontFamily = FontFamily.Serif,
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(end = 32.dp, top = 140.dp)
                        .rotate(8f)
                )
                Text(
                    text = "∇ × E = - ∂B/∂t",
                    color = Color(0xFF6366F1).copy(alpha = 0.12f),
                    fontSize = 18.sp,
                    fontFamily = FontFamily.Serif,
                    modifier = Modifier
                        .align(Alignment.CenterStart)
                        .padding(start = 16.dp)
                        .offset(y = (-150).dp)
                        .rotate(15f)
                )
                Text(
                    text = "F(ω) = ∫ f(t) e^(-iωt) dt",
                    color = Color(0xFF3B82F6).copy(alpha = 0.1f),
                    fontSize = 16.sp,
                    fontFamily = FontFamily.Serif,
                    modifier = Modifier
                        .align(Alignment.BottomStart)
                        .padding(start = 32.dp, bottom = 120.dp)
                        .rotate(-8f)
                )
                Text(
                    text = "G_μν + Λg_μν = (8πG/c⁴) T_μν",
                    color = Color(0xFF6366F1).copy(alpha = 0.12f),
                    fontSize = 16.sp,
                    fontFamily = FontFamily.Serif,
                    modifier = Modifier
                        .align(Alignment.BottomEnd)
                        .padding(end = 24.dp, bottom = 60.dp)
                        .rotate(5f)
                )

                // Glassmorphic Calculator Container
                Card(
                    modifier = Modifier
                        .width(340.dp)
                        .padding(16.dp)
                        .align(Alignment.Center),
                    colors = CardDefaults.cardColors(containerColor = Color(0xCC0F172A)),
                    shape = RoundedCornerShape(16.dp),
                    border = BorderStroke(1.dp, Color(0x26FFFFFF))
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp)
                    ) {
                        // Header
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(bottom = 8.dp)
                                .pointerInput(Unit) {
                                    detectTapGestures(
                                        onDoubleTap = {
                                            covertMode = false
                                        }
                                    )
                                },
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "Calculator",
                                color = Color.White.copy(alpha = 0.7f),
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Medium
                            )
                            Box(
                                modifier = Modifier
                                    .background(Color.White.copy(alpha = 0.08f), RoundedCornerShape(20.dp))
                                    .padding(horizontal = 8.dp, vertical = 2.dp)
                            ) {
                                Text(
                                    text = "Standard",
                                    color = Color.White.copy(alpha = 0.5f),
                                    fontSize = 11.sp
                                )
                            }
                        }

                        // Divider line
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(1.dp)
                                .background(Color.White.copy(alpha = 0.08f))
                        )

                        // Display History
                        Text(
                            text = if (operation != null) "$previousVal $operation" else "",
                            color = Color.White.copy(alpha = 0.45f),
                            fontSize = 13.sp,
                            fontFamily = FontFamily.Monospace,
                            textAlign = TextAlign.End,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp)
                                .height(20.dp)
                        )

                        // Display Current Value
                        Text(
                            text = currentVal,
                            color = Color.White,
                            fontSize = 36.sp,
                            fontFamily = FontFamily.Monospace,
                            fontWeight = FontWeight.Medium,
                            textAlign = TextAlign.End,
                            maxLines = 1,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(bottom = 12.dp)
                        )

                        // Keypad Grid
                        val buttons = listOf(
                            listOf("%", "CE", "C", "⌫"),
                            listOf("1/x", "x²", "√x", "÷"),
                            listOf("7", "8", "9", "×"),
                            listOf("4", "5", "6", "−"),
                            listOf("1", "2", "3", "+"),
                            listOf("+/-", "0", ".", "=")
                        )

                        buttons.forEach { row ->
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 3.dp),
                                horizontalArrangement = Arrangement.spacedBy(6.dp)
                            ) {
                                row.forEach { btn ->
                                    val isOp = btn in listOf("%", "1/x", "x²", "√x", "÷", "×", "−", "+", "CE", "C", "⌫")
                                    val isEq = btn == "="

                                    val containerColor = when {
                                        isEq -> Color(0xFF4F46E5)
                                        isOp -> Color(0xFF1E1B4B)
                                        else -> Color(0x0FFFFFFF)
                                    }
                                    val contentColor = when {
                                        isEq -> Color.White
                                        isOp -> Color(0xFFC7D2FE)
                                        else -> Color.White.copy(alpha = 0.9f)
                                    }

                                    Button(
                                        onClick = { handleInput(btn) },
                                        modifier = Modifier
                                            .weight(1f)
                                            .height(52.dp),
                                        shape = RoundedCornerShape(8.dp),
                                        colors = ButtonDefaults.buttonColors(
                                            containerColor = containerColor,
                                            contentColor = contentColor
                                        ),
                                        contentPadding = PaddingValues(0.dp)
                                    ) {
                                        Text(
                                            text = btn,
                                            fontSize = 16.sp,
                                            fontWeight = if (isEq) FontWeight.Bold else FontWeight.Normal
                                        )
                                    }
                                }
                            }
                        }
                    }
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
                                    .pointerInput(Unit) {
                                        detectTapGestures(
                                            onLongPress = {
                                                if (msg.sender != "System") {
                                                    showReactionPickerForMsg = msg
                                                }
                                            }
                                        )
                                    }
                            ) {
                                Column(modifier = Modifier.padding(12.dp)) {
                                    if (msg.isFile) {
                                        Text(
                                            text = "📄 ${msg.fileName}",
                                            fontWeight = FontWeight.Bold,
                                            color = if (isOwn) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSecondaryContainer
                                        )
                                        Text(
                                            text = String.format("%.2f MB", msg.fileSize / (1024f * 1024f)),
                                            style = MaterialTheme.typography.labelSmall,
                                            color = (if (isOwn) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSecondaryContainer).copy(alpha = 0.6f)
                                        )
                                        Spacer(modifier = Modifier.height(8.dp))
                                        if (msg.fileProgress == -1f) {
                                            Button(
                                                onClick = {
                                                    chatManager.downloadFileXFTP(
                                                        msg.id,
                                                        msg.fileName,
                                                        msg.fileMasterKey,
                                                        msg.fileChunks,
                                                        msg.fileSenderOnion
                                                    )
                                                },
                                                modifier = Modifier.fillMaxWidth()
                                            ) {
                                                Text("Download")
                                            }
                                        } else if (msg.fileProgress >= 0f && msg.fileProgress < 1f) {
                                            Column {
                                                LinearProgressIndicator(
                                                    progress = msg.fileProgress,
                                                    modifier = Modifier.fillMaxWidth()
                                                )
                                                Text(
                                                    text = "Downloading ${Math.round(msg.fileProgress * 100)}%",
                                                    style = MaterialTheme.typography.labelSmall,
                                                    color = (if (isOwn) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSecondaryContainer).copy(alpha = 0.6f)
                                                )
                                            }
                                        } else if (msg.fileProgress == -2f || msg.fileProgress == 1f) {
                                            Text(
                                                text = "✅ Saved to Downloads",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = Color(0xFF2E7D32),
                                                fontWeight = FontWeight.Bold
                                            )
                                        } else if (msg.fileProgress == -3f) {
                                            Button(
                                                onClick = {
                                                    chatManager.downloadFileXFTP(
                                                        msg.id,
                                                        msg.fileName,
                                                        msg.fileMasterKey,
                                                        msg.fileChunks,
                                                        msg.fileSenderOnion
                                                    )
                                                },
                                                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                                                modifier = Modifier.fillMaxWidth()
                                            ) {
                                                Text("❌ Failed. Retry?")
                                            }
                                        }
                                    } else {
                                        Column {
                                            Text(
                                                text = msg.text,
                                                color = if (!msg.isDecryptedSuccessfully) Color.Red else (if (isOwn) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSecondaryContainer)
                                            )
                                            if (msg.isEdited) {
                                                Text(
                                                    text = "edited",
                                                    style = MaterialTheme.typography.labelSmall,
                                                    fontStyle = FontStyle.Italic,
                                                    color = (if (isOwn) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSecondaryContainer).copy(alpha = 0.5f),
                                                    modifier = Modifier.padding(top = 2.dp)
                                                )
                                            }
                                        }
                                    }

                                    Row(
                                        verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.End,
                                        modifier = Modifier.fillMaxWidth().padding(top = 4.dp)
                                    ) {
                                        val timeFormat = java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault())
                                        val timeStr = timeFormat.format(java.util.Date(msg.timestamp))
                                        Text(
                                            text = timeStr,
                                            style = MaterialTheme.typography.labelSmall,
                                            color = (if (isOwn) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSecondaryContainer).copy(alpha = 0.6f)
                                        )
                                        if (isOwn) {
                                            Spacer(modifier = Modifier.width(4.dp))
                                            Text(
                                                text = when (msg.deliveryState) {
                                                    "read" -> "✓✓"
                                                    "delivered" -> "✓✓"
                                                    else -> "✓"
                                                },
                                                style = MaterialTheme.typography.labelSmall,
                                                color = if (msg.deliveryState == "read") Color(0xFF0078D4) else (if (isOwn) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSecondaryContainer).copy(alpha = 0.6f)
                                            )
                                        }
                                    }

                                    if (msg.reactions.isNotEmpty()) {
                                        Spacer(modifier = Modifier.height(6.dp))
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = if (isOwn) Arrangement.End else Arrangement.Start,
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            msg.reactions.map { it.substringAfter("-") }.distinct().forEach { emoji ->
                                                Surface(
                                                    shape = MaterialTheme.shapes.small,
                                                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.8f),
                                                    border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
                                                    modifier = Modifier.padding(horizontal = 2.dp)
                                                ) {
                                                    Text(
                                                        text = emoji,
                                                        style = MaterialTheme.typography.bodySmall,
                                                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                                                    )
                                                }
                                            }
                                        }
                                    }

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
                Column {
                    typingPreview?.let { previewText ->
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))
                                .padding(horizontal = 16.dp, vertical = 6.dp)
                        ) {
                            Text(
                                text = "Peer is typing: $previewText...",
                                style = MaterialTheme.typography.bodySmall,
                                fontStyle = FontStyle.Italic,
                                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                            )
                        }
                    }
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        OutlinedTextField(
                            value = messageText,
                            onValueChange = {
                                messageText = it
                                chatManager.sendTypingDraft(it)
                            },
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
                                    chatManager.sendTypingDraft("")
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

    if (showReactionPickerForMsg != null) {
        val targetMsg = showReactionPickerForMsg!!
        val isOwn = targetMsg.sender == "You"
        var isEditingMode by remember { mutableStateOf(false) }
        var editText by remember { mutableStateOf(targetMsg.text) }

        AlertDialog(
            onDismissRequest = { showReactionPickerForMsg = null },
            title = { Text(if (isEditingMode) "Edit Message" else "Message Options") },
            text = {
                Column {
                    if (!isEditingMode) {
                        Text("Select Reaction:", style = MaterialTheme.typography.titleSmall)
                        Spacer(modifier = Modifier.height(8.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(8.dp),
                            horizontalArrangement = Arrangement.SpaceEvenly
                        ) {
                            val emojis = listOf("👍", "❤️", "😂", "😮", "😢", "🙏")
                            emojis.forEach { emoji ->
                                Text(
                                    text = emoji,
                                    fontSize = 28.sp,
                                    modifier = Modifier
                                        .clickable {
                                            chatManager.sendReaction(targetMsg.timestamp, emoji)
                                            showReactionPickerForMsg = null
                                        }
                                        .padding(4.dp)
                                )
                            }
                        }
                        if (isOwn && !targetMsg.isFile) {
                            Spacer(modifier = Modifier.height(16.dp))
                            Divider()
                            Spacer(modifier = Modifier.height(8.dp))
                            Button(
                                onClick = { isEditingMode = true },
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Text("Edit Message")
                            }
                            Spacer(modifier = Modifier.height(8.dp))
                            Button(
                                onClick = {
                                    chatManager.sendDeleteMessage(targetMsg.timestamp)
                                    showReactionPickerForMsg = null
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Text("Delete Message")
                            }
                        }
                    } else {
                        OutlinedTextField(
                            value = editText,
                            onValueChange = { editText = it },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true
                        )
                    }
                }
            },
            confirmButton = {
                if (isEditingMode) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.End
                    ) {
                        TextButton(onClick = { isEditingMode = false }) {
                            Text("Cancel")
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                        Button(
                            onClick = {
                                chatManager.sendEditMessage(targetMsg.timestamp, editText)
                                showReactionPickerForMsg = null
                            },
                            enabled = editText.isNotBlank() && editText != targetMsg.text
                        ) {
                            Text("Save")
                        }
                    }
                }
            }
        )
    }
}
