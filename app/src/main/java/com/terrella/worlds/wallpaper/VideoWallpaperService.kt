package com.terrella.worlds.wallpaper

import android.media.MediaPlayer
import android.os.Handler
import android.os.Looper
import android.service.wallpaper.WallpaperService
import android.view.SurfaceHolder
import com.terrella.worlds.R
import com.terrella.worlds.data.LocationsRepository
import com.terrella.worlds.data.SettingsRepository
import com.terrella.worlds.util.SunriseSunsetCalculator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.util.Calendar
import java.util.TimeZone

/**
 * Live wallpaper engine. Renders a looping diorama video clip chosen from the
 * active location's real solar day/night state (NOAA sunrise/sunset math).
 *
 * Battery discipline: the player runs only while the wallpaper is visible,
 * and the clip choice is re-evaluated hourly so day/night transitions land
 * without any GPU work while the screen is off.
 */
class VideoWallpaperService : WallpaperService() {

    override fun onCreateEngine(): Engine = VideoEngine()

    private inner class VideoEngine : Engine() {

        private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        private val handler = Handler(Looper.getMainLooper())

        private var player: MediaPlayer? = null
        private var engineVisible = false
        private var currentClipRes = 0

        private val reevaluator = object : Runnable {
            override fun run() {
                evaluateAndMaybeSwapClip()
                handler.postDelayed(this, CLIP_REEVALUATE_MS)
            }
        }

        override fun onVisibilityChanged(visible: Boolean) {
            engineVisible = visible
            if (visible) {
                evaluateAndMaybeSwapClip()
                handler.postDelayed(reevaluator, CLIP_REEVALUATE_MS)
            } else {
                handler.removeCallbacks(reevaluator)
                stopPlayer()
            }
        }

        override fun onSurfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
            super.onSurfaceChanged(holder, format, width, height)
            if (engineVisible) evaluateAndMaybeSwapClip()
        }

        override fun onSurfaceDestroyed(holder: SurfaceHolder) {
            super.onSurfaceDestroyed(holder)
            stopPlayer()
        }

        override fun onDestroy() {
            handler.removeCallbacks(reevaluator)
            stopPlayer()
            scope.cancel()
        }

        /**
         * Resolves the active location, computes whether it is currently solar
         * day there, and picks the matching raw clip. Falls back to the night
         * clip when a day clip isn't bundled yet (res/raw/diorama_day.mp4).
         */
        private fun evaluateAndMaybeSwapClip() {
            scope.launch {
                val desiredRes = runCatching { resolveClipRes() }.getOrDefault(nightClipRes())
                // Player surface ops must stay on the main thread
                handler.post { maybeStartPlayer(desiredRes) }
            }
        }

        private suspend fun resolveClipRes(): Int {
            val context = applicationContext
            val settings = SettingsRepository.get(context).current()
            if (settings.wallpaperType != "live") return nightClipRes()

            val location = LocationsRepository.get(context).selectedLocation.first()
                ?: return nightClipRes()

            val isDay = isSolarDay(location.latitude, location.longitude, location.timezone)
            return if (isDay) dayClipRes() else nightClipRes()
        }

        private fun isSolarDay(lat: Double, lon: Double, timezoneId: String?): Boolean {
            val tz = timezoneId?.takeIf { it.isNotBlank() }
                ?.let { runCatching { TimeZone.getTimeZone(it) }.getOrNull() }
                ?: TimeZone.getDefault()
            val cal = Calendar.getInstance(tz)
            val dayOfYear = cal.get(Calendar.DAY_OF_YEAR)
            val minutes = cal.get(Calendar.HOUR_OF_DAY) * 60 + cal.get(Calendar.MINUTE)
            val offsetMinutes = tz.getOffset(cal.timeInMillis) / 60000
            val (sunriseMin, sunsetMin) = SunriseSunsetCalculator.compute(lat, lon, dayOfYear, offsetMinutes)
            return minutes in sunriseMin..sunsetMin
        }

        /** Dynamic lookup: a bundled diorama_day.mp4 is used when present, night is the fallback. */
        private fun dayClipRes(): Int {
            val id = resources.getIdentifier("diorama_day", "raw", packageName)
            return if (id != 0) id else nightClipRes()
        }

        private fun nightClipRes(): Int =
            resources.getIdentifier("diorama_night", "raw", packageName)
                .takeIf { it != 0 }
                ?: R.raw.diorama_night

        private fun maybeStartPlayer(desiredRes: Int) {
            val surface = surfaceHolder.surface ?: return
            if (!surface.isValid || !engineVisible) return

            if (player != null) {
                if (currentClipRes == desiredRes) return // already playing the right clip
                stopPlayer()
            }

            runCatching {
                MediaPlayer.create(applicationContext, desiredRes)?.apply {
                    isLooping = true
                    setSurface(surface)
                    start()
                    player = this
                    currentClipRes = desiredRes
                }
            }.onFailure { player = null }
        }

        private fun stopPlayer() {
            runCatching { player?.release() }
            player = null
            currentClipRes = 0
        }
    }

    private companion object {
        /** Re-check solar state hourly so day/night transitions swap without wasted work. */
        const val CLIP_REEVALUATE_MS = 60 * 60 * 1000L
    }
}
