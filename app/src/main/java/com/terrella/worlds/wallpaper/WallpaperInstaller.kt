package com.terrella.worlds.wallpaper

import android.app.WallpaperManager
import android.content.Context
import android.graphics.BitmapFactory

/** Static image wallpaper helpers. Video is handled by [VideoWallpaperService]. */
object WallpaperInstaller {

    sealed class Result {
        data object Ok : Result()
        data class Error(val message: String) : Result()
    }

    fun setStatic(context: Context, assetName: String): Result = runCatching {
        val bmp = BitmapFactory.decodeStream(context.assets.open("wallpapers/$assetName"))
        WallpaperManager.getInstance(context).setBitmap(bmp)
        Result.Ok
    }.getOrElse { Result.Error(it.message ?: "failed to set static wallpaper") }

    fun clear(context: Context): Result = runCatching {
        WallpaperManager.getInstance(context).clear()
        Result.Ok
    }.getOrElse { Result.Error(it.message ?: "failed to clear wallpaper") }
}
