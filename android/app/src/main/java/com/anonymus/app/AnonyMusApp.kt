package com.anonymus.app

import android.app.Application
import com.anonymus.app.data.ChatManager
import com.anonymus.app.data.PreferencesHelper
import com.anonymus.app.data.TinkCryptoProvider

class AnonyMusApp : Application() {
    lateinit var chatManager: ChatManager
        private set

    override fun onCreate() {
        super.onCreate()
        val prefs = PreferencesHelper(this)
        chatManager = ChatManager(this, prefs, TinkCryptoProvider())
    }
}
