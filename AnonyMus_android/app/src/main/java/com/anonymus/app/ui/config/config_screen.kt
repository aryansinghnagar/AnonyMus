package com.anonymus.app.ui.config

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.anonymus.app.data.ChatManager
import com.anonymus.app.data.NsdHelper
import com.anonymus.app.data.PreferencesHelper

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConfigScreen(onConfigSaved: () -> Unit) {
    val context = LocalContext.current
    val prefs = remember { PreferencesHelper(context) }

    var host by remember { mutableStateOf(prefs.host ?: "10.0.2.2") }
    var port by remember { mutableStateOf(prefs.port.toString()) }
    var trustSelfSigned by remember { mutableStateOf(prefs.trustSelfSigned) }
    var isScanning by remember { mutableStateOf(false) }
    var hasFingerprint by remember(host) { mutableStateOf(prefs.hasFingerprint(host)) }

    val nsdHelper = remember { 
        NsdHelper(context) { discoveredIp ->
            host = discoveredIp
            isScanning = false
        }
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
                .padding(16.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            OutlinedTextField(
                value = host,
                onValueChange = { host = it },
                label = { Text("Server Host / IP") },
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(modifier = Modifier.height(8.dp))
            OutlinedTextField(
                value = port,
                onValueChange = { port = it },
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

            if (hasFingerprint) {
                Spacer(modifier = Modifier.height(8.dp))
                Button(
                    onClick = {
                        prefs.clearFingerprint(host)
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
                    prefs.host = host
                    prefs.port = port.toIntOrNull() ?: 5000
                    prefs.trustSelfSigned = trustSelfSigned

                    // Auto-connect once config is saved
                    ChatManager.connect()
                    onConfigSaved()
                },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Save and Connect")
            }
        }
    }
}
