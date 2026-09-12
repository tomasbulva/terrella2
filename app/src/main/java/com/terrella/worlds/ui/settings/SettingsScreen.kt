package com.terrella.worlds.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.clickable
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.foundation.background
import androidx.compose.material.icons.filled.Bedtime
import androidx.compose.material.icons.filled.Wallpaper
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Cloud
import androidx.compose.material.icons.filled.Palette
import androidx.compose.material.icons.filled.Public
import androidx.compose.material.icons.filled.Straighten
import androidx.compose.material.icons.filled.Title
import androidx.compose.foundation.Image
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RangeSlider
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.terrella.worlds.data.Settings
import com.terrella.worlds.data.SettingsRepository
import com.terrella.worlds.data.weather.WeatherProviders
import com.terrella.worlds.wallpaper.WallpaperInstaller
import kotlinx.coroutines.launch

@Composable
fun SettingsScreen(
    onNavigateToWorld: () -> Unit,
    settingsRepository: SettingsRepository,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val settings by settingsRepository.settings.collectAsStateWithLifecycle(initialValue = null)
    val s = settings ?: return

    Box(modifier = Modifier.fillMaxSize()) {
        Image(
            painter = painterResource(com.terrella.worlds.R.drawable.app_background),
            contentDescription = null,
            modifier = Modifier.fillMaxSize(),
            contentScale = ContentScale.Crop,
        )
        Column(
            modifier = Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Spacer(Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "Settings",
                    style = MaterialTheme.typography.headlineLarge,
                    fontWeight = FontWeight.Bold,
                    color = Color.White,
                )
                IconButton(onClick = onNavigateToWorld) {
                    Icon(
                        imageVector = Icons.Filled.Close,
                        contentDescription = "Close",
                        tint = Color.White,
                    )
                }
            }
            Spacer(Modifier.height(16.dp))
            WeatherSection(s, settingsRepository, scope)
            WallpaperSection(s, settingsRepository, scope)
            LocationsSection(s, settingsRepository, scope)
            ExperienceSection(s, settingsRepository, scope)
            TelemetrySection(s, settingsRepository, scope)
            Spacer(Modifier.height(32.dp))
        }
    }
}

@Composable
private fun WeatherSection(s: Settings, repo: SettingsRepository, scope: kotlinx.coroutines.CoroutineScope) {
    SectionCard("Weather source") {
        WeatherProviders.all.forEach { provider ->
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth(),
            ) {
                RadioButton(
                    selected = s.weatherProviderId == provider.id,
                    onClick = {
                        scope.launch {
                            repo.setWeatherProvider(provider.id)
                            TelemetryBridge.event("weather_source_changed", mapOf("source" to provider.id))
                        }
                    },
                )
                Text(provider.displayName, style = MaterialTheme.typography.bodyLarge)
            }
        }
        WeatherTestRow(s, repo)
    }
}

@Composable
private fun WeatherTestRow(s: Settings, repo: SettingsRepository) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var testing by remember { mutableStateOf(false) }
    OutlinedButton(onClick = {
        if (testing) return@OutlinedButton
        testing = true
        scope.launch {
            runCatching {
                val snap = WeatherProviders.byId(s.weatherProviderId)
                    .current(52.37, 4.89, s.owmApiKey.ifBlank { null })
                "${snap.condition.name.lowercase().replace('_', ' ')} · ${snap.tempC}°C · wind ${snap.windKmh} km/h · ${if (snap.isDay) "day" else "night"}"
            }.fold(
                onSuccess = { com.terrella.worlds.util.Toasts.show(context, it) },
                onFailure = { com.terrella.worlds.util.Toasts.show(context, "Weather fetch failed: ${it.message}") },
            )
            testing = false
        }
    }, enabled = !testing) { Text(if (testing) "Fetching…" else "Test fetch (Amsterdam)") }
}

@Composable
private fun WallpaperSection(s: Settings, repo: SettingsRepository, scope: kotlinx.coroutines.CoroutineScope) {
    SectionCard("Wallpaper type", icon = Icons.Filled.Wallpaper) {
        Text(
            "Applied by the SET AS ACTIVE button on each place. Live is the default.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp))
                .padding(4.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            listOf("live" to "Live video", "static" to "Static image").forEach { (id, label) ->
                val selected = s.wallpaperType == id
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .background(
                            if (selected) MaterialTheme.colorScheme.primary else Color.Transparent,
                            RoundedCornerShape(9.dp),
                        )
                        .clickable {
                            scope.launch { repo.setWallpaperType(id) }
                            TelemetryBridge.event("wallpaper_type_changed", mapOf("type" to id))
                        }
                        .padding(vertical = 10.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        label,
                        color = if (selected) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
                        style = MaterialTheme.typography.labelLarge,
                    )
                }
            }
        }
    }
    SectionCard("Render on wallpaper", icon = Icons.Filled.Wallpaper) {
        Text(
            "Render the floating diorama tile into the wallpaper via 3D (available when the render pipeline lands).",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Switch(checked = s.renderOnWallpaper, onCheckedChange = { scope.launch { repo.setRenderOnWallpaper(it) } })
            Text(
                "Use 3D tile on the wallpaper",
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.padding(start = 8.dp),
            )
        }
    }
}

@Composable
private fun LocationsSection(s: Settings, repo: SettingsRepository, scope: kotlinx.coroutines.CoroutineScope) {
    val context = LocalContext.current
    SectionCard("Wallpaper refresh") {
        Text("Every ${s.refreshHours}h", style = MaterialTheme.typography.bodyLarge)
        var hours by remember { mutableStateOf(s.refreshHours.toFloat()) }
        Slider(
            value = hours,
            onValueChange = { hours = it },
            onValueChangeFinished = { scope.launch { repo.setRefreshHours(hours.toInt().coerceAtLeast(1)) } },
            valueRange = 1f..24f,
            steps = 22,
        )
        OutlinedButton(onClick = {
            scope.launch {
                com.terrella.worlds.data.telemetry.Telemetry.event("wallpaper_refresh_manual")
                androidx.work.WorkManager.getInstance(context).enqueue(
                    androidx.work.OneTimeWorkRequestBuilder<com.terrella.worlds.worker.WallpaperUpdateWorker>().build()
                )
            }
        }) { Text("Update wallpaper now") }
    }
}

@Composable
private fun ExperienceSection(s: Settings, repo: SettingsRepository, scope: kotlinx.coroutines.CoroutineScope) {
    SectionCard("Quiet time", icon = Icons.Filled.Bedtime) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text("Enabled", style = MaterialTheme.typography.bodyLarge)
            Switch(
                checked = s.quietEnabled,
                onCheckedChange = { scope.launch { repo.setQuietEnabled(it) } },
            )
        }

        if (s.quietEnabled) {
            val start = remember(s.quietStartHour) { mutableStateOf(s.quietStartHour.toFloat()) }
            val end = remember(s.quietEndHour) { mutableStateOf(s.quietEndHour.toFloat()) }

            Text(
                text = "Active window: %02d:00 – %02d:00".format(start.value.toInt(), end.value.toInt()),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.height(8.dp))

            // Two-handle range slider (0–24h, 25 discrete positions) — T1 pattern
            RangeSlider(
                value = start.value..end.value,
                onValueChange = { range ->
                    start.value = range.start
                    end.value = range.endInclusive
                },
                onValueChangeFinished = {
                    scope.launch {
                        repo.setQuietStartHour(start.value.toInt())
                        repo.setQuietEndHour(end.value.toInt())
                    }
                },
                valueRange = 0f..24f,
                steps = 23,
                modifier = Modifier.fillMaxWidth(),
                colors = SliderDefaults.colors(
                    thumbColor = MaterialTheme.colorScheme.primary,
                    activeTrackColor = MaterialTheme.colorScheme.primary,
                    inactiveTrackColor = MaterialTheme.colorScheme.outline,
                ),
            )

            // Hour labels
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                listOf(0, 4, 8, 12, 16, 20, 24).forEach { hour ->
                    Text(
                        text = "$hour",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            Spacer(Modifier.height(8.dp))

            // Live readout: updates inside the active window (T1's image-count pattern)
            val updateCount = com.terrella.worlds.util.QuietTimeUtils.calculateImages(
                start.value.toInt(),
                end.value.toInt(),
                s.refreshHours,
            )
            Text(
                text = buildAnnotatedString {
                    append("Terrella will update your wallpaper ")
                    withStyle(SpanStyle(color = MaterialTheme.colorScheme.primary)) {
                        append("$updateCount ${if (updateCount == 1) "time" else "times"}")
                    }
                },
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.fillMaxWidth(),
                textAlign = TextAlign.Center,
            )
            Text(
                text = "Wallpapers only update between the slider handles to conserve energy and reduce cost.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
    SectionCard("Units", icon = Icons.Filled.Straighten) {
        listOf(true to "Metric (°C, km/h)", false to "Imperial (°F, mph)").forEach { (metric, label) ->
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth(),
            ) {
                RadioButton(
                    selected = s.useMetric == metric,
                    onClick = { scope.launch { repo.setUseMetric(metric) } },
                )
                Text(label, style = MaterialTheme.typography.bodyLarge)
            }
        }
    }
    ArtStyleSection(s, repo, scope)
    SectionCard("Title in image", icon = Icons.Filled.Title) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Switch(checked = s.showTitleInImage, onCheckedChange = { scope.launch { repo.setShowTitleInImage(it) } })
            Text(
                "Show the place name in the diorama",
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.padding(start = 8.dp),
            )
        }
    }
}


private data class ArtStyleOption(val id: String, val name: String, val tagline: String, val imageRes: Int)

private val ART_STYLES = listOf(
    ArtStyleOption("original", "Original", "Clean & minimal", com.terrella.worlds.R.drawable.art_style_original),
    ArtStyleOption("video_game", "Video Game", "Action packed", com.terrella.worlds.R.drawable.art_style_video_game),
    ArtStyleOption("lego", "Color Bricks", "Brick by brick", com.terrella.worlds.R.drawable.art_style_lego),
    ArtStyleOption("trolls_claymation", "Glitter Claymation", "Glittery & fun", com.terrella.worlds.R.drawable.art_style_trolls_claymation),
    ArtStyleOption("back_to_the_future", "Back to the 80's", "Retro futuristic", com.terrella.worlds.R.drawable.art_style_back_to_the_future),
    ArtStyleOption("lord_of_the_ring", "Halfling Village", "Medieval fantasy", com.terrella.worlds.R.drawable.art_style_lord_of_the_ring),
    ArtStyleOption("harry_potter", "Young Wizard", "Magical world", com.terrella.worlds.R.drawable.art_style_harry_potter),
    ArtStyleOption("zombie_apocalypse", "Zombie Apocalypse", "Post-apocalyptic", com.terrella.worlds.R.drawable.art_style_zombie_apocalypse),
    ArtStyleOption("plastic_dollhouse", "Plastic Dollhouse", "Toy world", com.terrella.worlds.R.drawable.art_style_isometric),
)

@Composable
private fun ArtStyleSection(s: Settings, repo: SettingsRepository, scope: kotlinx.coroutines.CoroutineScope) {
    SectionCard("Art style", icon = Icons.Filled.Palette) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            ART_STYLES.forEach { style ->
                val selected = s.artStyle == style.id
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier
                        .width(110.dp)
                        .border(
                            width = if (selected) 2.dp else 1.dp,
                            color = if (selected) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.outline,
                            shape = RoundedCornerShape(12.dp),
                        )
                        .clip(RoundedCornerShape(12.dp))
                        .clickable {
                            scope.launch { repo.setArtStyle(style.id) }
                            TelemetryBridge.event("art_style_changed", mapOf("style" to style.id))
                        }
                        .padding(6.dp),
                ) {
                    androidx.compose.foundation.Image(
                        painter = androidx.compose.ui.res.painterResource(style.imageRes),
                        contentDescription = style.name,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(80.dp)
                            .clip(RoundedCornerShape(8.dp)),
                        contentScale = androidx.compose.ui.layout.ContentScale.Crop,
                    )
                    Text(
                        style.name,
                        style = MaterialTheme.typography.labelMedium,
                        color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                    )
                    Text(
                        style.tagline,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                    )
                }
            }
        }
    }
}


@Composable
private fun TelemetrySection(s: Settings, repo: SettingsRepository, scope: kotlinx.coroutines.CoroutineScope) {
    SectionCard("Usage tracking", icon = Icons.Filled.Public) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Switch(checked = s.telemetryEnabled, onCheckedChange = { scope.launch { repo.setTelemetryEnabled(it) } })
            Text(
                "Share anonymous usage events",
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.padding(start = 8.dp),
            )
        }
        Text(
            "Helps us learn which features you actually use. Events go only to our own server, " +
                "batches every 6h, and contain a random install id — never ads, never third parties.",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}


@Composable
private fun SectionCard(
    title: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector? = null,
    content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                icon?.let { Icon(it, contentDescription = null, tint = MaterialTheme.colorScheme.primary) }
                Text(title, style = MaterialTheme.typography.titleMedium)
            }
            content()
        }
    }
}

private object TelemetryBridge {
    fun event(name: String, params: Map<String, String> = emptyMap()) =
        com.terrella.worlds.data.telemetry.Telemetry.event(name, params)
}
