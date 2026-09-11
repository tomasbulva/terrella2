package com.terrella.worlds.data

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "settings")

data class Settings(
    val weatherProviderId: String,
    val owmApiKey: String,
    val wallpaperMode: String, // "static" | "video" | "off"
    val telemetryEnabled: Boolean,
)

class SettingsRepository(private val context: Context) {

    private object Keys {
        val WEATHER_PROVIDER = stringPreferencesKey("weather_provider")
        val OWM_API_KEY = stringPreferencesKey("owm_api_key")
        val WALLPAPER_MODE = stringPreferencesKey("wallpaper_mode")
        val TELEMETRY_ENABLED = booleanPreferencesKey("telemetry_enabled")
    }

    companion object {
        @Volatile private var instance: SettingsRepository? = null
        fun get(context: Context): SettingsRepository =
            instance ?: synchronized(this) {
                instance ?: SettingsRepository(context.applicationContext).also { instance = it }
            }

        const val WEATHER_OPEN_METEO = "open-meteo"
        const val WEATHER_MET_NORWAY = "met-norway"
        const val WEATHER_OPENWEATHERMAP = "openweathermap"
    }

    val settings: Flow<Settings> = context.dataStore.data.map { p ->
        Settings(
            weatherProviderId = p[Keys.WEATHER_PROVIDER] ?: WEATHER_OPEN_METEO,
            owmApiKey = p[Keys.OWM_API_KEY] ?: "",
            wallpaperMode = p[Keys.WALLPAPER_MODE] ?: "off",
            telemetryEnabled = p[Keys.TELEMETRY_ENABLED] ?: true,
        )
    }

    suspend fun current(): Settings = settings.first()

    suspend fun setWeatherProvider(id: String) = context.dataStore.edit { it[Keys.WEATHER_PROVIDER] = id }
    suspend fun setOwmApiKey(key: String) = context.dataStore.edit { it[Keys.OWM_API_KEY] = key }
    suspend fun setWallpaperMode(mode: String) = context.dataStore.edit { it[Keys.WALLPAPER_MODE] = mode }
    suspend fun setTelemetryEnabled(enabled: Boolean) = context.dataStore.edit { it[Keys.TELEMETRY_ENABLED] = enabled }
}
