package com.terrella.worlds.wallpaper

import android.app.WallpaperManager
import android.content.Context

/** Wallpaper installer helpers that apply directly in the background. */
object WallpaperInstaller {

    sealed class Result {
        data object Ok : Result()
        data class Error(val message: String) : Result()
    }

    /** Directly applies wallpaper to home and lock screen with display-fit cropping. */
    fun setStatic(context: Context, assetName: String): Result = runCatching {
        WallpaperHelper.decodeAndApply(context, assetName).getOrThrow()
        Result.Ok
    }.getOrElse { Result.Error(it.message ?: "failed to set wallpaper") }

    /** Clears wallpaper. */
    fun clear(context: Context): Result = runCatching {
        WallpaperManager.getInstance(context).clear()
        Result.Ok
    }.getOrElse { Result.Error(it.message ?: "failed to clear wallpaper") }
}
