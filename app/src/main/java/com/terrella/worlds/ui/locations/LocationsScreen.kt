package com.terrella.worlds.ui.locations

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.location.Geocoder
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Navigation
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.terrella.worlds.data.LocationsRepository
import com.terrella.worlds.data.SavedLocation
import com.terrella.worlds.data.SettingsRepository
import com.terrella.worlds.data.telemetry.Telemetry
import com.terrella.worlds.data.weather.WeatherProviders
import com.terrella.worlds.data.weather.WeatherSnapshot
import com.terrella.worlds.location.LocationProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.Locale
import kotlin.math.roundToInt

@Composable
fun LocationsScreen(
    onNavigateToWorld: () -> Unit,
    onNavigateToSettings: () -> Unit,
    locationsRepository: LocationsRepository,
    settingsRepository: SettingsRepository,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val locations by locationsRepository.locations.collectAsStateWithLifecycle(initialValue = emptyList())
    val settings by settingsRepository.settings.collectAsStateWithLifecycle(initialValue = null)
    val selectedId by locationsRepository.selectedLocationId.collectAsStateWithLifecycle(initialValue = null)
    val s = settings ?: return

    var showAddDialog by remember { mutableStateOf(false) }

    // Weather per location, fetched on entry
    val weather = remember { mutableStateMapOf<String, WeatherSnapshot>() }
    LaunchedEffect(locations.size, s?.weatherProviderId) {
        val list = locations
        if (list.isEmpty()) return@LaunchedEffect
        list.take(6).forEach { loc ->
            if (weather[loc.id] == null) {
                runCatching {
                    WeatherProviders.byId(s.weatherProviderId)
                        .current(loc.latitude, loc.longitude, s.owmApiKey.ifBlank { null })
                }.getOrNull()?.let { weather[loc.id] = it }
            }
        }
    }

    // Bundled diorama thumbnails (day/night), decoded once
    val nightBmp = remember { decodeAsset(context, "wallpapers/diorama_night.jpg") }
    val dayBmp = remember { decodeAsset(context, "wallpapers/diorama_day.jpg") }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        floatingActionButton = {
            FloatingActionButton(onClick = { showAddDialog = true }) {
                Icon(Icons.Filled.Add, contentDescription = "Add location")
            }
        },
    ) { padding ->
        Column(
            Modifier
                .padding(padding)
                .fillMaxSize()
                .padding(horizontal = 16.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("Places", style = MaterialTheme.typography.headlineSmall)
                Row {
                    OutlinedButton(onClick = onNavigateToWorld, modifier = Modifier.padding(end = 8.dp)) {
                        Text("World")
                    }
                    IconButton(onClick = onNavigateToSettings) {
                        Icon(Icons.Filled.Settings, contentDescription = "Settings")
                    }
                }
            }

            if (locations.isEmpty()) {
                Column(
                    modifier = Modifier.fillMaxSize().padding(32.dp),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text("No places yet", style = MaterialTheme.typography.titleMedium)
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "Add a city and its diorama will follow the real weather.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(16.dp))
                    Button(onClick = { showAddDialog = true }) { Text("Add your first place") }
                }
            } else {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    items(locations, key = { it.id }) { location ->
                        val snap = weather[location.id]
                        val isSelected = location.id == selectedId
                        val thumb = if (snap?.isDay == false) nightBmp else dayBmp
                        LocationCard(
                            name = location.name,
                            subtitle = location.country,
                            weather = snap,
                            isSelected = isSelected,
                            backgroundBitmap = thumb,
                            isCurrentLocation = false,
                            useMetric = s.useMetric,
                            onClick = {
                                scope.launch {
                                    locationsRepository.select(location.id)
                                    Telemetry.event("location_selected", mapOf("source" to "list"))
                                }
                            },
                            onDelete = {
                                scope.launch { locationsRepository.removeLocation(location.id) }
                            },
                        )
                    }
                    item { Spacer(Modifier.height(88.dp)) }
                }
            }
        }
    }

    if (showAddDialog) {
        AddLocationDialog(
            onDismiss = { showAddDialog = false },
            onAdd = { loc ->
                scope.launch {
                    locationsRepository.addLocation(loc)
                    Telemetry.event("location_added", mapOf("source" to "search"))
                }
                showAddDialog = false
            },
            onUseCurrentLocation = {
                scope.launch {
                    val pos = LocationProvider.currentPosition(context)
                    val loc = pos?.let { LocationProvider.reverseGeocode(context, it.first, it.second) }
                    if (loc != null) {
                        locationsRepository.addLocation(loc)
                        Telemetry.event("location_added", mapOf("source" to "gps"))
                    }
                    showAddDialog = false
                }
            },
        )
    }
}

private fun decodeAsset(context: android.content.Context, path: String): Bitmap? = runCatching {
    BitmapFactory.decodeStream(context.assets.open(path))
}.getOrNull()

/** T1's visual language: expanded selected card with diorama backdrop, compact unselected cards. */
@Composable
private fun LocationCard(
    name: String,
    subtitle: String,
    weather: WeatherSnapshot?,
    isSelected: Boolean,
    backgroundBitmap: Bitmap?,
    isCurrentLocation: Boolean,
    useMetric: Boolean,
    onClick: () -> Unit,
    onDelete: () -> Unit,
) {
    val cardShape = RoundedCornerShape(16.dp)
    val borderModifier = if (isSelected) {
        Modifier.border(width = 2.dp, color = MaterialTheme.colorScheme.primary, shape = cardShape)
    } else {
        Modifier
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .then(if (isSelected) Modifier.height(160.dp) else Modifier.height(96.dp))
            .then(borderModifier)
            .clickable(onClick = onClick),
        shape = cardShape,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Box(modifier = Modifier.fillMaxSize()) {
            if (backgroundBitmap != null) {
                Image(
                    bitmap = backgroundBitmap.asImageBitmap(),
                    contentDescription = null,
                    modifier = Modifier.fillMaxSize(),
                    contentScale = ContentScale.Crop,
                )
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(
                            Brush.verticalGradient(
                                colors = listOf(
                                    Color.Black.copy(alpha = 0.3f),
                                    Color.Black.copy(alpha = 0.6f),
                                ),
                            ),
                        ),
                )
            }
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(16.dp),
                verticalArrangement = Arrangement.SpaceBetween,
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (isSelected && isCurrentLocation) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                Icons.Filled.Navigation,
                                contentDescription = null,
                                modifier = Modifier.size(14.dp),
                                tint = Color.White.copy(alpha = 0.8f),
                            )
                            Spacer(Modifier.width(4.dp))
                            Text("GPS", style = MaterialTheme.typography.labelSmall, color = Color.White.copy(alpha = 0.8f))
                        }
                    } else {
                        Spacer(Modifier.height(0.dp))
                    }
                    if (!isSelected) {
                        Icon(
                            Icons.Filled.Delete,
                            contentDescription = "Remove ${name}",
                            modifier = Modifier
                                .size(20.dp)
                                .clickable(onClick = onDelete),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.Bottom,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = name,
                            style = if (isSelected) MaterialTheme.typography.headlineMedium else MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            color = if (backgroundBitmap != null) Color.White else MaterialTheme.colorScheme.onSurface,
                        )
                        if (subtitle.isNotBlank()) {
                            Text(
                                text = subtitle,
                                style = MaterialTheme.typography.bodySmall,
                                color = if (backgroundBitmap != null) Color.White.copy(alpha = 0.7f)
                                else MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    if (weather != null) {
                        Column(horizontalAlignment = Alignment.End) {
                            val temp = if (useMetric) weather.tempC else weather.tempC * 9 / 5 + 32
                            Text(
                                text = "${temp.roundToInt()}°${if (useMetric) "C" else "F"}",
                                style = MaterialTheme.typography.headlineSmall,
                                fontWeight = FontWeight.Bold,
                                color = if (backgroundBitmap != null) Color.White else MaterialTheme.colorScheme.onSurface,
                            )
                            Text(
                                text = weather.condition.name.lowercase().replace('_', ' '),
                                style = MaterialTheme.typography.labelSmall,
                                color = if (backgroundBitmap != null) Color.White.copy(alpha = 0.8f)
                                else MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun AddLocationDialog(
    onDismiss: () -> Unit,
    onAdd: (SavedLocation) -> Unit,
    onUseCurrentLocation: () -> Unit,
) {
    val context = LocalContext.current
    var query by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<SavedLocation>>(emptyList()) }
    var searching by remember { mutableStateOf(false) }

    fun search() {
        val q = query.trim()
        if (q.length < 3) return
        searching = true
        results = emptyList()
        kotlinx.coroutines.CoroutineScope(Dispatchers.IO).launch {
            val addresses: List<android.location.Address> = runCatching {
                val geocoder = Geocoder(context, Locale.getDefault())
                @Suppress("DEPRECATION")
                geocoder.getFromLocationName(q, 5)
            }.getOrNull() ?: emptyList()
            val found: List<SavedLocation> = addresses.mapNotNull { a ->
                val name = a.locality ?: a.subAdminArea ?: a.adminArea ?: a.getAddressLine(0) ?: q
                val country = a.countryName ?: ""
                if (name.isBlank()) null
                else SavedLocation(name = name, country = country, latitude = a.latitude, longitude = a.longitude)
            }
            withContext(kotlinx.coroutines.Dispatchers.Main) {
                results = found
                searching = false
            }
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add a place") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    label = { Text("City or place") },
                    singleLine = true,
                    trailingIcon = {
                        IconButton(onClick = { search() }) {
                            Icon(Icons.Filled.Search, contentDescription = "Search")
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                )
                if (searching) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.Center,
                    ) {
                        CircularProgressIndicator(modifier = Modifier.size(24.dp))
                    }
                }
                results.forEach { candidate ->
                    OutlinedButton(
                        onClick = { onAdd(candidate) },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Column {
                            Text(candidate.name)
                            if (candidate.country.isNotBlank()) {
                                Text(
                                    candidate.country,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
                if (query.isNotBlank() && results.isEmpty() && !searching) {
                    Text(
                        "Press the search icon to look up the place.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        },
        confirmButton = {},
        dismissButton = {
            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = onUseCurrentLocation) { Text("Use my location") }
                OutlinedButton(onClick = onDismiss) { Text("Close") }
            }
        },
    )
}
