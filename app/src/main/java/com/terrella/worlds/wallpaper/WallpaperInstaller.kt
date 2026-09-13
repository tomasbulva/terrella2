package com.terrella.worlds.wallpaper

import android.app.WallpaperManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent

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
}
