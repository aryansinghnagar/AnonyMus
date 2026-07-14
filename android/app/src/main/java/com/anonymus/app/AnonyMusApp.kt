package com.anonymus.app

import android.app.Application
import com.anonymus.app.data.ChatManager
import com.anonymus.app.di.appModule
import org.koin.android.ext.android.inject
import org.koin.android.ext.koin.androidContext
import org.koin.core.context.startKoin

class AnonyMusApp : Application() {
    val chatManager: ChatManager by inject()

    override fun onCreate() {
        super.onCreate()
        startKoin {
            androidContext(this@AnonyMusApp)
            modules(appModule)
        }
    }
}
