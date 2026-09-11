package com.terrella.worlds.util

import kotlin.math.roundToInt

object QuietTimeUtils {

    /**
     * Returns how many wallpaper images will be generated during the active window.
     *
     * The active window runs from [startHour] (inclusive) to [endHour] (exclusive).
     * The first generation fires at [startHour]; subsequent ones fire every [intervalHours]
     * until the next firing would exceed [endHour].
     *
     * Special cases:
     * - [intervalHours] <= 0  → auto-update disabled ("once" mode); returns 0.
     * - [startHour] >= [endHour] → zero-width or inverted window; returns 0.
     *
     * Examples (matching the Settings UI screenshot):
     *   startHour=5, endHour=22, intervalHours=1 → 18
     *   startHour=5, endHour=22, intervalHours=2 → 9
     *   startHour=5, endHour=22, intervalHours=6 → 3
     */
    fun calculateImages(startHour: Int, endHour: Int, intervalHours: Int): Int {
        if (intervalHours <= 0) return 0
        if (startHour >= endHour) return 0
        return (endHour - startHour) / intervalHours + 1
    }

    /**
     * Returns true when [currentHour] falls inside the active window [startHour, endHour).
     * Used by [com.terrella.app.worker.WallpaperUpdateWorker] to decide whether to skip a run.
     */
    fun isInActiveWindow(currentHour: Int, startHour: Int, endHour: Int): Boolean {
        return currentHour >= startHour && currentHour < endHour
    }

    /**
     * Converts an hour of the day (0–24) to a notification progress-bar position (0–100).
     * Mirrors the scale used by [com.terrella.app.notification.NotificationHelper] where
     * the full 24-hour day maps linearly to 0–100 progress units.
     *
     * Examples: 0 h → 0, 6 h → 25, 12 h → 50, 18 h → 75, 24 h → 100
     */
    fun milestoneProgress(hour: Int): Int = (hour * 100.0 / 24.0).roundToInt()

    /**
     * Returns the progress-bar positions (0–100) for the quiet-time start and end milestones
     * as a [Pair] of (startProgress, endProgress), or **null** when quiet time is disabled.
     */
    fun milestonePositions(enabled: Boolean, startHour: Int, endHour: Int): Pair<Int, Int>? {
        if (!enabled) return null
        return Pair(milestoneProgress(startHour), milestoneProgress(endHour))
    }
}
