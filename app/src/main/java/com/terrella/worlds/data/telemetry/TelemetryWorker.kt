package com.terrella.worlds.data.telemetry

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

class TelemetryWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        Telemetry.flush()
        return Result.success()
    }

    companion object {
        fun schedule(context: Context) {
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                "telemetry-flush",
                ExistingPeriodicWorkPolicy.KEEP,
                PeriodicWorkRequestBuilder<TelemetryWorker>(6, TimeUnit.HOURS).build(),
            )
        }
    }
}
