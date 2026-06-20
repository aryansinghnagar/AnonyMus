package com.example.privacychat.ui.auth

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.privacychat.data.ChatManager

@Composable
fun AuthScreen(
    onAuthSuccess: () -> Unit,
    onBackToConfig: () -> Unit
) {
    var isLoginMode by remember { mutableStateOf(true) }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(false) }
    var infoMessage by remember { mutableStateOf<String?>(null) }
    var infoIsError by remember { mutableStateOf(false) }

    val backgroundGradient = Brush.verticalGradient(
        colors = listOf(Color(0xFF0F172A), Color(0xFF1E293B))
    )
    val accentColor = Color(0xFF10B981) // Emerald Green
    val errorColor = Color(0xFFEF4444)
    val infoColor = Color(0xFF60A5FA) // Blue for info

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(backgroundGradient)
            .padding(16.dp)
    ) {
        // Back Button to configurations
        IconButton(
            onClick = onBackToConfig,
            modifier = Modifier
                .align(Alignment.TopStart)
                .padding(8.dp)
                .background(Color(0x1FFFFFFF), RoundedCornerShape(12.dp))
        ) {
            Icon(
                imageVector = Icons.Default.ArrowBack,
                contentDescription = "Back",
                tint = Color.White
            )
        }

        Column(
            modifier = Modifier
                .fillMaxWidth(0.9f)
                .align(Alignment.Center),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            // Lock icon
            Box(
                modifier = Modifier
                    .size(64.dp)
                    .background(Color(0x1A10B981), RoundedCornerShape(20.dp))
                    .border(2.dp, accentColor, RoundedCornerShape(20.dp)),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Default.Lock,
                    contentDescription = "Auth Logo",
                    tint = accentColor,
                    modifier = Modifier.size(32.dp)
                )
            }

            Spacer(modifier = Modifier.height(24.dp))

            Text(
                text = if (isLoginMode) "Log In" else "Create Account",
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold,
                color = Color.White
            )

            Spacer(modifier = Modifier.height(8.dp))

            Text(
                text = if (isLoginMode) "Connect securely with your credentials" else "Register a new username and password",
                fontSize = 13.sp,
                color = Color(0xFF94A3B8),
                textAlign = TextAlign.Center
            )

            Spacer(modifier = Modifier.height(28.dp))

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
                    // Username Field
                    OutlinedTextField(
                        value = username,
                        onValueChange = {
                            username = it.replace(" ", "")
                            infoMessage = null
                        },
                        label = { Text("Username", color = Color(0xFF94A3B8)) },
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = accentColor,
                            unfocusedBorderColor = Color(0x33FFFFFF),
                            focusedLabelColor = accentColor,
                            unfocusedLabelColor = Color(0xFF94A3B8),
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White
                        ),
                        singleLine = true,
                        enabled = !isLoading,
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    // Password Field
                    OutlinedTextField(
                        value = password,
                        onValueChange = {
                            password = it
                            infoMessage = null
                        },
                        label = { Text("Password", color = Color(0xFF94A3B8)) },
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = accentColor,
                            unfocusedBorderColor = Color(0x33FFFFFF),
                            focusedLabelColor = accentColor,
                            unfocusedLabelColor = Color(0xFF94A3B8),
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White
                        ),
                        singleLine = true,
                        enabled = !isLoading,
                        visualTransformation = PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                        modifier = Modifier.fillMaxWidth()
                    )

                    // Error or Info Message Display
                    AnimatedVisibility(
                        visible = infoMessage != null,
                        enter = fadeIn(),
                        exit = fadeOut()
                    ) {
                        infoMessage?.let { msg ->
                            Text(
                                text = msg,
                                color = if (infoIsError) errorColor else infoColor,
                                fontSize = 13.sp,
                                modifier = Modifier.padding(top = 16.dp),
                                textAlign = TextAlign.Center
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(24.dp))

                    // Submit Button
                    Button(
                        onClick = {
                            if (username.isBlank() || password.isBlank()) {
                                infoIsError = true
                                infoMessage = "Both fields are required"
                                return@Button
                            }

                            isLoading = true
                            infoMessage = null
                            val endpoint = if (isLoginMode) "/login" else "/register"

                            ChatManager.performAuthRequest(endpoint, username, password) { success, msg ->
                                isLoading = false
                                if (success) {
                                    if (isLoginMode) {
                                        onAuthSuccess()
                                    } else {
                                        isLoginMode = true
                                        infoIsError = false
                                        infoMessage = "Registration successful! You can now log in."
                                        password = ""
                                    }
                                } else {
                                    infoIsError = true
                                    infoMessage = msg
                                }
                            }
                        },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = accentColor,
                            contentColor = Color.Black
                        ),
                        shape = RoundedCornerShape(16.dp),
                        enabled = !isLoading,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(56.dp)
                    ) {
                        if (isLoading) {
                            CircularProgressIndicator(
                                color = Color.Black,
                                modifier = Modifier.size(24.dp)
                            )
                        } else {
                            Text(
                                text = if (isLoginMode) "Log In" else "Register",
                                fontSize = 16.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    // Toggle Link
                    Text(
                        text = if (isLoginMode) "No account? Register" else "Already registered? Login",
                        color = accentColor,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        modifier = Modifier
                            .clickable(enabled = !isLoading) {
                                isLoginMode = !isLoginMode
                                infoMessage = null
                                password = ""
                            }
                            .padding(8.dp)
                    )
                }
            }
        }
    }
}
