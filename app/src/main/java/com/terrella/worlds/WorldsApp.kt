package com.terrella.worlds

import android.app.Application
import com.terrella.worlds.data.telemetry.Telemetry
import com.terrella.worlds.data.telemetry.TelemetryWorker

class WorldsApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Telemetry.init(this)
        TelemetryWorker.schedule(this)
    }
}
