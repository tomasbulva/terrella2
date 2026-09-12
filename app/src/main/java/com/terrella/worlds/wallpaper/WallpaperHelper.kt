package com.terrella.worlds.wallpaper

import android.app.WallpaperManager
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Point
import android.util.DisplayMetrics
import android.util.Log
import android.view.WindowManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Wallpaper application with T1-proven screen-fit logic: center-crop the bitmap
 * to the display using the most reliable dimension source per API level.
 */
object WallpaperHelper {

    private const val TAG = "WallpaperHelper"

    suspend fun apply(context: Context, bitmap: Bitmap): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val wm = WallpaperManager.getInstance(context)
            if (!wm.isWallpaperSupported) {
                Log.w(TAG, "Wallpaper not supported on device")
                return@withContext Result.failure(UnsupportedOperationException("Wallpaper not supported"))
            }

            val fitted = fitToScreen(context, bitmap)

            // 1. Set Home Screen wallpaper
            wm.setBitmap(
                fitted,
                null,
                true,
                WallpaperManager.FLAG_SYSTEM
            )

            // 2. Set Lock Screen wallpaper (best-effort across OEM skins)
            runCatching {
                wm.setBitmap(
                    fitted,
                    null,
                    true,
                    WallpaperManager.FLAG_LOCK
                )
            }.onFailure {
                Log.w(TAG, "Lockscreen wallpaper setting skipped/failed: ${it.message}")
            }

            Log.i(TAG, "Wallpaper successfully set for system & lock screens")
            Result.success(Unit)
        } catch (e: Exception) {
            Log.e(TAG, "Failed setting wallpaper", e)
            Result.failure(e)
        }
    }

    suspend fun decodeAndApply(context: Context, assetName: String): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            val bmp = BitmapFactory.decodeStream(context.assets.open("wallpapers/$assetName"))
                ?: error("Could not decode asset: wallpapers/$assetName")
            apply(context, bmp).getOrThrow()
        }
    }

    /** Scale-and-center-crop so the image fills the screen exactly (no black bars). */
    private fun fitToScreen(context: Context, bitmap: Bitmap): Bitmap {
        val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        var screenW = 0
        var screenH = 0

        // Source 1: WindowMetrics bounds (API 30+) — full display minus system decorations
        runCatching { wm.currentWindowMetrics.bounds }.getOrNull()?.let {
            screenW = it.width()
            screenH = it.height()
        }

        // Source 2: Display.getRealSize — physical display including system bars
        if (screenW <= 0 || screenH <= 0) {
            runCatching {
                val size = Point()
                @Suppress("DEPRECATION")
                wm.defaultDisplay.getRealSize(size)
                screenW = size.x
                screenH = size.y
            }
        }

        // Source 3: Resources.displayMetrics — density-adjusted logical display
        if (screenW <= 0 || screenH <= 0) {
            val metrics: DisplayMetrics = context.resources.displayMetrics
            screenW = metrics.widthPixels
            screenH = metrics.heightPixels
        }

        if (screenW <= 0 || screenH <= 0) return bitmap

        val scale = maxOf(
            screenW.toFloat() / bitmap.width,
            screenH.toFloat() / bitmap.height,
        )
        val scaledW = (bitmap.width * scale).toInt()
        val scaledH = (bitmap.height * scale).toInt()
        val offsetX = ((screenW - scaledW) / 2f)
        val offsetY = ((screenH - scaledH) / 2f)

        val out = Bitmap.createBitmap(screenW, screenH, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(out)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
        val matrix = Matrix().apply {
            postScale(scale, scale)
            postTranslate(offsetX, offsetY)
        }
        canvas.drawBitmap(bitmap, matrix, paint)
        return out
    }
}
