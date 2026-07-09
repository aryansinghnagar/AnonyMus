package com.anonymus.app.ui.setup

import android.graphics.Bitmap
import android.graphics.Color
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.text.selection.SelectionContainer
import com.anonymus.app.BuildConfig
import com.anonymus.app.LocalChatManager
import com.anonymus.app.data.ConnectionStatus
import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter

@Composable
fun SetupScreen(onNavigateToChat: () -> Unit) {
    val chatManager = LocalChatManager.current
    val connectionStatus by chatManager.connectionStatus.collectAsState()
    val isSessionActive by chatManager.isSessionActive.collectAsState()
    val context = LocalContext.current
    var pastedLink by remember { mutableStateOf("") }
    var pasteError by remember { mutableStateOf<String?>(null) }
    var isConnecting by remember { mutableStateOf(false) }
    
    LaunchedEffect(isSessionActive) {
        if (isSessionActive) {
            onNavigateToChat()
        }
    }

    LaunchedEffect(connectionStatus) {
        if (connectionStatus != ConnectionStatus.CONNECTED) {
            isConnecting = false
        }
    }

    Scaffold(
        topBar = {
            @OptIn(ExperimentalMaterial3Api::class)
            TopAppBar(
                title = { Text("Start Session") },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(24.dp)
                .verticalScroll(rememberScrollState()),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            if (connectionStatus != ConnectionStatus.CONNECTED) {
                CircularProgressIndicator()
                Spacer(modifier = Modifier.height(16.dp))
                Text("Connecting to relay server...")
                return@Column
            }

            if (chatManager.myQueueId == null || chatManager.myPublicKeyExported == null) {
                CircularProgressIndicator()
                Spacer(modifier = Modifier.height(16.dp))
                Text("Generating keys...")
                return@Column
            }

            val inviteUrl = "${BuildConfig.URL_SCHEME}://${BuildConfig.URL_HOST_JOIN}?q=${chatManager.myQueueId}&k=${android.net.Uri.encode(chatManager.myPublicKeyExported)}"
            
            Text("Your secure invite link:", style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(8.dp))
            SelectionContainer {
                Text(
                    text = inviteUrl,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier
                        .background(MaterialTheme.colorScheme.surfaceVariant)
                        .padding(8.dp),
                    textAlign = TextAlign.Center
                )
            }
            
            Spacer(modifier = Modifier.height(8.dp))
            Button(
                onClick = {
                    val clipboard = context.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                    clipboard.setPrimaryClip(android.content.ClipData.newPlainText("Invite Link", inviteUrl))
                    android.widget.Toast.makeText(context, "Link copied!", android.widget.Toast.LENGTH_SHORT).show()
                },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Copy Invite Link")
            }
            
            Spacer(modifier = Modifier.height(16.dp))
            
            // Generate QR Code
            val qrBitmap = generateQrCode(inviteUrl)
            if (qrBitmap != null) {
                Image(
                    bitmap = qrBitmap.asImageBitmap(),
                    contentDescription = "QR Code containing invite link for secure chat connection",
                    modifier = Modifier.size(200.dp)
                )
            }
            
            Spacer(modifier = Modifier.height(16.dp))
            Text("Scan or share this link to start a chat.", style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center)
            Text("Waiting for peer to connect...", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)

            Spacer(modifier = Modifier.height(24.dp))
            HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
            Spacer(modifier = Modifier.height(8.dp))

            Text("Or Enter Invite Link", style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(8.dp))

            OutlinedTextField(
                value = pastedLink,
                onValueChange = {
                    pastedLink = it
                    pasteError = null
                },
                label = { Text("Paste Peer's Invite Link") },
                placeholder = { Text("${BuildConfig.URL_SCHEME}://${BuildConfig.URL_HOST_JOIN}?q=... or https://...") },
                modifier = Modifier.fillMaxWidth(),
                isError = pasteError != null,
                enabled = !isConnecting,
                supportingText = {
                    if (pasteError != null) {
                        Text(pasteError!!, color = MaterialTheme.colorScheme.error)
                    }
                }
            )
            Spacer(modifier = Modifier.height(8.dp))
            Button(
                onClick = {
                    isConnecting = true
                    val parsed = parseInviteLink(pastedLink)
                    if (parsed != null) {
                        chatManager.acceptInvite(parsed.first, parsed.second)
                    } else {
                        pasteError = "Invalid invite link format."
                        isConnecting = false
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = pastedLink.isNotBlank() && !isConnecting
            ) {
                if (isConnecting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(24.dp),
                        color = MaterialTheme.colorScheme.onPrimary
                    )
                } else {
                    Text("Connect to Peer")
                }
            }
        }
    }
}

private fun parseInviteLink(url: String): Pair<String, String>? {
    return try {
        val normalized = url.replace("#q=", "?q=").replace("#", "?")
        val uri = android.net.Uri.parse(normalized)
        val q = uri.getQueryParameter("q")
        val k = uri.getQueryParameter("k")
        if (!q.isNullOrBlank() && !k.isNullOrBlank()) {
            Pair(q, k)
        } else {
            null
        }
    } catch (e: Exception) {
        null
    }
}

private fun generateQrCode(text: String): Bitmap? {
    return try {
        val writer = QRCodeWriter()
        val bitMatrix = writer.encode(text, BarcodeFormat.QR_CODE, 512, 512)
        val width = bitMatrix.width
        val height = bitMatrix.height
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.RGB_565)
        for (x in 0 until width) {
            for (y in 0 until height) {
                bitmap.setPixel(x, y, if (bitMatrix.get(x, y)) Color.BLACK else Color.WHITE)
            }
        }
        bitmap
    } catch (e: Exception) {
        android.util.Log.e("SetupScreen", "Failed to generate QR code")
        null
    }
}
