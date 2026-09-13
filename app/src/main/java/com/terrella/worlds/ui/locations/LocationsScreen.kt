package com.terrella.worlds.ui.locations

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.location.Geocoder
import android.location.Location
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
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
import com.terrella.worlds.R
import com.terrella.worlds.data.catalog.AssetCatalogRepository
import com.terrella.worlds.data.catalog.AssetCatalogRepository.AssetState
import com.terrella.worlds.data.LocationsRepository
import com.terrella.worlds.data.SavedLocation
import com.terrella.worlds.data.SettingsRepository
import com.terrella.worlds.data.telemetry.Telemetry
import com.terrella.worlds.data.weather.WeatherProviders
import com.terrella.worlds.data.weather.WeatherSnapshot
import com.terrella.worlds.location.LocationProvider
import com.terrella.worlds.util.DioramaHumor
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.Locale
import kotlin.math.roundToInt

@Composable
fun LocationsScreen(
    onOpenDetail: (String) -> Unit,
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
    var locating by remember { mutableStateOf(false) }

    val manualLocations = locations.filterNot { it.isCurrent }
    val currentLocation = locations.firstOrNull { it.isCurrent }

    // ---- Auto-detect current location on entry (aggressive PRIORITY_HIGH_ACCURACY) ----
    fun fetchCurrent() {
        if (locating) return
        locating = true
        scope.launch {
            val result = LocationProvider.getCurrentLocation(context)
            val pos = result.getOrNull()
            if (pos != null) {
                val loc = LocationProvider.reverseGeocode(context, pos.latitude, pos.longitude)
                locationsRepository.upsertCurrentLocation(
                    name = loc?.first ?: "Current location",
                    country = loc?.second ?: "",
                    latitude = pos.latitude,
                    longitude = pos.longitude,
                )
            }
            locating = false
        }
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        if (grants.values.any { it }) fetchCurrent()
    }

    LaunchedEffect(Unit) {
        if (currentLocation == null && !locating) {
            if (LocationProvider.hasPermission(context)) fetchCurrent()
            else permissionLauncher.launch(
                arrayOf(
                    android.Manifest.permission.ACCESS_FINE_LOCATION,
                    android.Manifest.permission.ACCESS_COARSE_LOCATION,
                )
            )
        }
    }

    // ---- Weather per location on entry ----
    val weather = remember { mutableStateMapOf<String, WeatherSnapshot>() }
    LaunchedEffect(locations.size, s.weatherProviderId) {
        locations.take(6).forEach { loc ->
            if (weather[loc.id] == null) {
                runCatching {
                    WeatherProviders.byId(s.weatherProviderId)
                        .current(loc.latitude, loc.longitude, s.owmApiKey.ifBlank { null })
                }.getOrNull()?.let { weather[loc.id] = it }
            }
        }
    }

    val catalog = AssetCatalogRepository.get(context)
    val catalogStates by catalog.states.collectAsStateWithLifecycle()

    // Drive asset availability: catalog sync, downloads, generation jobs
    LaunchedEffect(locations, s.assetServerToken, s.assetServerUrl) {
        if (locations.isNotEmpty()) catalog.refresh(s, locations)
    }

    Scaffold(
        containerColor = Color.Transparent,
        floatingActionButton = {
            FloatingActionButton(onClick = { showAddDialog = true }) {
                Icon(Icons.Filled.Add, contentDescription = "Add location")
            }
        },
    ) { padding ->
        Box(Modifier.padding(padding).fillMaxSize()) {
        Image(
            painter = androidx.compose.ui.res.painterResource(com.terrella.worlds.R.drawable.app_background),
            contentDescription = null,
            modifier = Modifier.fillMaxSize(),
            contentScale = ContentScale.Crop,
        )
        Column(
            Modifier
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
                Text("Terrella", style = MaterialTheme.typography.headlineSmall)
                IconButton(onClick = onNavigateToSettings) {
                    Icon(Icons.Filled.Settings, contentDescription = "Settings")
                }
            }

            if (locations.isEmpty()) {
                Column(
                    modifier = Modifier.fillMaxSize().padding(32.dp),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    if (locating) {
                        CircularProgressIndicator()
                        Spacer(Modifier.height(16.dp))
                        Text("Finding your place…", style = MaterialTheme.typography.bodyMedium)
                    } else {
                        Text("No places yet", style = MaterialTheme.typography.titleMedium)
                        Spacer(Modifier.height(8.dp))
                        Text(
                            "We couldn't detect your location — add a place manually and its diorama will follow the real weather.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Spacer(Modifier.height(16.dp))
                        Button(onClick = { showAddDialog = true }) { Text("Add a place") }
                    }
                }
            } else {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    // ── Current location (auto-recognized) ──
                    currentLocation?.let { current ->
                        item {
                            SectionLabel("Current location")
                            val snap = weather[current.id]
                            val state = catalogStates[catalog.keyOf(current)]
                            val poster = rememberPosterBitmap((state as? AssetState.Ready)?.poster)
                            if (state is AssetState.Ready && poster != null) {
                                LocationCard(
                                    name = current.name,
                                    subtitle = current.country,
                                    weather = snap,
                                    isSelected = current.id == selectedId,
                                    backgroundBitmap = poster,
                                    isCurrentLocation = true,
                                    useMetric = s.useMetric,
                                    onClick = {
                                        scope.launch {
                                            locationsRepository.select(current.id)
                                            Telemetry.event("location_selected", mapOf("source" to "gps"))
                                            onOpenDetail(current.id)
                                        }
                                    },
                                    onDelete = null,
                                )
                            } else {
                                PendingDioramaCard(
                                    name = current.name,
                                    subtitle = current.country,
                                    state = state ?: AssetState.Missing,
                                    isSelected = current.id == selectedId,
                                    isCurrentLocation = true,
                                )
                            }
                        }
                    }
                    // ── Your locations (manual) ──
                    if (manualLocations.isNotEmpty()) {
                        item { SectionLabel("Your locations") }
                        items(manualLocations, key = { it.id }) { location ->
                            val snap = weather[location.id]
                            val state = catalogStates[catalog.keyOf(location)]
                            val poster = rememberPosterBitmap((state as? AssetState.Ready)?.poster)
                            if (state is AssetState.Ready && poster != null) {
                                LocationCard(
                                    name = location.name,
                                    subtitle = location.country,
                                    weather = snap,
                                    isSelected = location.id == selectedId,
                                    backgroundBitmap = poster,
                                    isCurrentLocation = false,
                                    useMetric = s.useMetric,
                                    onClick = {
                                        scope.launch {
                                            locationsRepository.select(location.id)
                                            Telemetry.event("location_selected", mapOf("source" to "list"))
                                            onOpenDetail(location.id)
                                        }
                                    },
                                    onDelete = {
                                        scope.launch { locationsRepository.removeLocation(location.id) }
                                    },
                                )
                            } else {
                                PendingDioramaCard(
                                    name = location.name,
                                    subtitle = location.country,
                                    state = state ?: AssetState.Missing,
                                    isSelected = location.id == selectedId,
                                    isCurrentLocation = false,
                                    onDelete = {
                                        scope.launch { locationsRepository.removeLocation(location.id) }
                                    },
                                )
                            }
                        }
                    }
                    item { Spacer(Modifier.height(88.dp)) }
                }
            }
        }
        }
    }

    if (showAddDialog) {
        AddLocationDialog(
            onDismiss = { showAddDialog = false },
            onAdd = { loc ->
                scope.launch {
                    runCatching { locationsRepository.addLocation(loc) }
                        .fold(
                            onSuccess = {
                                Telemetry.event("location_added", mapOf("source" to "search"))
                                com.terrella.worlds.util.Toasts.show(context, "${loc.name} added")
                            },
                            onFailure = {
                                com.terrella.worlds.util.Toasts.show(context, "Couldn't add place: ${it.message}")
                            },
                        )
                }
                showAddDialog = false
            },
        )
    }
}

@Composable
private fun SectionLabel(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleSmall,
        color = MaterialTheme.colorScheme.primary,
        modifier = Modifier.padding(top = 4.dp, bottom = 4.dp),
    )
}

@Composable
private fun rememberPosterBitmap(file: java.io.File?): Bitmap? =
    remember(file?.absolutePath) {
        file?.let { runCatching { BitmapFactory.decodeFile(it.absolutePath) }.getOrNull() }
    }

/**
 * No-asset card per the new-user spec: no screenshot background — location
 * name, a nerdy "cooking" line, and the card background acting as the
 * progress bar (bright gradient gradually covered left→right by a darker
 * translucent layer as generation progresses).
 */
@Composable
private fun PendingDioramaCard(
    name: String,
    subtitle: String,
    state: AssetState,
    isSelected: Boolean,
    isCurrentLocation: Boolean,
    onDelete: (() -> Unit)? = null,
) {
    val cardShape = RoundedCornerShape(16.dp)
    val borderModifier = if (isSelected) {
        Modifier.border(width = 2.dp, color = MaterialTheme.colorScheme.primary, shape = cardShape)
    } else {
        Modifier
    }
    val progress = when (state) {
        is AssetState.Generating -> state.progress.coerceIn(0.03f, 0.98f)
        is AssetState.Failed -> 0f
        AssetState.Missing -> 0.03f
        is AssetState.Ready -> 1f
    }
    val fill by animateFloatAsState(
        targetValue = progress,
        animationSpec = tween(durationMillis = 600),
        label = "dioramaProgress",
    )

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .then(if (isSelected) Modifier.height(160.dp) else Modifier.height(96.dp))
            .then(borderModifier),
        shape = cardShape,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Box(modifier = Modifier.fillMaxSize()) {
            // Bright gradient base — the "to be covered" progress canvas
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(
                        Brush.linearGradient(
                            listOf(Color(0xFF46536B), Color(0xFF2A3342))
                        )
                    ),
            )
            // Darker translucent cover sliding in from the left = progress
            Box(
                modifier = Modifier
                    .fillMaxHeight()
                    .fillMaxWidth(fill)
                    .background(Color(0xFF12161D).copy(alpha = 0.72f)),
            )
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
                    if (isCurrentLocation) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                Icons.Filled.Navigation,
                                contentDescription = null,
                                modifier = Modifier.size(14.dp),
                                tint = Color.White.copy(alpha = 0.8f),
                            )
                            Spacer(Modifier.width(4.dp))
                            Text(
                                "GPS",
                                style = MaterialTheme.typography.labelSmall,
                                color = Color.White.copy(alpha = 0.8f),
                            )
                        }
                    } else {
                        Spacer(Modifier.height(0.dp))
                    }
                    if (!isCurrentLocation && onDelete != null) {
                        Icon(
                            Icons.Filled.Delete,
                            contentDescription = "Remove $name",
                            modifier = Modifier
                                .size(20.dp)
                                .clickable(onClick = { onDelete.invoke() }),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                Column {
                    Text(
                        text = DioramaHumor.forName(name, subtitle),
                        style = MaterialTheme.typography.bodySmall,
                        fontStyle = androidx.compose.ui.text.font.FontStyle.Italic,
                        color = Color.White.copy(alpha = 0.85f),
                    )
                    if (state is AssetState.Failed) {
                        Text(
                            text = "Couldn't finish — will retry next launch",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.error,
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                    Text(
                        text = name,
                        style = if (isSelected) MaterialTheme.typography.headlineMedium else MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = Color.White,
                    )
                    if (subtitle.isNotBlank()) {
                        Text(
                            text = subtitle,
                            style = MaterialTheme.typography.bodySmall,
                            color = Color.White.copy(alpha = 0.7f),
                        )
                    }
                }
            }
        }
    }
}

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
    onDelete: (() -> Unit)?,
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
                    if (isCurrentLocation) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                Icons.Filled.Navigation,
                                contentDescription = null,
                                modifier = Modifier.size(14.dp),
                                tint = if (backgroundBitmap != null) Color.White.copy(alpha = 0.8f)
                                else MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Spacer(Modifier.width(4.dp))
                            Text(
                                "GPS",
                                style = MaterialTheme.typography.labelSmall,
                                color = if (backgroundBitmap != null) Color.White.copy(alpha = 0.8f)
                                else MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    } else {
                        Spacer(Modifier.height(0.dp))
                    }
                    if (!isCurrentLocation) {
                        Icon(
                            Icons.Filled.Delete,
                            contentDescription = "Remove $name",
                            modifier = Modifier
                                .size(20.dp)
                                .clickable(onClick = { onDelete?.invoke() }),
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
                    label = { Text("City, village or place") },
                    singleLine = true,
                    trailingIcon = {
                        IconButton(onClick = { search() }) {
                            Icon(Icons.Filled.Search, contentDescription = "Search")
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                )
                if (searching) {
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                        CircularProgressIndicator(modifier = Modifier.size(24.dp))
                    }
                }
                results.forEach { candidate ->
                    OutlinedButton(onClick = { onAdd(candidate) }, modifier = Modifier.fillMaxWidth()) {
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
            OutlinedButton(onClick = onDismiss) { Text("Close") }
        },
    )
}
