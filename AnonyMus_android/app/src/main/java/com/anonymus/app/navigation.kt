package com.anonymus.app

import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.anonymus.app.data.ChatManager
import com.anonymus.app.ui.config.ConfigScreen
import com.anonymus.app.ui.setup.SetupScreen
import com.anonymus.app.ui.chat.ChatScreen
import com.anonymus.app.ui.auth.AuthScreen

val LocalChatManager = staticCompositionLocalOf<ChatManager> {
    error("No ChatManager provided")
}

@Composable
fun AppNavigation() {
    val navController = rememberNavController()

    NavHost(navController = navController, startDestination = "config") {
        composable("config") {
            ConfigScreen(onConfigSaved = {
                navController.navigate("auth") {
                    popUpTo("config") { inclusive = true }
                }
            })
        }
        composable("auth") {
            AuthScreen(onLoginSuccess = {
                navController.navigate("setup") {
                    popUpTo("auth") { inclusive = true }
                }
            })
        }
        composable("setup") {
            SetupScreen(onNavigateToChat = {
                navController.navigate("chat") {
                    popUpTo("setup") { inclusive = true }
                }
            })
        }
        composable("chat") {
            ChatScreen()
        }
    }
}
