package com.terrella.worlds.wallpaper

import android.app.WallpaperManager
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Point
import android.os.Build
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

            val fitted = fitToScreen(context, bitmap)

            var applied = false
            var lastError: Throwable? = null

            // 1. Primary path: try setting both Home and Lock screen if API >= 24
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                try {
                    wm.setBitmap(
                        fitted,
                        null,
                        true,
                        WallpaperManager.FLAG_SYSTEM or WallpaperManager.FLAG_LOCK
                    )
                    applied = true
                    Log.i(TAG, "Wallpaper set for FLAG_SYSTEM or FLAG_LOCK")
                } catch (e: Exception) {
                    Log.w(TAG, "FLAG_SYSTEM | FLAG_LOCK failed, trying individual flags", e)
                    lastError = e
                }

                if (!applied) {
                    try {
                        wm.setBitmap(
                            fitted,
                            null,
                            true,
                            WallpaperManager.FLAG_SYSTEM
                        )
                        applied = true
                        Log.i(TAG, "Wallpaper set for FLAG_SYSTEM")
                    } catch (e: Exception) {
                        Log.w(TAG, "FLAG_SYSTEM failed", e)
                        lastError = e
                    }
                }
            }

            // 2. Fallback path: standard 1-arg setBitmap (works universally on all Android versions & OEMs)
            if (!applied) {
                try {
                    wm.setBitmap(fitted)
                    applied = true
                    Log.i(TAG, "Wallpaper set via standard setBitmap(bitmap)")
                } catch (e: Exception) {
                    Log.e(TAG, "Standard setBitmap failed", e)
                    lastError = e
                }
            }

            if (applied) {
                Result.success(Unit)
            } else {
                Result.failure(lastError ?: Exception("Unknown wallpaper error"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed setting wallpaper", e)
            Result.failure(e)
        }
    }

    suspend fun decodeAndApply(context: Context, assetName: String): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            val stream = context.assets.open("wallpapers/$assetName")
            val bmp = BitmapFactory.decodeStream(stream)
            stream.close()
            if (bmp == null) {
                error("Could not decode asset: wallpapers/$assetName")
            }
            apply(context, bmp).getOrThrow()
        }
    }

    /** Scale-and-center-crop so the image fills the screen exactly (no black bars). */
    private fun fitToScreen(context: Context, bitmap: Bitmap): Bitmap {
        var screenW = 0
        var screenH = 0

        val wm = context.getSystemService(Context.WINDOW_SERVICE) as? WindowManager

        // Source 1: WindowMetrics bounds (API 30+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R && wm != null) {
            runCatching { wm.currentWindowMetrics.bounds }.getOrNull()?.let {
                screenW = it.width()
                screenH = it.height()
            }
        }

        // Source 2: Display.getRealSize — physical display including system bars
        if ((screenW <= 0 || screenH <= 0) && wm != null) {
            runCatching {
                val size = Point()
                @Suppress("DEPRECATION")
                wm.defaultDisplay?.getRealSize(size)
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

        if (screenW <= 0 || screenH <= 0 || (screenW == bitmap.width && screenH == bitmap.height)) {
            return bitmap
        }

        val scale = maxOf(
            screenW.toFloat() / bitmap.width.toFloat(),
            screenH.toFloat() / bitmap.height.toFloat(),
        )
        val scaledW = (bitmap.width * scale).toInt().coerceAtLeast(1)
        val scaledH = (bitmap.height * scale).toInt().coerceAtLeast(1)
        val offsetX = (screenW - scaledW) / 2f
        val offsetY = (screenH - scaledH) / 2f

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
