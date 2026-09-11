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

/** OpenWeatherMap — user supplies their own API key (stored in settings, never in the repo). */
object OpenWeatherMapProvider : WeatherProvider {
    override val id = "openweathermap"
    override val displayName = "OpenWeatherMap (your API key)"
    override val requiresKey = true

    private val json = Json { ignoreUnknownKeys = true }

    private fun codeToCondition(code: Int): Condition = when (code) {
        800 -> Condition.CLEAR
        in 801..802 -> Condition.PARTLY_CLOUDY
        in 803..804 -> Condition.CLOUDY
        in 700..799 -> Condition.FOG
        in 300..399 -> Condition.DRIZZLE
        500, 501, 520, 521 -> Condition.RAIN
        in 502..531 -> Condition.HEAVY_RAIN
        in 600..699 -> Condition.SNOW
        in 200..299 -> Condition.THUNDER
        else -> Condition.CLOUDY
    }

    private fun get(url: String): String = withContext(Dispatchers.IO) {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 8000
        conn.readTimeout = 8000
        try { conn.inputStream.bufferedReader().readText() }
        finally { conn.disconnect() }
    }

    override suspend fun current(lat: Double, lon: Double, apiKey: String?): WeatherSnapshot {
        val key = requireNotNull(apiKey) { "OpenWeatherMap requires an API key" }
        val url = "https://api.openweathermap.org/data/2.5/weather?lat=$lat&lon=$lon&units=metric&appid=$key"
        val root = json.parseToJsonElement(get(url)).jsonObject
        val weather = root["weather"]!!.jsonArray[0].jsonObject
        val main = root["main"]!!.jsonObject
        val wind = root["wind"]!!.jsonObject
        val clouds = root["clouds"]?.jsonObject?.get("all")?.jsonPrimitive?.int ?: 0
        val rain = root["rain"]?.jsonObject?.get("1h")?.jsonPrimitive?.double ?: 0.0
        return WeatherSnapshot(
            tempC = main["temp"]!!.jsonPrimitive.double,
            condition = codeToCondition(weather["id"]!!.jsonPrimitive.int),
            isDay = (root["dt"]!!.jsonPrimitive.int in
                (root["sys"]!!.jsonObject["sunrise"]!!.jsonPrimitive.int)..(root["sys"]!!.jsonObject["sunset"]!!.jsonPrimitive.int)),
            windKmh = (wind["speed"]?.jsonPrimitive?.double ?: 0.0) * 3.6,
            cloudCoverPct = clouds,
            precipMm = rain,
        )
    }

    override suspend fun hourly(lat: Double, lon: Double, apiKey: String?, hours: Int): List<HourlyForecast> {
        val key = requireNotNull(apiKey) { "OpenWeatherMap requires an API key" }
        val url = "https://api.openweathermap.org/data/2.5/forecast?lat=$lat&lon=$lon&units=metric&appid=$key&cnt=$hours"
        val root = json.parseToJsonElement(get(url)).jsonObject
        val list = root["list"]!!.jsonArray
        return list.map { entry ->
            val o = entry.jsonObject
            val weather = o["weather"]!!.jsonArray[0].jsonObject
            HourlyForecast(
                isoTime = o["dt_txt"]!!.jsonPrimitive.content,
                tempC = o["main"]!!.jsonObject["temp"]!!.jsonPrimitive.double,
                condition = codeToCondition(weather["id"]!!.jsonPrimitive.int),
                precipMm = o["rain"]?.jsonObject?.get("3h")?.jsonPrimitive?.double ?: 0.0,
                isDay = true, // 3h forecast granularity — refine later if needed
            )
        }
    }
}
