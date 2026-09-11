package com.terrella.worlds.wallpaper

import android.media.MediaPlayer
import android.service.wallpaper.WallpaperService
import android.view.SurfaceHolder
import com.terrella.worlds.R

/**
 * Looping-video live wallpaper. Renders the bundled diorama clip on the
 * wallpaper surface; pauses completely when the wallpaper is not visible
 * (battery discipline: zero work while screen is off).
 */
class VideoWallpaperService : WallpaperService() {

    override fun onCreateEngine(): Engine = VideoEngine()

    private inner class VideoEngine : Engine() {

        private var player: MediaPlayer? = null
        private var engineVisible = false

        override fun onVisibilityChanged(visible: Boolean) {
            engineVisible = visible
            if (visible) startPlayer() else stopPlayer()
        }

        override fun onSurfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
            super.onSurfaceChanged(holder, format, width, height)
            if (engineVisible) startPlayer()
        }

        override fun onDestroy() {
            stopPlayer()
        }

        private fun startPlayer() {
            val surface = surfaceHolder.surface ?: return
            if (!surface.isValid || player != null) return
            runCatching {
                MediaPlayer.create(applicationContext, R.raw.diorama_night)?.apply {
                    isLooping = true
                    setSurface(surface)
                    start()
                    player = this
                }
            }.onFailure { player = null }
        }

        private fun stopPlayer() {
            runCatching { player?.release() }
            player = null
        }
    }
}
