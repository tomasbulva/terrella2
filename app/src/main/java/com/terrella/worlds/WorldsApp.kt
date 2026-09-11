package com.terrella.worlds

import android.app.Application
import com.terrella.worlds.data.telemetry.Telemetry
import com.terrella.worlds.data.telemetry.TelemetryWorker

class WorldsApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Telemetry.init(this)
        TelemetryWorker.schedule(this)
        kotlinx.coroutines.runBlocking {
            val hours = runCatching {
                com.terrella.worlds.data.SettingsRepository.get(this@WorldsApp).current().refreshHours
            }.getOrDefault(6)
            com.terrella.worlds.worker.WallpaperUpdateWorker.schedule(this@WorldsApp, hours)
        }
    }
}
