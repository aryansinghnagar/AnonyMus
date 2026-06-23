package com.anonymus.app.ui.auth

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.anonymus.app.data.ChatManager
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AuthScreen(onLoginSuccess: () -> Unit) {
    var isRegister by remember { mutableStateOf(false) }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var isLoading by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    // Auto-login check
    LaunchedEffect(Unit) {
        if (ChatManager.isLoggedIn()) {
            onLoginSuccess()
        }
    }

    Scaffold(
        topBar = { TopAppBar(title = { Text(if (isRegister) "Register" else "Login") }) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            if (error != null) {
                Text(text = error!!, color = MaterialTheme.colorScheme.error)
                Spacer(modifier = Modifier.height(8.dp))
            }

            OutlinedTextField(
                value = username,
                onValueChange = { username = it },
                label = { Text("Username") },
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(modifier = Modifier.height(16.dp))
            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                label = { Text("Password") },
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(modifier = Modifier.height(24.dp))

            Button(
                onClick = {
                    isLoading = true
                    error = null
                    scope.launch {
                        if (isRegister) {
                            val (success, msg) = ChatManager.register(username, password)
                            isLoading = false
                            if (success) {
                                isRegister = false // Switch to login
                                error = "Registration successful. Please log in."
                            } else {
                                error = msg
                            }
                        } else {
                            val (success, msg) = ChatManager.login(username, password)
                            isLoading = false
                            if (success) {
                                onLoginSuccess()
                            } else {
                                error = msg
                            }
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = username.isNotBlank() && password.isNotBlank() && !isLoading
            ) {
                if (isLoading) {
                    CircularProgressIndicator(color = MaterialTheme.colorScheme.onPrimary, modifier = Modifier.size(24.dp))
                } else {
                    Text(if (isRegister) "Register" else "Login")
                }
            }
            Spacer(modifier = Modifier.height(16.dp))
            TextButton(onClick = { 
                isRegister = !isRegister
                error = null
            }) {
                Text(if (isRegister) "Already have an account? Login" else "Don't have an account? Register")
            }
        }
    }
}
