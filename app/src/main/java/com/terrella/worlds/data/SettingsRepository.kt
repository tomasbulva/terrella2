package com.terrella.worlds.data

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.intPreferencesKey
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
    val refreshHours: Int,
    val quietEnabled: Boolean,
    val quietStartHour: Int,
    val quietEndHour: Int,
    val useMetric: Boolean,
    val artStyle: String,
    val showTitleInImage: Boolean,
    val wallpaperType: String, // "live" (default) | "static"
    val renderOnWallpaper: Boolean, // future: TRELLIS 3D tile rendered into wallpaper
    val assetServerUrl: String,
    val assetServerToken: String,
    val appliedLocationId: String,
)

class SettingsRepository(private val context: Context) {

    private object Keys {
        val WEATHER_PROVIDER = stringPreferencesKey("weather_provider")
        val OWM_API_KEY = stringPreferencesKey("owm_api_key")
        val WALLPAPER_MODE = stringPreferencesKey("wallpaper_mode")
        val TELEMETRY_ENABLED = booleanPreferencesKey("telemetry_enabled")
        val REFRESH_HOURS = intPreferencesKey("refresh_hours")
        val QUIET_ENABLED = booleanPreferencesKey("quiet_enabled")
        val QUIET_START_HOUR = intPreferencesKey("quiet_start_hour")
        val QUIET_END_HOUR = intPreferencesKey("quiet_end_hour")
        val USE_METRIC = booleanPreferencesKey("use_metric")
        val ART_STYLE = stringPreferencesKey("art_style")
        val SHOW_TITLE_IN_IMAGE = booleanPreferencesKey("show_title_in_image")
        val WALLPAPER_TYPE = stringPreferencesKey("wallpaper_type")
        val RENDER_ON_WALLPAPER = booleanPreferencesKey("render_on_wallpaper")
        val ASSET_SERVER_URL = stringPreferencesKey("asset_server_url")
        val ASSET_SERVER_TOKEN = stringPreferencesKey("asset_server_token")
        val APPLIED_LOCATION_ID = stringPreferencesKey("applied_location_id")
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
            wallpaperMode = p[Keys.WALLPAPER_MODE] ?: "video",
            telemetryEnabled = p[Keys.TELEMETRY_ENABLED] ?: true,
            refreshHours = p[Keys.REFRESH_HOURS] ?: 6,
            quietEnabled = p[Keys.QUIET_ENABLED] ?: false,
            quietStartHour = p[Keys.QUIET_START_HOUR] ?: 23,
            quietEndHour = p[Keys.QUIET_END_HOUR] ?: 7,
            useMetric = p[Keys.USE_METRIC] ?: true,
            artStyle = p[Keys.ART_STYLE] ?: "original",
            showTitleInImage = p[Keys.SHOW_TITLE_IN_IMAGE] ?: false,
            wallpaperType = p[Keys.WALLPAPER_TYPE] ?: "live",
            renderOnWallpaper = p[Keys.RENDER_ON_WALLPAPER] ?: false,
            assetServerUrl = p[Keys.ASSET_SERVER_URL] ?: com.terrella.worlds.BuildConfig.ASSET_SERVICE_URL,
            assetServerToken = p[Keys.ASSET_SERVER_TOKEN] ?: com.terrella.worlds.BuildConfig.ASSET_SERVICE_TOKEN,
            appliedLocationId = p[Keys.APPLIED_LOCATION_ID] ?: "",
        )
    }

    suspend fun current(): Settings = settings.first()

    suspend fun setWeatherProvider(id: String) = context.dataStore.edit { it[Keys.WEATHER_PROVIDER] = id }
    suspend fun setOwmApiKey(key: String) = context.dataStore.edit { it[Keys.OWM_API_KEY] = key }
    suspend fun setWallpaperMode(mode: String) = context.dataStore.edit { it[Keys.WALLPAPER_MODE] = mode }
    suspend fun setTelemetryEnabled(enabled: Boolean) = context.dataStore.edit { it[Keys.TELEMETRY_ENABLED] = enabled }
    suspend fun setRefreshHours(hours: Int) = context.dataStore.edit { it[Keys.REFRESH_HOURS] = hours }
    suspend fun setQuietEnabled(enabled: Boolean) = context.dataStore.edit { it[Keys.QUIET_ENABLED] = enabled }
    suspend fun setQuietStartHour(hour: Int) = context.dataStore.edit { it[Keys.QUIET_START_HOUR] = hour }
    suspend fun setQuietEndHour(hour: Int) = context.dataStore.edit { it[Keys.QUIET_END_HOUR] = hour }
    suspend fun setUseMetric(metric: Boolean) = context.dataStore.edit { it[Keys.USE_METRIC] = metric }
    suspend fun setArtStyle(style: String) = context.dataStore.edit { it[Keys.ART_STYLE] = style }
    suspend fun setShowTitleInImage(show: Boolean) = context.dataStore.edit { it[Keys.SHOW_TITLE_IN_IMAGE] = show }
    suspend fun setWallpaperType(type: String) = context.dataStore.edit { it[Keys.WALLPAPER_TYPE] = type }
    suspend fun setRenderOnWallpaper(render: Boolean) = context.dataStore.edit { it[Keys.RENDER_ON_WALLPAPER] = render }
    suspend fun setAssetServerUrl(url: String) = context.dataStore.edit { it[Keys.ASSET_SERVER_URL] = url }
    suspend fun setAssetServerToken(token: String) = context.dataStore.edit { it[Keys.ASSET_SERVER_TOKEN] = token }
    suspend fun setAppliedLocationId(id: String) = context.dataStore.edit { it[Keys.APPLIED_LOCATION_ID] = id }
}
