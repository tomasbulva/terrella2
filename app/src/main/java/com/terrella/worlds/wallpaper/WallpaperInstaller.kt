package com.terrella.worlds.wallpaper

import android.app.WallpaperManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever

/** Wallpaper installer helpers that apply directly in the background or launch the live wallpaper picker. */
object WallpaperInstaller {

    sealed class Result {
        data object Ok : Result()
        data class Error(val message: String) : Result()
    }

    /** Directly applies wallpaper to home and lock screen with display-fit cropping. */
    suspend fun setStatic(context: Context, assetName: String): Result = runCatching {
        WallpaperHelper.decodeAndApply(context, assetName).getOrThrow()
        Result.Ok
    }.getOrElse { Result.Error(it.message ?: "failed to set wallpaper") }

    /** Applies a static image to the LOCK screen only, fully in background. */
    fun setLockScreenStatic(context: Context, bitmap: Bitmap): Result = runCatching {
        WallpaperManager.getInstance(context).setBitmap(bitmap, null, true, WallpaperManager.FLAG_LOCK)
        Result.Ok
    }.getOrElse { Result.Error(it.message ?: "failed to set lock screen wallpaper") }

    /** Applies a static image to arbitrary screen flags, fully in background. */
    fun setStaticBitmap(
        context: Context,
        bitmap: Bitmap,
        which: Int = WallpaperManager.FLAG_SYSTEM or WallpaperManager.FLAG_LOCK,
    ): Result = runCatching {
        WallpaperManager.getInstance(context).setBitmap(bitmap, null, true, which)
        Result.Ok
    }.getOrElse { Result.Error(it.message ?: "failed to set wallpaper") }

    /** Grabs a frame from a video file — used as the lock-screen still for live wallpapers. */
    fun captureVideoFrame(videoPath: String, atMs: Long = 0): Bitmap? = runCatching {
        MediaMetadataRetriever().use { retriever ->
            retriever.setDataSource(videoPath)
            retriever.getFrameAtTime(atMs * 1000, MediaMetadataRetriever.OPTION_CLOSEST_SYNC)
        }
    }.getOrNull()

    /** Launches the system Live Wallpaper preview picker for VideoWallpaperService. */
    fun launchLiveWallpaperPicker(context: Context): Result = runCatching {
        val intent = Intent(WallpaperManager.ACTION_CHANGE_LIVE_WALLPAPER).apply {
            putExtra(
                WallpaperManager.EXTRA_LIVE_WALLPAPER_COMPONENT,
                ComponentName(context, VideoWallpaperService::class.java)
            )
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
        Result.Ok
    }.getOrElse { Result.Error(it.message ?: "failed to launch live wallpaper picker") }

    /** Clears wallpaper. */
    fun clear(context: Context): Result = runCatching {
        WallpaperManager.getInstance(context).clear()
        Result.Ok
    }.getOrElse { Result.Error(it.message ?: "failed to clear wallpaper") }

    /** True when the system's current home-screen live wallpaper is our VideoWallpaperService. */
    fun isOurLiveWallpaperActive(context: Context): Boolean = runCatching {
        val info = WallpaperManager.getInstance(context).getWallpaperInfo() ?: return false
        info.serviceInfo.packageName == context.packageName &&
            info.serviceInfo.name == VideoWallpaperService::class.java.name
    }.getOrDefault(false)
}
