package com.anonymus.app.service

import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.anonymus.app.data.PreferencesHelper

class PushWorker(
    private val context: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(context, workerParams) {

    private val TAG = "PushWorker"

    override suspend fun doWork(): Result {
        Log.d(TAG, "WorkManager trigger - verifying background service status")
        val prefs = PreferencesHelper(context)

        if (prefs.pushEnabled && prefs.isConfigured() && prefs.sessionCookie != null) {
            val intent = Intent(context, PushService::class.java).apply {
                action = PushService.ACTION_START
            }
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
                Log.d(TAG, "Successfully started/revived PushService from worker")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start PushService: ${e.message}", e)
                return Result.retry()
            }
        } else {
            Log.d(TAG, "Push is disabled or credentials not set. No actions taken.")
        }

        return Result.success()
    }
}
