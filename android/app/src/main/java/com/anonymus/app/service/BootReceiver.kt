package com.anonymus.app.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import com.anonymus.app.data.PreferencesHelper

class BootReceiver : BroadcastReceiver() {

    private val TAG = "BootReceiver"

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            Log.d(TAG, "Device boot completed - checking if push service should start")
            val prefs = PreferencesHelper(context)

            if (prefs.pushEnabled && prefs.isConfigured() && prefs.sessionCookie != null) {
                val serviceIntent = Intent(context, PushService::class.java).apply {
                    action = PushService.ACTION_START
                }
                try {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        context.startForegroundService(serviceIntent)
                    } else {
                        context.startService(serviceIntent)
                    }
                    Log.d(TAG, "PushService successfully started on boot")
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to start PushService on boot: ${e.message}", e)
                }
            }
        }
    }
}
