package com.example.privacychat.ui.config

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun ConfigScreen(
    onConfigSaved: (host: String, port: Int, trustSelfSigned: Boolean) -> Unit
) {
    var host by remember { mutableStateOf("") }
    var portText by remember { mutableStateOf("5000") }
    var trustSelfSigned by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    // Harmonious curated dark palette with vibrant neon accents
    val backgroundGradient = Brush.verticalGradient(
        colors = listOf(Color(0xFF0F172A), Color(0xFF1E293B)) // Slate 900 to Slate 800
    )
    val accentColor = Color(0xFF10B981) // Emerald Green for Privacy/Security
    val dangerColor = Color(0xFFEF4444) // Soft Coral Red
    val warningColor = Color(0xFFF59E0B) // Amber Yellow

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(backgroundGradient),
        contentAlignment = Alignment.Center
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth(0.9f)
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            // Glowing Logo/Header Section
            Box(
                modifier = Modifier
                    .size(80.dp)
                    .background(Color(0x1A10B981), RoundedCornerShape(24.dp))
                    .border(2.dp, accentColor, RoundedCornerShape(24.dp)),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Default.Lock,
                    contentDescription = "Shield Logo",
                    tint = accentColor,
                    modifier = Modifier.size(40.dp)
                )
            }

            Spacer(modifier = Modifier.height(24.dp))

            Text(
                text = "Anonymouse Configuration",
                fontSize = 26.sp,
                fontWeight = FontWeight.Bold,
                color = Color.White,
                textAlign = TextAlign.Center
            )

            Spacer(modifier = Modifier.height(8.dp))

            Text(
                text = "Setup your local server connection",
                fontSize = 14.sp,
                color = Color(0xFF94A3B8), // Slate 400
                textAlign = TextAlign.Center
            )

            Spacer(modifier = Modifier.height(32.dp))

            // Premium Glassmorphic Card
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, Color(0x33FFFFFF), RoundedCornerShape(24.dp)),
                shape = RoundedCornerShape(24.dp),
                colors = CardDefaults.cardColors(containerColor = Color(0x1F1E293B))
            ) {
                Column(
                    modifier = Modifier.padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    // Server Host field
                    OutlinedTextField(
                        value = host,
                        onValueChange = { 
                            host = it.trim()
                            errorMessage = null
                        },
                        label = { Text("Server Host IP (e.g. 192.168.x.x)", color = Color(0xFF94A3B8)) },
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = accentColor,
                            unfocusedBorderColor = Color(0x33FFFFFF),
                            focusedLabelColor = accentColor,
                            unfocusedLabelColor = Color(0xFF94A3B8),
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White
                        ),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    // Port field
                    OutlinedTextField(
                        value = portText,
                        onValueChange = { 
                            portText = it.trim()
                            errorMessage = null
                        },
                        label = { Text("Port", color = Color(0xFF94A3B8)) },
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = accentColor,
                            unfocusedBorderColor = Color(0x33FFFFFF),
                            focusedLabelColor = accentColor,
                            unfocusedLabelColor = Color(0xFF94A3B8),
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White
                        ),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    // Self-signed toggle
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Checkbox(
                            checked = trustSelfSigned,
                            onCheckedChange = { trustSelfSigned = it },
                            colors = CheckboxDefaults.colors(
                                checkedColor = accentColor,
                                uncheckedColor = Color(0x33FFFFFF)
                            )
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "Trust Self-Signed SSL Certificate",
                            color = Color.White,
                            fontSize = 14.sp
                        )
                    }

                    // Warning details when checkbox enabled
                    AnimatedVisibility(
                        visible = trustSelfSigned,
                        enter = fadeIn(),
                        exit = fadeOut()
                    ) {
                        Column(modifier = Modifier.padding(top = 12.dp)) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .background(Color(0x1AEE9B00), RoundedCornerShape(12.dp))
                                    .border(1.dp, warningColor, RoundedCornerShape(12.dp))
                                    .padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Info,
                                    contentDescription = "Warning",
                                    tint = warningColor,
                                    modifier = Modifier.size(24.dp)
                                )
                                Spacer(modifier = Modifier.width(12.dp))
                                Text(
                                    text = "Security Warning: Bypassing SSL validation is only recommended on trusted private/local networks. Never run this on public Wi-Fi networks.",
                                    color = Color(0xFFFCD34D), // Light yellow
                                    fontSize = 11.sp,
                                    lineHeight = 15.sp,
                                    modifier = Modifier.weight(1f)
                                )
                            }
                        }
                    }

                    // Error Message
                    AnimatedVisibility(
                        visible = errorMessage != null,
                        enter = fadeIn(),
                        exit = fadeOut()
                    ) {
                        errorMessage?.let { msg ->
                            Text(
                                text = msg,
                                color = dangerColor,
                                fontSize = 13.sp,
                                modifier = Modifier.padding(top = 16.dp),
                                textAlign = TextAlign.Center
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(24.dp))

                    // Connect button
                    Button(
                        onClick = {
                            if (host.isBlank()) {
                                errorMessage = "Server Host IP is required"
                                return@Button
                            }
                            val parsedPort = portText.toIntOrNull()
                            if (parsedPort == null || parsedPort !in 1..65535) {
                                errorMessage = "Port must be a valid number between 1 and 65535"
                                return@Button
                            }

                            onConfigSaved(host, parsedPort, trustSelfSigned)
                        },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = accentColor,
                            contentColor = Color.Black
                        ),
                        shape = RoundedCornerShape(16.dp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(56.dp)
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                imageVector = Icons.Default.Settings,
                                contentDescription = "Connect Settings Icon",
                                tint = Color.Black
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = "Save & Continue",
                                fontSize = 16.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }
                }
            }
        }
    }
}
