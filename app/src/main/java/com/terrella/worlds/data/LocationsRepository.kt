package com.terrella.worlds.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

private val Context.locationsStore by preferencesDataStore(name = "locations")

class LocationsRepository(private val context: Context) {

    private object Keys {
        val LOCATIONS = stringPreferencesKey("saved_locations")
        val SELECTED_ID = stringPreferencesKey("selected_location_id")
    }

    private val json = Json { ignoreUnknownKeys = true }

    val locations: Flow<List<SavedLocation>> = context.locationsStore.data.map { p ->
        p[Keys.LOCATIONS]?.let { runCatching { json.decodeFromString<List<SavedLocation>>(it) }.getOrNull() } ?: emptyList()
    }

    val selectedLocationId: Flow<String?> = context.locationsStore.data.map { it[Keys.SELECTED_ID] }

    val selectedLocation: Flow<SavedLocation?> =
        combine(selectedLocationId, locations) { id, list -> list.firstOrNull { it.id == id } }

    suspend fun addLocation(location: SavedLocation) = context.locationsStore.edit { p ->
        val list = p[Keys.LOCATIONS]
            ?.let { runCatching { json.decodeFromString<List<SavedLocation>>(it) }.getOrDefault(emptyList()) }
            ?: emptyList()
        p[Keys.LOCATIONS] = json.encodeToString(list + location)
        if (list.isEmpty()) p[Keys.SELECTED_ID] = location.id
    }

    suspend fun removeLocation(id: String) = context.locationsStore.edit { p ->
        val list = p[Keys.LOCATIONS]
            ?.let { runCatching { json.decodeFromString<List<SavedLocation>>(it) }.getOrDefault(emptyList()) }
            ?: emptyList()
        p[Keys.LOCATIONS] = json.encodeToString(list.filterNot { it.id == id })
        if (p[Keys.SELECTED_ID] == id) {
            val next = list.firstOrNull { it.id != id }?.id
            if (next != null) p[Keys.SELECTED_ID] = next else p.remove(Keys.SELECTED_ID)
        }
    }

    suspend fun select(id: String) = context.locationsStore.edit { it[Keys.SELECTED_ID] = id }

    companion object {
        @Volatile private var instance: LocationsRepository? = null
        fun get(context: Context): LocationsRepository =
            instance ?: synchronized(this) {
                instance ?: LocationsRepository(context.applicationContext).also { instance = it }
            }
    }
}
