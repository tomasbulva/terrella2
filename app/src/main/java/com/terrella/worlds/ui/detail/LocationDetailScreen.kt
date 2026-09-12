package com.terrella.worlds.ui.detail

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.terrella.worlds.R
import com.terrella.worlds.data.DioramaRegistry
import com.terrella.worlds.data.LocationsRepository
import com.terrella.worlds.data.SavedLocation
import com.terrella.worlds.data.SettingsRepository
import com.terrella.worlds.data.telemetry.Telemetry
import com.terrella.worlds.data.weather.WeatherProviders
import com.terrella.worlds.data.weather.WeatherSnapshot
import com.terrella.worlds.util.Toasts
import com.terrella.worlds.wallpaper.WallpaperInstaller
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

@Composable
fun LocationDetailScreen(
    locationId: String?,
    onNavigateBack: () -> Unit,
    onNavigateToSettings: () -> Unit,
    locationsRepository: LocationsRepository,
    settingsRepository: SettingsRepository,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val settings by settingsRepository.settings.collectAsStateWithLifecycle(initialValue = null)
    val s = settings ?: return
    val locations by locationsRepository.locations.collectAsStateWithLifecycle(initialValue = emptyList())
    val selectedId by locationsRepository.selectedLocationId.collectAsStateWithLifecycle(initialValue = null)

    val location = remember(locations, locationId, selectedId) {
        locations.firstOrNull { it.id == locationId }
            ?: locations.firstOrNull { it.id == selectedId }
            ?: locations.firstOrNull()
    }

    var showMenu by remember { mutableStateOf(false) }
    var weather by remember { mutableStateOf<WeatherSnapshot?>(null) }
    var rendering by remember { mutableStateOf(false) }

    LaunchedEffect(location?.id, s.weatherProviderId) {
        val loc = location ?: return@LaunchedEffect
        runCatching {
            WeatherProviders.byId(s.weatherProviderId).current(loc.latitude, loc.longitude, s.owmApiKey.ifBlank { null })
        }.getOrNull()?.let { weather = it }
    }

    val isCurrentSelected = location?.id != null && location.id == selectedId

    val dioramaStyle = remember(location, s.artStyle) {
        DioramaRegistry.getStyleForLocation(location, s.artStyle)
    }

    fun applyOrUnsetWallpaper() {
        val loc = location ?: return
        scope.launch {
            rendering = true
            if (isCurrentSelected) {
                // Unset wallpaper / unselect active location
                locationsRepository.select("")
                WallpaperInstaller.clear(context)
                Toasts.show(context, "Wallpaper unset")
                Telemetry.event("wallpaper_unset", mapOf("location" to loc.name))
            } else {
                locationsRepository.select(loc.id)
                val asset = if (weather?.isDay == false) "diorama_night.jpg" else "diorama_day.jpg"
                val result = WallpaperInstaller.setStatic(context, asset)
                Toasts.show(
                    context,
                    if (result is WallpaperInstaller.Result.Ok)
                        "Wallpaper set for ${loc.name}"
                    else "Couldn't set wallpaper: ${(result as WallpaperInstaller.Result.Error).message}"
                )
                Telemetry.event("wallpaper_applied", mapOf("location" to loc.name))
            }
            rendering = false
        }
    }

    Box(modifier = Modifier.fillMaxSize()) {
        // Full-screen theme background
        Image(
            painter = painterResource(id = R.drawable.app_background),
            contentDescription = null,
            modifier = Modifier.fillMaxSize(),
            contentScale = ContentScale.Crop,
        )

        // 3D Diorama View with dynamic NOAA sun calculation & lighting
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(top = 80.dp, bottom = 120.dp),
            contentAlignment = Alignment.Center
        ) {
            Diorama3DView(
                modelPath = dioramaStyle.modelAssetPath,
                location = location,
                weather = weather,
                modifier = Modifier.fillMaxSize()
            )

            // Dynamic atmospheric weather VFX layer (rain, snow, fog, lightning, night vignette)
            WeatherEffectsOverlay(
                weather = weather,
                modifier = Modifier.fillMaxSize()
            )
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .statusBarsPadding(),
        ) {
            // ── Top bar: back | name + country | 3-dot menu ──
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = onNavigateBack) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back", tint = Color.White)
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                    Text(
                        location?.name ?: "…",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = Color.White,
                    )
                    if (!location?.country.isNullOrBlank()) {
                        Text(location.country, style = MaterialTheme.typography.bodySmall, color = Color.White.copy(alpha = 0.8f))
                    }
                }
                Box {
                    IconButton(onClick = { showMenu = true }) {
                        Icon(Icons.Filled.MoreVert, contentDescription = "Menu", tint = Color.White)
                    }
                    DropdownMenu(expanded = showMenu, onDismissRequest = { showMenu = false }) {
                        DropdownMenuItem(
                            text = { Text("Re-render") },
                            onClick = {
                                showMenu = false
                                rendering = true
                                scope.launch {
                                    val loc = location
                                    val snap = loc?.let {
                                        runCatching {
                                            WeatherProviders.byId(s.weatherProviderId).current(it.latitude, it.longitude, s.owmApiKey.ifBlank { null })
                                        }.getOrNull()
                                    }
                                    if (snap != null) weather = snap
                                    applyOrUnsetWallpaper()
                                    rendering = false
                                }
                            },
                        )
                        DropdownMenuItem(
                            text = { Text(if (isCurrentSelected) "Unset wallpaper" else "Use as Wallpaper") },
                            onClick = {
                                showMenu = false
                                applyOrUnsetWallpaper()
                            },
                        )
                        DropdownMenuItem(
                            text = { Text("Settings") },
                            onClick = {
                                showMenu = false
                                onNavigateToSettings()
                            },
                        )
                    }
                }
            }

            // ── Weather pill ──
            weather?.let { w ->
                val temp = if (s.useMetric) "${w.tempC.roundToInt()}°C" else "${(w.tempC * 9 / 5 + 32).roundToInt()}°F"
                Box(
                    modifier = Modifier
                        .align(Alignment.CenterHorizontally)
                        .padding(top = 4.dp)
                        .background(Color.Black.copy(alpha = 0.45f), RoundedCornerShape(20.dp))
                        .padding(horizontal = 16.dp, vertical = 6.dp),
                ) {
                    Text(
                        "${temp} · ${w.condition.name.lowercase().replace('_', ' ')}",
                        color = Color.White,
                        style = MaterialTheme.typography.labelLarge,
                    )
                }
            }

            Spacer(Modifier.weight(1f))

            // ── Large Circular Action Button ──
            Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                if (rendering) {
                    CircularProgressIndicator(color = Color.White)
                } else {
                    val buttonColor = if (isCurrentSelected) Color(0xFFE53935) else MaterialTheme.colorScheme.primary
                    val buttonIcon = if (isCurrentSelected) Icons.Filled.Close else Icons.Filled.Check
                    Box(
                        modifier = Modifier
                            .size(72.dp)
                            .background(buttonColor, CircleShape)
                            .clickable { applyOrUnsetWallpaper() },
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(buttonIcon, contentDescription = null, tint = Color.White, modifier = Modifier.size(32.dp))
                    }
                }
            }
            Text(
                if (isCurrentSelected) "UNSET WALLPAPER" else "SET AS ACTIVE",
                color = Color.White,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
                letterSpacing = 2.sp,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp, bottom = 32.dp),
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            )
        }
    }
}
