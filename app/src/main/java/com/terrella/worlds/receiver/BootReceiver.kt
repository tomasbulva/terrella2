package com.terrella.worlds.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.terrella.worlds.data.SettingsRepository
import com.terrella.worlds.worker.WallpaperUpdateWorker
import kotlinx.coroutines.runBlocking

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        // Settings read on the receiver thread; settings write is rare and local.
        val hours = runBlocking { runCatching { SettingsRepository.get(context).current().refreshHours }.getOrDefault(6) }
        WallpaperUpdateWorker.schedule(context, hours)
    }
}
