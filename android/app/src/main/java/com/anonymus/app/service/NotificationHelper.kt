package com.anonymus.app.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.anonymus.app.MainActivity

object NotificationHelper {
    const val CHANNEL_PUSH_SERVICE = "anonymus_push_service"
    const val CHANNEL_MESSAGES = "anonymus_messages"
    const val SERVICE_NOTIFICATION_ID = 1001
    const val MESSAGE_NOTIFICATION_ID = 1002

    fun createChannels(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

            // Low importance status channel for the persistent foreground service
            val serviceChannel = NotificationChannel(
                CHANNEL_PUSH_SERVICE,
                "Background Connection Status",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Shows status of background message delivery service"
                setShowBadge(false)
            }
            manager.createNotificationChannel(serviceChannel)

            // High importance channel for incoming message alerts
            val messagesChannel = NotificationChannel(
                CHANNEL_MESSAGES,
                "Incoming Messages",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Alerts you when a new message is received securely"
                enableVibration(true)
                setShowBadge(true)
            }
            manager.createNotificationChannel(messagesChannel)
        }
    }

    fun buildServiceNotification(context: Context): Notification {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        val pendingIntentFlags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }
        val pendingIntent = PendingIntent.getActivity(context, 0, intent, pendingIntentFlags)

        return NotificationCompat.Builder(context, CHANNEL_PUSH_SERVICE)
            .setContentTitle("AnonyMus Secure Service")
            .setContentText("Listening for incoming messages securely...")
            .setSmallIcon(android.R.drawable.ic_menu_share) // fallback drawable, system icon
            .setOngoing(true)
            .setContentIntent(pendingIntent)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()
    }

    fun postMessageNotification(context: Context, sender: String, text: String, isPrivateMode: Boolean) {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        val pendingIntentFlags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }
        val pendingIntent = PendingIntent.getActivity(context, 0, intent, pendingIntentFlags)

        val title = if (isPrivateMode) "New Message" else "New message from $sender"
        val body = if (isPrivateMode) "Open AnonyMus to read your message" else text

        val notification = NotificationCompat.Builder(context, CHANNEL_MESSAGES)
            .setContentTitle(title)
            .setContentText(body)
            .setSmallIcon(android.R.drawable.ic_dialog_email) // system icon
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .build()

        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(MESSAGE_NOTIFICATION_ID, notification)
    }
}
