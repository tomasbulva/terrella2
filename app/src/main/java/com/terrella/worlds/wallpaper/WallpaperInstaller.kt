package com.terrella.worlds.wallpaper

import android.app.WallpaperManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory

/** Static and Live wallpaper installer helpers. */
object WallpaperInstaller {

    sealed class Result {
        data object Ok : Result()
        data class Error(val message: String) : Result()
    }

    /** Sets a static diorama bitmap as system home / lock screen wallpaper. */
    fun setStatic(context: Context, assetName: String): Result = runCatching {
        val bmp = BitmapFactory.decodeStream(context.assets.open("wallpapers/$assetName"))
        WallpaperManager.getInstance(context).setBitmap(bmp)
        Result.Ok
    }.getOrElse { Result.Error(it.message ?: "failed to set static wallpaper") }

    /** Opens Android's native Live Wallpaper preview / chooser targeting Terrella. */
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
    }.getOrElse {
        // Fallback to generic live wallpaper chooser
        runCatching {
            val fallbackIntent = Intent(WallpaperManager.ACTION_LIVE_WALLPAPER_CHOOSER).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(fallbackIntent)
            Result.Ok
        }.getOrElse { Result.Error(it.message ?: "failed to open live wallpaper chooser") }
    }

    /** Clears wallpaper. */
    fun clear(context: Context): Result = runCatching {
        WallpaperManager.getInstance(context).clear()
        Result.Ok
    }.getOrElse { Result.Error(it.message ?: "failed to clear wallpaper") }
}
