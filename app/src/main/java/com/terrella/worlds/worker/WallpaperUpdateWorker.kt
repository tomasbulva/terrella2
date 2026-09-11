package com.terrella.worlds.worker

import android.content.Context
import android.content.pm.ServiceInfo
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.terrella.worlds.R
import com.terrella.worlds.data.LocationsRepository
import com.terrella.worlds.data.SettingsRepository
import com.terrella.worlds.data.telemetry.Telemetry
import com.terrella.worlds.data.weather.Condition
import com.terrella.worlds.data.weather.WeatherProviders
import com.terrella.worlds.notification.NotificationHelper
import com.terrella.worlds.util.QuietTimeUtils
import com.terrella.worlds.wallpaper.WallpaperHelper
import kotlinx.coroutines.flow.first
import java.util.Calendar
import java.util.concurrent.TimeUnit

/**
 * Periodic wallpaper refresh: fetch weather for the selected location,
 * pick the matching bundled diorama (night/day, storm mood), apply with
 * screen-fit, update the status notification. Skips during Quiet Time.
 */
class WallpaperUpdateWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val settingsRepo = SettingsRepository.get(applicationContext)
        val locationsRepo = LocationsRepository.get(applicationContext)
        val settings = settingsRepo.current()

        if (settings.wallpaperMode != "static") return Result.success() // video loops on its own

        if (settings.quietEnabled) {
            val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
            if (!QuietTimeUtils.isInActiveWindow(hour, settings.quietStartHour, settings.quietEndHour)) {
                Log.i(TAG, "Quiet time active — skipping update")
                return Result.success()
            }
        }

        val location = locationsRepo.selectedLocation.first()
            ?: return Result.success().also { Log.i(TAG, "No selected location — skipping") }

        val provider = WeatherProviders.byId(settings.weatherProviderId)
        val snapshot = runCatching {
            provider.current(location.latitude, location.longitude, settings.owmApiKey.ifBlank { null })
        }.getOrElse {
            Log.w(TAG, "Weather fetch failed: ${it.message}")
            return if (runAttemptCount < 3) Result.retry() else Result.failure()
        }

        val asset = pickAsset(snapshot.isDay, snapshot.condition)
        val applied = WallpaperHelper.decodeAndApply(applicationContext, asset)

        NotificationHelper.showStatus(
            context = applicationContext,
            locationName = "${location.name}, ${location.country}".trim(' ', ','),
            condition = snapshot.condition,
            isDay = snapshot.isDay,
            tempC = snapshot.tempC,
            useMetric = settings.useMetric,
            latitude = location.latitude,
            longitude = location.longitude,
            locationTimezone = location.timezone.ifBlank { null },
            quietTimeEnabled = settings.quietEnabled,
            quietStartHour = settings.quietStartHour,
            quietEndHour = settings.quietEndHour,
        )

        Telemetry.event(
            "wallpaper_refreshed",
            mapOf(
                "asset" to asset,
                "condition" to snapshot.condition.name,
                "provider" to provider.id,
                "ok" to applied.isSuccess.toString(),
            ),
        )
        return Result.success()
    }

    private fun pickAsset(isDay: Boolean, condition: Condition): String = when {
        !isDay -> "diorama_night.jpg"
        condition == Condition.THUNDER || condition == Condition.HEAVY_RAIN -> "diorama_night.jpg"
        condition == Condition.CLEAR -> "diorama_day.jpg"
        else -> "diorama_day.jpg"
    }

    companion object {
        private const val TAG = "WallpaperUpdateWorker"
        const val WORK_NAME = "wallpaper-update"

        /** Re( schedule) periodic wallpaper updates at the user's chosen interval. */
        fun schedule(context: Context, refreshHours: Int) {
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.UPDATE,
                PeriodicWorkRequestBuilder<WallpaperUpdateWorker>(refreshHours.toLong().coerceAtLeast(1), TimeUnit.HOURS)
                    .build(),
            )
        }
    }
}
