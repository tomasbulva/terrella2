package com.terrella.worlds.data.weather

/**
 * A weather data source. Providers must be side-effect free and network-safe
 * (called from Dispatchers.IO). Keys, when required, come from user settings —
 * never from the repo.
 */
interface WeatherProvider {
    val id: String
    val displayName: String
    val requiresKey: Boolean

    suspend fun current(lat: Double, lon: Double, apiKey: String? = null): WeatherSnapshot
    suspend fun hourly(lat: Double, lon: Double, apiKey: String? = null, hours: Int = 24): List<HourlyForecast>
}

object WeatherProviders {
    val all: List<WeatherProvider> = listOf(OpenMeteoProvider, MetNoProvider)
    fun byId(id: String): WeatherProvider = all.firstOrNull { it.id == id } ?: OpenMeteoProvider
}
