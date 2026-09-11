package com.terrella.worlds.notification

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.Icon
import android.os.Build
import androidx.annotation.DrawableRes
import com.terrella.worlds.MainActivity
import com.terrella.worlds.R
import com.terrella.worlds.data.weather.Condition
import com.terrella.worlds.util.QuietTimeUtils
import com.terrella.worlds.util.SunriseSunsetCalculator
import java.util.Calendar
import java.util.TimeZone
import kotlin.math.roundToInt

/**
 * T1's progressive notification, ported: a 3-segment day-cycle progress bar
 * (night | day | night) computed from the location's real sunrise/sunset (NOAA
 * solar algorithm), a minute-precision tracker, and quiet-time milestone points.
 * API 36+ renders the segmented style; API 35 falls back to a plain progress bar.
 */
object NotificationHelper {

    const val CHANNEL_ID = "terrella_status"
    const val STATUS_NOTIFICATION_ID = 1001

    // Night segments: deep navy; day segment: warm golden yellow
    private val COLOR_NIGHT = Color.rgb(0x1A, 0x23, 0x7E)
    private val COLOR_DAY = Color.rgb(0xFF, 0xC1, 0x07)

    fun ensureChannel(context: Context) {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Terrella", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Day-cycle progress and wallpaper updates"
                setShowBadge(false)
            }
        )
    }

    fun showStatus(
        context: Context,
        locationName: String,
        condition: Condition,
        isDay: Boolean,
        tempC: Double,
        useMetric: Boolean,
        latitude: Double? = null,
        longitude: Double? = null,
        locationTimezone: String? = null,
        isGenerating: Boolean = false,
        quietTimeEnabled: Boolean = false,
        quietStartHour: Int = 5,
        quietEndHour: Int = 22,
    ) {
        ensureChannel(context)
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(STATUS_NOTIFICATION_ID, build(context, locationName, condition, isDay, tempC, useMetric, latitude, longitude, locationTimezone, isGenerating, quietTimeEnabled, quietStartHour, quietEndHour))
    }

    private fun build(
        context: Context,
        locationName: String,
        condition: Condition,
        isDay: Boolean,
        tempC: Double,
        useMetric: Boolean,
        latitude: Double?,
        longitude: Double?,
        locationTimezone: String?,
        isGenerating: Boolean,
        quietTimeEnabled: Boolean,
        quietStartHour: Int,
        quietEndHour: Int,
    ): Notification {
        val pendingIntent = PendingIntent.getActivity(
            context, 0,
            Intent(context, MainActivity::class.java).apply { flags = Intent.FLAG_ACTIVITY_SINGLE_TOP },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val tz = locationTimezone?.let { runCatching { TimeZone.getTimeZone(it) }.getOrNull() }
        val cal = if (tz != null) Calendar.getInstance(tz) else Calendar.getInstance()
        val currentMinute = cal.get(Calendar.HOUR_OF_DAY) * 60 + cal.get(Calendar.MINUTE)

        val (sunriseMin, sunsetMin) = if (latitude != null && longitude != null) {
            val tzOffsetMin = cal.timeZone.getOffset(cal.timeInMillis) / 60_000
            SunriseSunsetCalculator.compute(
                latitudeDeg = latitude,
                longitudeDeg = longitude,
                dayOfYear = cal.get(Calendar.DAY_OF_YEAR),
                utcOffsetMinutes = tzOffsetMin,
            )
        } else {
            Pair(360, 1080) // fallback: 6 am / 6 pm
        }

        val isDaytime = currentMinute in sunriseMin until sunsetMin
        val tempDisplay = if (useMetric) "${tempC.roundToInt()}°C" else "${(tempC * 9f / 5f + 32f).roundToInt()}°F"
        val contentText = when {
            isGenerating -> "Generating new wallpaper…"
            else -> "${conditionDescription(condition)} · $tempDisplay"
        }

        // 3-segment day cycle in 0–100 space
        val sunriseProgress = (sunriseMin.toFloat() / 1440f * 100).roundToInt().coerceIn(1, 98)
        val sunsetProgress = (sunsetMin.toFloat() / 1440f * 100).roundToInt().coerceIn(sunriseProgress + 1, 99)
        val seg1 = sunriseProgress
        val seg2 = sunsetProgress - sunriseProgress
        val seg3 = 100 - sunsetProgress
        val progressInUnits = (currentMinute.toFloat() / 1440f * 100).roundToInt()

        val milestoneValues = if (quietTimeEnabled) {
            listOf(QuietTimeUtils.milestoneProgress(quietStartHour), QuietTimeUtils.milestoneProgress(quietEndHour))
        } else emptyList()

        val builder = Notification.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.mipmap.terrella_icon)
            .setLargeIcon(Icon.createWithResource(context, weatherIconRes(condition, isDaytime)))
            .setContentTitle(locationName.ifBlank { "Terrella" })
            .setContentText(contentText)
            .setOngoing(true)
            .setContentIntent(pendingIntent)

        if (Build.VERSION.SDK_INT >= 36) {
            val progressStyle = Notification.ProgressStyle()
                .setStyledByProgress(false)
                .setProgress(progressInUnits)
                .setProgressTrackerIcon(Icon.createWithResource(context, R.drawable.ic_notification_tracker))
                .setProgressSegments(
                    listOf(
                        Notification.ProgressStyle.Segment(seg1).setColor(COLOR_NIGHT),
                        Notification.ProgressStyle.Segment(seg2).setColor(COLOR_DAY),
                        Notification.ProgressStyle.Segment(seg3).setColor(COLOR_NIGHT),
                    )
                )
                .also { style ->
                    if (milestoneValues.isNotEmpty()) {
                        style.setProgressPoints(
                            milestoneValues.map { progress ->
                                Notification.ProgressStyle.Point(progress).setColor(Color.WHITE)
                            }
                        )
                    }
                }
            builder.setStyle(progressStyle)
        } else {
            builder.setProgress(100, progressInUnits, false)
        }

        return builder.build()
    }

    fun conditionDescription(condition: Condition): String = when (condition) {
        Condition.CLEAR -> "Clear"
        Condition.PARTLY_CLOUDY -> "Partly cloudy"
        Condition.CLOUDY -> "Overcast"
        Condition.FOG -> "Foggy"
        Condition.DRIZZLE -> "Drizzle"
        Condition.RAIN -> "Rain"
        Condition.HEAVY_RAIN -> "Heavy rain"
        Condition.SNOW -> "Snow"
        Condition.THUNDER -> "Thunderstorm"
    }

    @DrawableRes
    fun weatherIconRes(condition: Condition, isDaytime: Boolean = true): Int = when (condition) {
        Condition.CLEAR -> if (isDaytime) R.drawable.ic_weather_clear else R.drawable.ic_weather_clear_night
        Condition.PARTLY_CLOUDY -> if (isDaytime) R.drawable.ic_weather_partly_cloudy else R.drawable.ic_weather_partly_cloudy_night
        Condition.CLOUDY -> R.drawable.ic_weather_cloudy
        Condition.FOG -> R.drawable.ic_weather_fog
        Condition.DRIZZLE, Condition.RAIN -> R.drawable.ic_weather_rain
        Condition.HEAVY_RAIN -> R.drawable.ic_weather_rain_mix
        Condition.SNOW -> R.drawable.ic_weather_snow
        Condition.THUNDER -> R.drawable.ic_weather_thunder
    }
}
