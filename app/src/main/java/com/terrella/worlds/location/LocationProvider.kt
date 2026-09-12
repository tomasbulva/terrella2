package com.terrella.worlds.location

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Geocoder
import android.location.Location
import android.util.Log
import androidx.core.content.ContextCompat
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import com.terrella.worlds.data.SavedLocation
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import java.util.Locale
import kotlin.coroutines.resume

/**
 * T1-proven aggressive acquisition: PRIORITY_HIGH_ACCURACY actively wakes the
 * GPS radio for a fresh fix (works from cold start); falls back to last-known
 * location only when the fresh fix fails.
 */
object LocationProvider {

    private const val TAG = "LocationProvider"

    fun hasPermission(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    suspend fun getCurrentLocation(context: Context): Result<Location> {
        if (!hasPermission(context)) {
            return Result.failure(SecurityException("Location permission not granted"))
        }
        return try {
            val client = LocationServices.getFusedLocationProviderClient(context)
            val fresh = runCatching {
                val cts = CancellationTokenSource()
                client.getCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY, cts.token).await()
            }.getOrNull()
            val lastKnown = if (fresh == null) runCatching {
                client.lastLocation.await()
            }.getOrNull() else null
            val location = fresh ?: lastKnown
            if (location != null) Result.success(location)
            else Result.failure(Exception("Unable to get location"))
        } catch (e: SecurityException) {
            Log.e(TAG, "Security exception getting location", e)
            Result.failure(e)
        } catch (e: Exception) {
            Log.e(TAG, "Error getting location", e)
            Result.failure(e)
        }
    }

    suspend fun reverseGeocode(context: Context, lat: Double, lon: Double): Pair<String, String>? =
        withContext(Dispatchers.IO) {
            runCatching {
                val geocoder = Geocoder(context, Locale.ENGLISH)
                @Suppress("DEPRECATION")
                val addresses = geocoder.getFromLocation(lat, lon, 1)
                val a = addresses?.firstOrNull() ?: return@withContext null
                val city = a.locality ?: a.subAdminArea ?: a.adminArea ?: "$lat, $lon"
                city to (a.countryName ?: "")
            }.getOrNull()
        }

    suspend fun reverseGeocodeToSaved(context: Context, lat: Double, lon: Double): SavedLocation? {
        val info = reverseGeocode(context, lat, lon)
        return SavedLocation(
            name = info?.first ?: "Current location",
            country = info?.second ?: "",
            latitude = lat,
            longitude = lon,
        )
    }
}
