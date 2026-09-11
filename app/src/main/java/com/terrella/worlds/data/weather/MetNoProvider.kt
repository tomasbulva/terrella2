package com.terrella.worlds.data.weather

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.net.HttpURLConnection
import java.net.URL

/** MET Norway Locationforecast 2.0 — free, no key; User-Agent identifies the app (their ToS). */
object MetNoProvider : WeatherProvider {
    override val id = "met-norway"
    override val displayName = "MET Norway (free, no key)"
    override val requiresKey = false

    private val json = Json { ignoreUnknownKeys = true }
    private val userAgent = "Terrella2/0.1 github.com/tomasbulva/terrella2"

    private fun symbolToCondition(symbol: String): Condition = when {
        "snow" in symbol || "sleet" in symbol -> Condition.SNOW
        "thunder" in symbol -> Condition.THUNDER
        "rainshowers" in symbol -> Condition.RAIN
        "rain" in symbol -> Condition.RAIN
        "drizzle" in symbol -> Condition.DRIZZLE
        "fog" in symbol -> Condition.FOG
        "partlycloudy" in symbol -> Condition.PARTLY_CLOUDY
        "cloudy" in symbol -> Condition.CLOUDY
        "fair" in symbol || "clearsky" in symbol -> Condition.CLEAR
        else -> Condition.CLOUDY
    }

    private suspend fun get(url: String): String = withContext(Dispatchers.IO) {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 8000
        conn.readTimeout = 8000
        conn.setRequestProperty("User-Agent", userAgent)
        try { conn.inputStream.bufferedReader().readText() }
        finally { conn.disconnect() }
    }

    override suspend fun current(lat: Double, lon: Double, apiKey: String?): WeatherSnapshot {
        val url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=$lat&lon=$lon"
        val root = json.parseToJsonElement(get(url)).jsonObject
        val ts = root["properties"]!!.jsonObject["timeseries"]!!.jsonArray
        val first = ts[0].jsonObject["data"]!!.jsonObject
        val instant = first["instant"]!!.jsonObject["details"]!!.jsonObject
        val next1h = first["next_1_hours"]?.jsonObject?.get("details")?.jsonObject
        // day/night approximation from their symbol_code suffix (_day/_night)
        val symbol = next1h?.get("summary")?.jsonObject?.get("symbol_code")?.jsonPrimitive?.content ?: "cloudy"
        return WeatherSnapshot(
            tempC = instant["air_temperature"]!!.jsonPrimitive.double,
            condition = symbolToCondition(symbol),
            isDay = !symbol.endsWith("_night"),
            windKmh = (instant["wind_speed"]!!.jsonPrimitive.double) * 3.6,
            cloudCoverPct = (instant["cloud_area_fraction"]?.jsonPrimitive?.double ?: 0.0).toInt(),
            precipMm = next1h?.get("precipitation_amount")?.jsonPrimitive?.double ?: 0.0,
        )
    }

    override suspend fun hourly(lat: Double, lon: Double, apiKey: String?, hours: Int): List<HourlyForecast> {
        val url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=$lat&lon=$lon"
        val root = json.parseToJsonElement(get(url)).jsonObject
        val ts = root["properties"]!!.jsonObject["timeseries"]!!.jsonArray
        return ts.take(hours).map { entry ->
            val data = entry.jsonObject["data"]!!.jsonObject
            val instant = data["instant"]!!.jsonObject["details"]!!.jsonObject
            val next1h = data["next_1_hours"]?.jsonObject?.get("details")?.jsonObject
            val symbol = next1h?.get("summary")?.jsonObject?.get("symbol_code")?.jsonPrimitive?.content ?: "cloudy"
            val time = entry.jsonObject["time"]!!.jsonPrimitive.content
            HourlyForecast(
                isoTime = time,
                tempC = instant["air_temperature"]!!.jsonPrimitive.double,
                condition = symbolToCondition(symbol),
                precipMm = next1h?.get("precipitation_amount")?.jsonPrimitive?.double ?: 0.0,
                isDay = !symbol.endsWith("_night"),
            )
        }
    }
}
