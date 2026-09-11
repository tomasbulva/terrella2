package com.terrella.worlds.location

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Geocoder
import androidx.core.content.ContextCompat
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.terrella.worlds.data.SavedLocation
import kotlinx.coroutines.tasks.await
import java.util.Locale

/** One-shot location lookup + geocoding helpers. */
object LocationProvider {

    fun hasPermission(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    /** Reverse-geocode coordinates into a SavedLocation. Never blocks main thread. */
    suspend fun reverseGeocode(context: Context, lat: Double, lon: Double): SavedLocation? =
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            runCatching {
                val geocoder = Geocoder(context, Locale.getDefault())
                @Suppress("DEPRECATION")
                val addresses = geocoder.getFromLocation(lat, lon, 1) ?: return@withContext null
                val a = addresses.firstOrNull() ?: return@withContext null
                SavedLocation(
                    name = a.locality ?: a.subAdminArea ?: a.adminArea ?: "Current location",
                    country = a.countryName ?: "",
                    latitude = lat,
                    longitude = lon,
                )
            }.getOrNull()
        }

    /** One-shot current position (coarse-ish accuracy is fine for a city). */
    suspend fun currentPosition(context: Context): Pair<Double, Double>? {
        if (!hasPermission(context)) return null
        return runCatching {
            val client = LocationServices.getFusedLocationProviderClient(context)
            val location = client.getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, null).await()
            location?.let { it.latitude to it.longitude }
        }.getOrNull()
    }
}
