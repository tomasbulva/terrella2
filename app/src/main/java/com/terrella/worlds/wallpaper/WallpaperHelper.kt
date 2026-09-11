package com.terrella.worlds.wallpaper

import android.app.WallpaperManager
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Point
import android.util.DisplayMetrics
import android.view.WindowManager

/**
 * Wallpaper application with T1-proven screen-fit logic: center-crop the bitmap
 * to the display using the most reliable dimension source per API level.
 */
object WallpaperHelper {

    fun apply(context: Context, bitmap: Bitmap): Result<Unit> = runCatching {
        WallpaperManager.getInstance(context).setBitmap(fitToScreen(context, bitmap))
    }

    fun decodeAndApply(context: Context, assetName: String): Result<Unit> = runCatching {
        val bmp = BitmapFactory.decodeStream(context.assets.open("wallpapers/$assetName"))
        apply(context, bmp)
    }

    /** Scale-and-center-crop so the image fills the screen exactly (no black bars). */
    private fun fitToScreen(context: Context, bitmap: Bitmap): Bitmap {
        val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        var screenW = 0
        var screenH = 0

        // Source 1: WindowMetrics bounds (API 30+) — full display minus system decorations
        runCatching { wm.currentWindowMetrics.bounds }.getOrNull()?.let {
            screenW = it.width(); screenH = it.height()
        }

        // Source 2: Display.getRealSize — physical display including system bars
        if (screenW <= 0 || screenH <= 0) {
            runCatching {
                val size = Point()
                wm.defaultDisplay.getRealSize(size)
                screenW = size.x; screenH = size.y
            }
        }

        // Source 3: Resources.displayMetrics — density-adjusted logical display
        if (screenW <= 0 || screenH <= 0) {
            val metrics: DisplayMetrics = context.resources.displayMetrics
            screenW = metrics.widthPixels; screenH = metrics.heightPixels
        }

        if (screenW <= 0 || screenH <= 0) return bitmap

        val scale = maxOf(
            screenW.toFloat() / bitmap.width,
            screenH.toFloat() / bitmap.height,
        )
        val scaledW = (bitmap.width * scale).toInt()
        val scaledH = (bitmap.height * scale).toInt()
        val offsetX = ((screenW - scaledW) / 2f).toInt()
        val offsetY = ((screenH - scaledH) / 2f).toInt()

        val out = Bitmap.createBitmap(screenW, screenH, Bitmap.Config.ARGB_8888)
        val canvas = android.graphics.Canvas(out)
        canvas.drawBitmap(
            android.graphics.Bitmap.createScaledBitmap(bitmap, scaledW, scaledH, true),
            offsetX.toFloat(), offsetY.toFloat(), null,
        )
        return out
    }
}
