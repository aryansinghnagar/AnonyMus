package com.example.privacychat

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.navigation3.runtime.entryProvider
import androidx.navigation3.runtime.rememberNavBackStack
import androidx.navigation3.ui.NavDisplay
import com.example.privacychat.data.ChatManager
import com.example.privacychat.data.PreferencesHelper
import com.example.privacychat.ui.config.ConfigScreen
import com.example.privacychat.ui.auth.AuthScreen
import com.example.privacychat.ui.chat.ChatScreen

@Composable
fun MainNavigation() {
  val context = LocalContext.current
  val prefs = remember { PreferencesHelper(context) }
  
  // Start on Auth screen if server configuration already exists, otherwise show Config screen first.
  val startDestination = if (prefs.isConfigured()) Auth else Config
  val backStack = rememberNavBackStack(startDestination)

  NavDisplay(
    backStack = backStack,
    onBack = { backStack.removeLastOrNull() },
    entryProvider =
      entryProvider {
        entry<Config> {
          ConfigScreen(
            onConfigSaved = { host, port, trustSelfSigned ->
              prefs.host = host
              prefs.port = port
              prefs.trustSelfSigned = trustSelfSigned
              
              // Re-initialize ChatManager OkHttpClient configuration with new settings
              ChatManager.resetClient()
              
              // Clear current stack and add Auth
              backStack.removeLastOrNull()
              backStack.add(Auth)
            }
          )
        }

        entry<Auth> {
          AuthScreen(
            onAuthSuccess = {
              backStack.add(Chat)
            },
            onBackToConfig = {
              backStack.add(Config)
            }
          )
        }

        entry<Chat> {
          ChatScreen(
            onResetConfig = {
              // Reset navigation stack to Config screen
              backStack.removeLastOrNull() // remove Chat
              backStack.removeLastOrNull() // remove Auth
              backStack.add(Config)
            }
          )
        }
      },
  )
}

