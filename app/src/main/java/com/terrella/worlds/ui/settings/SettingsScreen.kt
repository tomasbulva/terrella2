package com.terrella.worlds.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Slider
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
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

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Settings", style = MaterialTheme.typography.headlineSmall)
        WeatherSection(s, settingsRepository, scope)
        WallpaperSection(s, settingsRepository, scope)
        LocationsSection(s, settingsRepository, scope)
        ExperienceSection(s, settingsRepository, scope)
        TelemetrySection(s, settingsRepository, scope)
        OutlinedButton(onClick = onNavigateToWorld, modifier = Modifier.fillMaxWidth()) {
            Text("Back to world")
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
        if (WeatherProviders.byId(s.weatherProviderId).requiresKey) {
            var key by remember(s.weatherProviderId) { mutableStateOf(s.owmApiKey) }
            OutlinedTextField(
                value = key,
                onValueChange = { key = it },
                label = { Text("API key (stored on this device only)") },
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(4.dp))
            Button(onClick = { scope.launch { repo.setOwmApiKey(key) } }, enabled = key.isNotBlank()) {
                Text("Save key")
            }
        }
        WeatherTestRow(s, repo)
    }
}

@Composable
private fun WeatherTestRow(s: Settings, repo: SettingsRepository) {
    val scope = rememberCoroutineScope()
    var result by remember { mutableStateOf<String?>(null) }
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(onClick = {
            scope.launch {
                result = runCatching {
                    val snap = WeatherProviders.byId(s.weatherProviderId)
                        .current(52.37, 4.89, s.owmApiKey.ifBlank { null })
                    "${snap.condition} · ${snap.tempC}°C · wind ${snap.windKmh} km/h · ${if (snap.isDay) "day" else "night"}"
                }.getOrElse { "Error: ${it.message}" }
            }
        }) { Text("Test fetch (Amsterdam)") }
        result?.let {
            Spacer(Modifier.height(4.dp))
            Text(it, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun WallpaperSection(s: Settings, repo: SettingsRepository, scope: kotlinx.coroutines.CoroutineScope) {
    val context = LocalContext.current
    val modes = listOf("static" to "Static image", "video" to "Live video (looping)", "off" to "None")
    SectionCard("Wallpaper") {
        modes.forEach { (id, label) ->
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                RadioButton(
                    selected = s.wallpaperMode == id,
                    onClick = {
                        scope.launch {
                            repo.setWallpaperMode(id)
                            TelemetryBridge.event("wallpaper_mode_changed", mapOf("mode" to id))
                        }
                    },
                )
                Text(label, style = MaterialTheme.typography.bodyLarge)
            }
        }
        if (s.wallpaperMode == "static") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = {
                    val r = WallpaperInstaller.setStatic(context, "diorama_night.jpg")
                    TelemetryBridge.event("wallpaper_set", mapOf("kind" to "static_night"))
                }) { Text("Night city") }
                Button(onClick = {
                    val r = WallpaperInstaller.setStatic(context, "diorama_day.jpg")
                    TelemetryBridge.event("wallpaper_set", mapOf("kind" to "static_day"))
                }) { Text("Day city") }
            }
        }
        if (s.wallpaperMode == "video") {
            LiveWallpaperButton()
        }
    }
}

@Composable
private fun LiveWallpaperButton() {
    val context = LocalContext.current
    OutlinedButton(onClick = {
        val component = android.content.ComponentName(context, com.terrella.worlds.wallpaper.VideoWallpaperService::class.java)
        val intent = IntentBuilder(component)
        runCatching { context.startActivity(intent) }
    }) { Text("Set looping video wallpaper") }
}

private fun IntentBuilder(component: android.content.ComponentName): android.content.Intent =
    android.content.Intent(android.app.WallpaperManager.ACTION_CHANGE_LIVE_WALLPAPER)
        .putExtra(android.app.WallpaperManager.EXTRA_LIVE_WALLPAPER_COMPONENT, component)

@Composable
private fun TelemetrySection(s: Settings, repo: SettingsRepository, scope: kotlinx.coroutines.CoroutineScope) {
    SectionCard("Usage tracking") {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Switch(
                checked = s.telemetryEnabled,
                onCheckedChange = {
                    scope.launch { repo.setTelemetryEnabled(it) }
                },
            )
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
    SectionCard("Quiet time") {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Switch(checked = s.quietEnabled, onCheckedChange = { scope.launch { repo.setQuietEnabled(it) } })
            Text(
                "Pause updates during quiet hours",
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.padding(start = 8.dp),
            )
        }
        Text(
            "Quiet window: ${s.quietStartHour}:00 – ${s.quietEndHour}:00 (hour pickers land next release)",
            style = MaterialTheme.typography.bodySmall,
        )
    }
    SectionCard("Units") {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Switch(checked = s.useMetric, onCheckedChange = { scope.launch { repo.setUseMetric(it) } })
            Text(
                if (s.useMetric) "Metric (°C, km/h)" else "Imperial (°F, mph)",
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.padding(start = 8.dp),
            )
        }
    }
    SectionCard("Notifications") {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Switch(checked = s.notificationsEnabled, onCheckedChange = { scope.launch { repo.setNotificationsEnabled(it) } })
            Text(
                "World status in notifications",
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.padding(start = 8.dp),
            )
        }
    }
}

@Composable
private fun SectionCard(title: String, content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            content()
        }
    }
}

private object TelemetryBridge {
    fun event(name: String, params: Map<String, String> = emptyMap()) =
        com.terrella.worlds.data.telemetry.Telemetry.event(name, params)
}
