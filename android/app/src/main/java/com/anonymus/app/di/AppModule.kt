package com.anonymus.app.di

import com.anonymus.app.data.ChatManager
import com.anonymus.app.data.CryptoProvider
import com.anonymus.app.data.JniCryptoProvider
import com.anonymus.app.data.PreferencesHelper
import com.anonymus.app.data.db.AppDatabase
import org.koin.android.ext.koin.androidContext
import org.koin.dsl.module

val appModule = module {
    single { PreferencesHelper(androidContext()) }
    single<CryptoProvider> { JniCryptoProvider() }
    single { AppDatabase.getDatabase(androidContext()) }
    single { get<AppDatabase>().messageDao() }
    single { ChatManager(androidContext(), get(), get(), get()) }
}
