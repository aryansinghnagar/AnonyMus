package com.anonymus.app

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.anonymus.app.data.ChatManager
import com.anonymus.app.theme.AnonyMusTheme

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Anti-Forensics Phase 3: Screen Security (Block screenshots & tab previews)
        window.setFlags(
            WindowManager.LayoutParams.FLAG_SECURE,
            WindowManager.LayoutParams.FLAG_SECURE
        )

        ChatManager.initialize(applicationContext)

        // Handle cold start deep link
        handleIntent(intent)

        setContent {
            AnonyMusTheme {
                AppNavigation()
            }
        }
    }

    private val clipboardClearHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private val clipboardClearRunnable = Runnable {
        try {
            val clipboard = getSystemService(android.content.Context.CLIPBOARD_SERVICE) as? android.content.ClipboardManager
            val clipData = clipboard?.primaryClip
            if (clipData != null && clipData.itemCount > 0) {
                val text = clipData.getItemAt(0).text?.toString() ?: ""
                val expectedPrefix = "${BuildConfig.URL_SCHEME}://${BuildConfig.URL_HOST_JOIN}"
                if (text.startsWith(expectedPrefix) && text.contains("q=") && text.contains("k=")) {
                    if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
                        clipboard.clearPrimaryClip()
                    } else {
                        clipboard.setPrimaryClip(android.content.ClipData.newPlainText("", ""))
                    }
                }
            }
        } catch(e: Exception) {}
    }

    override fun onPause() {
        super.onPause()
        // Phase 5: Auto-clear clipboard after 30 seconds in background
        clipboardClearHandler.postDelayed(clipboardClearRunnable, 30000)
    }

    override fun onResume() {
        super.onResume()
        clipboardClearHandler.removeCallbacks(clipboardClearRunnable)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        val action = intent?.action
        val data: Uri? = intent?.data

        if (Intent.ACTION_VIEW == action && data != null) {
            if (data.scheme == BuildConfig.URL_SCHEME && data.host == BuildConfig.URL_HOST_JOIN) {
                val q = data.getQueryParameter("q")
                val k = data.getQueryParameter("k")
                if (q != null && k != null) {
                    ChatManager.connect() // Ensure we are connected
                    ChatManager.acceptInvite(q, k)
                }
            }
        }
    }
}
