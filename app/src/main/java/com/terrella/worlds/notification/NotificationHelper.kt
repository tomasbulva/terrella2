package com.terrella.worlds.notification

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import com.terrella.worlds.MainActivity
import com.terrella.worlds.R

object NotificationHelper {
    private const val CHANNEL_STATUS = "terrella_status"
    const val STATUS_NOTIFICATION_ID = 1001

    fun ensureChannel(context: Context) {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_STATUS,
                "World status",
                NotificationManager.IMPORTANCE_LOW,
            ).apply { description = "Current weather in your Terrella world" }
        )
    }

    /** Persistent status notification: location name + weather summary, opens the app. */
    fun showStatus(
        context: Context,
        locationName: String,
        summary: String,
    ) {
        ensureChannel(context)
        val intent = Intent(context, MainActivity::class.java)
        val pending = PendingIntent.getActivity(
            context, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(context, CHANNEL_STATUS)
            .setSmallIcon(R.mipmap.terrella_icon)
            .setContentTitle(locationName.ifBlank { "Terrella" })
            .setContentText(summary)
            .setOngoing(true)
            .setContentIntent(pending)
            .build()
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(STATUS_NOTIFICATION_ID, notification)
    }
}
