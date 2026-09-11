package com.terrella.worlds.data.weather

/** Normalized weather condition — every provider maps its codes into this. */
enum class Condition {
    CLEAR, PARTLY_CLOUDY, CLOUDY, FOG, DRIZZLE, RAIN, HEAVY_RAIN, SNOW, THUNDER
}

data class WeatherSnapshot(
    val tempC: Double,
    val condition: Condition,
    val isDay: Boolean,
    val windKmh: Double,
    val cloudCoverPct: Int,
    val precipMm: Double,
)

data class HourlyForecast(
    val isoTime: String,
    val tempC: Double,
    val condition: Condition,
    val precipMm: Double,
    val isDay: Boolean,
)
