package com.terrella.worlds.data.weather

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.net.HttpURLConnection
import java.net.URL

/** Open-Meteo — free, no API key, WMO weather codes. https://open-meteo.com */
object OpenMeteoProvider : WeatherProvider {
    override val id = "open-meteo"
    override val displayName = "Open-Meteo (free, no key)"
    override val requiresKey = false

    private val json = Json { ignoreUnknownKeys = true }

    private fun wmoToCondition(code: Int): Condition = when (code) {
        0 -> Condition.CLEAR
        1, 2 -> Condition.PARTLY_CLOUDY
        3 -> Condition.CLOUDY
        45, 48 -> Condition.FOG
        51, 53, 55, 56, 57, 61, 80 -> Condition.DRIZZLE
        63, 65, 66, 67, 81, 82 -> Condition.RAIN
        71, 73, 75, 77, 85, 86 -> Condition.SNOW
        in 95..99 -> Condition.THUNDER
        else -> Condition.CLOUDY
    }

    private fun get(url: String): String = withContext(Dispatchers.IO) {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 8000
        conn.readTimeout = 8000
        conn.setRequestProperty("User-Agent", "Terrella2/0.1 (github.com/tomasbulva/terrella2)")
        try { conn.inputStream.bufferedReader().readText() }
        finally { conn.disconnect() }
    }

    override suspend fun current(lat: Double, lon: Double, apiKey: String?): WeatherSnapshot {
        val url = "https://api.open-meteo.com/v1/forecast" +
            "?latitude=$lat&longitude=$lon" +
            "&current=temperature_2m,weather_code,is_day,wind_kmh,cloud_cover,precip"
        val root = json.parseToJsonElement(get(url)).jsonObject
        val c = root["current"]!!.jsonObject
        return WeatherSnapshot(
            tempC = c["temperature_2m"]!!.jsonPrimitive.double,
            condition = wmoToCondition(c["weather_code"]!!.jsonPrimitive.int),
            isDay = c["is_day"]!!.jsonPrimitive.int == 1,
            windKmh = c["wind_kmh"]!!.jsonPrimitive.double,
            cloudCoverPct = c["cloud_cover"]!!.jsonPrimitive.int,
            precipMm = c["precip"]!!.jsonPrimitive.double,
        )
    }

    override suspend fun hourly(lat: Double, lon: Double, apiKey: String?, hours: Int): List<HourlyForecast> {
        val url = "https://api.open-meteo.com/v1/forecast" +
            "?latitude=$lat&longitude=$lon" +
            "&hourly=temperature_2m,weather_code,precip,is_day&forecast_hours=$hours"
        val root = json.parseToJsonElement(get(url)).jsonObject
        val h = root["hourly"]!!.jsonObject
        val times = h["time"]!!.jsonArray.map { it.jsonPrimitive.content }
        val temps = h["temperature_2m"]!!.jsonArray.map { it.jsonPrimitive.double }
        val codes = h["weather_code"]!!.jsonArray.map { it.jsonPrimitive.int }
        val precip = h["precip"]!!.jsonArray.map { it.jsonPrimitive.double }
        val isDay = h["is_day"]!!.jsonArray.map { it.jsonPrimitive.int == 1 }
        return times.indices.map { i ->
            HourlyForecast(times[i], temps[i], wmoToCondition(codes[i]), precip[i], isDay[i])
        }
    }
}
