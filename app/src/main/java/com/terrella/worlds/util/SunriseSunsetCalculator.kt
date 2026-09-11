package com.terrella.worlds.util

import kotlin.math.PI
import kotlin.math.acos
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.tan

/**
 * Computes sunrise and sunset times using the NOAA Solar Calculator algorithm.
 *
 * Reference: https://gml.noaa.gov/grad/solcalc/solareqns.PDF
 *
 * All inputs are plain integers/doubles so this object is fully testable without
 * any Android framework dependency.
 */
object SunriseSunsetCalculator {

    /**
     * Returns (sunriseMinutes, sunsetMinutes) — minutes since local midnight (0–1440).
     *
     * @param latitudeDeg     Latitude in degrees  (-90 to +90).
     * @param longitudeDeg    Longitude in degrees (-180 to +180).
     * @param dayOfYear       Day of the year (1–366), in the *local* calendar.
     * @param utcOffsetMinutes UTC offset of the location in minutes, including DST
     *                         (e.g. UTC+1 = 60, UTC-5 = -300).
     *
     * Edge cases:
     *  - Polar day  (sun never sets)  → (0, 1440)
     *  - Polar night (sun never rises) → (720, 720)  [centred on solar noon]
     */
    fun compute(
        latitudeDeg: Double,
        longitudeDeg: Double,
        dayOfYear: Int,
        utcOffsetMinutes: Int,
    ): Pair<Int, Int> {
        // Fractional year in radians (day 1 = 0 rad, day 365 = ~2π)
        val gamma = 2.0 * PI / 365.0 * (dayOfYear - 1)

        // Equation of time (minutes) — correction for orbital eccentricity and axial tilt
        val eqtime = 229.18 * (
            0.000075
            + 0.001868 * cos(gamma)
            - 0.032077 * sin(gamma)
            - 0.014615 * cos(2.0 * gamma)
            - 0.040890 * sin(2.0 * gamma)
        )

        // Solar declination (radians)
        val decl = (
            0.006918
            - 0.399912 * cos(gamma)
            + 0.070257 * sin(gamma)
            - 0.006758 * cos(2.0 * gamma)
            + 0.000907 * sin(2.0 * gamma)
            - 0.002697 * cos(3.0 * gamma)
            + 0.001480 * sin(3.0 * gamma)
        )

        val latRad = latitudeDeg * PI / 180.0

        // Hour angle at sunrise / sunset.
        // 90.833° solar zenith accounts for atmospheric refraction + solar disc radius.
        val cosHourAngle = (
            cos(90.833 * PI / 180.0) / (cos(latRad) * cos(decl))
            - tan(latRad) * tan(decl)
        )

        // Polar edge cases
        if (cosHourAngle < -1.0) return Pair(0, 1440)    // polar day  — sun never sets
        if (cosHourAngle >  1.0) return Pair(720, 720)   // polar night — sun never rises

        val hourAngleDeg = acos(cosHourAngle) * 180.0 / PI

        // Solar noon in UTC minutes (longitude correction + equation of time)
        val solarNoonUtcMin = 720.0 - 4.0 * longitudeDeg - eqtime

        // Sunrise / sunset in UTC minutes
        val sunriseUtcMin = solarNoonUtcMin - 4.0 * hourAngleDeg
        val sunsetUtcMin  = solarNoonUtcMin + 4.0 * hourAngleDeg

        // Convert to local time. Using Kotlin's mod() guarantees a non-negative result.
        val sunriseLocal = (sunriseUtcMin.toInt() + utcOffsetMinutes).mod(1440)
        val sunsetLocal  = (sunsetUtcMin.toInt()  + utcOffsetMinutes).mod(1440)

        return Pair(sunriseLocal, sunsetLocal)
    }
}
