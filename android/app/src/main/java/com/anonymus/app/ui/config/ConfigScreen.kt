package com.anonymus.app.ui.config

import android.content.Intent
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.anonymus.app.LocalChatManager
import com.anonymus.app.data.NsdHelper
import com.anonymus.app.data.PreferencesHelper
import java.util.concurrent.TimeUnit

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConfigScreen(onConfigSaved: () -> Unit) {
    val context = LocalContext.current
    val prefs = remember { PreferencesHelper(context) }
    val chatManager = LocalChatManager.current

    var host by remember { mutableStateOf(prefs.host ?: "10.0.2.2") }
    var port by remember { mutableStateOf(prefs.port.toString()) }
    var trustSelfSigned by remember { mutableStateOf(prefs.trustSelfSigned) }
    var biometricLock by remember { mutableStateOf(prefs.biometricLock) }
    var pushEnabled by remember { mutableStateOf(prefs.pushEnabled) }
    var pushPrivateMode by remember { mutableStateOf(prefs.pushPrivateMode) }
    var isScanning by remember { mutableStateOf(false) }
    var hasFingerprint by remember(host) { mutableStateOf(prefs.hasFingerprint(host)) }
    var validationError by remember { mutableStateOf<String?>(null) }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            pushEnabled = true
        } else {
            pushEnabled = false
        }
    }

    val nsdHelper = remember { 
        NsdHelper(context) { discoveredIp ->
            host = discoveredIp
            isScanning = false
        }
    }

    fun isValidServerConfig(host: String, port: String): Boolean {
        val portNum = port.toIntOrNull() ?: return false
        if (portNum < 1 || portNum > 65535) return false
        if (host.isBlank()) return false
        if (host.contains("..") || host.contains("\n") || host.contains("\r")) return false
        return host.matches(Regex("^[a-zA-Z0-9._-]+$"))
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Server Configuration") },
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
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            if (validationError != null) {
                Text(validationError!!, color = MaterialTheme.colorScheme.error)
                Spacer(modifier = Modifier.height(8.dp))
            }

            OutlinedTextField(
                value = host,
                onValueChange = { 
                    host = it
                    validationError = null
                },
                label = { Text("Server Host / IP") },
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(modifier = Modifier.height(8.dp))
            OutlinedTextField(
                value = port,
                onValueChange = { 
                    port = it
                    validationError = null
                },
                label = { Text("Port") },
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(modifier = Modifier.height(16.dp))
            
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth()
            ) {
                Checkbox(
                    checked = trustSelfSigned,
                    onCheckedChange = { trustSelfSigned = it }
                )
                Text("Trust Self-Signed Certificates")
            }

            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth()
            ) {
                Checkbox(
                    checked = biometricLock,
                    onCheckedChange = { biometricLock = it }
                )
                Text("Enable Biometric App Lock")
            }

            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth()
            ) {
                Checkbox(
                    checked = pushEnabled,
                    onCheckedChange = { checked ->
                        if (checked) {
                            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                                permissionLauncher.launch(android.Manifest.permission.POST_NOTIFICATIONS)
                            } else {
                                pushEnabled = true
                            }
                        } else {
                            pushEnabled = false
                        }
                    }
                )
                Text("Enable Background Notifications")
            }

            if (pushEnabled) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Checkbox(
                        checked = pushPrivateMode,
                        onCheckedChange = { pushPrivateMode = it }
                    )
                    Text("Hide Notification Details (Private Mode)")
                }
            }

            if (hasFingerprint) {
                Spacer(modifier = Modifier.height(12.dp))
                val fingerprint = prefs.serverCertFingerprint
                if (fingerprint != null) {
                    Text(
                        text = "Pinned Certificate Hash (TOFU):\n$fingerprint",
                        style = MaterialTheme.typography.bodySmall,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )
                }
                Button(
                    onClick = {
                        prefs.clearFingerprint(host)
                        prefs.serverCertFingerprint = null
                        hasFingerprint = false
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("Clear Pinned Certificate Fingerprint")
                }
            }

            Spacer(modifier = Modifier.height(24.dp))
            
            if (isScanning) {
                CircularProgressIndicator()
                Text("Scanning local network for AnonyMus relay...")
            } else {
                Button(
                    onClick = { 
                        isScanning = true
                        nsdHelper.discoverServices()
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary)
                ) {
                    Text("Auto-Detect Local Server (mDNS)")
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            Button(
                onClick = {
                    if (!isValidServerConfig(host, port)) {
                        validationError = "Invalid server host, IP address, or port format."
                        return@Button
                    }
                    
                    prefs.host = host
                    prefs.port = port.toIntOrNull() ?: 5000
                    prefs.trustSelfSigned = trustSelfSigned
                    prefs.biometricLock = biometricLock
                    prefs.pushEnabled = pushEnabled
                    prefs.pushPrivateMode = pushPrivateMode

                    // Start/Stop Push Service and Schedule Keep-Alive
                    val serviceIntent = Intent(context, com.anonymus.app.service.PushService::class.java)
                    if (pushEnabled) {
                        serviceIntent.action = com.anonymus.app.service.PushService.ACTION_START
                        try {
                            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                                context.startForegroundService(serviceIntent)
                            } else {
                                context.startService(serviceIntent)
                            }
                        } catch (e: Exception) {
                            android.util.Log.e("ConfigScreen", "Failed to start foreground service: ${e.message}")
                        }

                        val workRequest = androidx.work.PeriodicWorkRequestBuilder<com.anonymus.app.service.PushWorker>(
                            30, TimeUnit.MINUTES
                        ).build()
                        androidx.work.WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                            "PushServiceKeepAlive",
                            androidx.work.ExistingPeriodicWorkPolicy.UPDATE,
                            workRequest
                        )
                    } else {
                        serviceIntent.action = com.anonymus.app.service.PushService.ACTION_STOP
                        context.startService(serviceIntent)
                        androidx.work.WorkManager.getInstance(context).cancelUniqueWork("PushServiceKeepAlive")
                    }

                    // Auto-connect once config is saved
                    chatManager.connect()
                    onConfigSaved()
                },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Save and Connect")
            }
        }
    }
}
