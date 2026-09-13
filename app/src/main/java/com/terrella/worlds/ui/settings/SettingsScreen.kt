package com.terrella.worlds.ui.settings

import android.widget.Toast
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Bedtime
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Cloud
import androidx.compose.material.icons.filled.Palette
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Straighten
import androidx.compose.material.icons.filled.Wallpaper
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RangeSlider
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.terrella.worlds.R
import com.terrella.worlds.data.Settings
import com.terrella.worlds.data.SettingsRepository
import com.terrella.worlds.data.weather.WeatherProviders
import com.terrella.worlds.wallpaper.WallpaperRefreshWorker
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

@Composable
fun SettingsScreen(
    onNavigateBack: () -> Unit,
    settingsRepository: SettingsRepository,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val settings by settingsRepository.settings.collectAsState(initial = null)
    val s = settings ?: return

    Box(modifier = Modifier.fillMaxSize()) {
        Image(
            painter = painterResource(id = R.drawable.app_background),
            contentDescription = null,
            modifier = Modifier.fillMaxSize(),
            contentScale = ContentScale.Crop,
        )

        Column(
            modifier = Modifier
                .fillMaxSize()
                .statusBarsPadding(),
        ) {
            // Header bar with X close button
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 8.dp, vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = onNavigateBack) {
                    Icon(Icons.Filled.Close, contentDescription = "Close", tint = Color.White)
                }
                Text(
                    "Settings",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = Color.White,
                    modifier = Modifier.padding(start = 4.dp),
                )
            }

            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                // Weather source
                WeatherSourceSection(s, settingsRepository)

                // Wallpaper type
                WallpaperTypeSection(s, settingsRepository)

                // Wallpaper refresh
                WallpaperRefreshSection(s, settingsRepository)

                // Quiet time
                QuietTimeSection(s, settingsRepository)

                // Units
                UnitsSection(s, settingsRepository)

                // Art style
                ArtStyleSection(s, settingsRepository)

                Spacer(Modifier.height(32.dp))
            }
        }
    }
}

@Composable
private fun SectionCard(
    title: String,
    icon: ImageVector,
    content: @Composable () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(
            containerColor = Color(0xFF1E1E2E).copy(alpha = 0.85f),
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(bottom = 12.dp),
            ) {
                Icon(icon, contentDescription = null, tint = Color(0xFF90CAF9), modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(8.dp))
                Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = Color.White)
            }
            content()
        }
    }
}

@Composable
private fun WeatherSourceSection(s: Settings, repo: SettingsRepository) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var testResult by remember { mutableStateOf<String?>(null) }
    var testing by remember { mutableStateOf(false) }

    SectionCard("Weather source", icon = Icons.Filled.Cloud) {
        WeatherProviders.all.forEach { p ->
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { scope.launch { repo.setWeatherProvider(p.id) } }
                    .padding(vertical = 4.dp),
            ) {
                RadioButton(
                    selected = s.weatherProviderId == p.id,
                    onClick = { scope.launch { repo.setWeatherProvider(p.id) } },
                )
                Spacer(Modifier.width(8.dp))
                Text(p.name, color = Color.White)
            }
        }

        if (s.weatherProviderId == "owm") {
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = s.owmApiKey,
                onValueChange = { scope.launch { repo.setOwmApiKey(it) } },
                label = { Text("OpenWeatherMap API Key") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
        }

        Spacer(Modifier.height(8.dp))
        Button(
            onClick = {
                testing = true
                testResult = null
                scope.launch {
                    val p = WeatherProviders.byId(s.weatherProviderId)
                    val r = runCatching { p.current(52.3676, 4.9041, s.owmApiKey.ifBlank { null }) }
                    testing = false
                    testResult = r.fold(
                        onSuccess = { "${it.tempC}°C, ${it.condition.name.lowercase()} via ${it.provider}" },
                        onFailure = { it.message ?: "Failed" },
                    )
                }
            },
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2A2B3D)),
        ) {
            Text(if (testing) "Testing…" else "Test fetch (Amsterdam)", color = Color.White)
        }
        testResult?.let {
            Spacer(Modifier.height(4.dp))
            Text(it, style = MaterialTheme.typography.bodySmall, color = Color(0xFF81C784))
        }
    }
}

@Composable
private fun WallpaperTypeSection(s: Settings, repo: SettingsRepository) {
    val scope = rememberCoroutineScope()
    SectionCard("Wallpaper type", icon = Icons.Filled.Wallpaper) {
        Text(
            "Applied by the SET AS ACTIVE button on each place. Live launches the system picker; Static applies directly.",
            style = MaterialTheme.typography.bodySmall,
            color = Color.White.copy(alpha = 0.7f),
            modifier = Modifier.padding(bottom = 8.dp),
        )
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val types = listOf("live" to "Live video", "static" to "Static image")
            types.forEach { (type, label) ->
                val selected = s.wallpaperType == type
                Button(
                    onClick = { scope.launch { repo.setWallpaperType(type) } },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (selected) MaterialTheme.colorScheme.primary else Color(0xFF2A2B3D),
                    ),
                ) {
                    Text(label, color = Color.White)
                }
            }
        }
    }
}

@Composable
private fun WallpaperRefreshSection(s: Settings, repo: SettingsRepository) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val intervals = listOf(
        0 to "Once",
        1 to "1h",
        2 to "2h",
        3 to "3h",
        4 to "4h",
        5 to "5h",
        6 to "6h",
    )
    val currentIndex = intervals.indexOfFirst { it.first == s.refreshIntervalHours }.coerceAtLeast(0)

    SectionCard("Wallpaper refresh", icon = Icons.Filled.Refresh) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                if (s.refreshIntervalHours == 0) "Manual only" else "Every ${s.refreshIntervalHours}h",
                color = Color.White,
                fontWeight = FontWeight.Medium,
            )
        }
        Slider(
            value = currentIndex.toFloat(),
            onValueChange = { idx ->
                val hours = intervals[idx.roundToInt().coerceIn(0, intervals.size - 1)].first
                scope.launch {
                    repo.setRefreshInterval(hours)
                    WallpaperRefreshWorker.schedule(context, hours)
                }
            },
            valueRange = 0f..(intervals.size - 1).toFloat(),
            steps = intervals.size - 2,
        )
        Spacer(Modifier.height(8.dp))
        Button(
            onClick = {
                WallpaperRefreshWorker.runOnce(context)
                Toast.makeText(context, "Updating wallpaper…", Toast.LENGTH_SHORT).show()
            },
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2A2B3D)),
        ) {
            Text("Update wallpaper now", color = Color.White)
        }
    }
}

@Composable
private fun QuietTimeSection(s: Settings, repo: SettingsRepository) {
    val scope = rememberCoroutineScope()

    SectionCard("Quiet time", icon = Icons.Filled.Bedtime) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Enabled", color = Color.White)
            Switch(checked = s.quietTimeEnabled, onCheckedChange = { scope.launch { repo.setQuietTimeEnabled(it) } })
        }

        if (s.quietTimeEnabled) {
            Spacer(Modifier.height(8.dp))
            Text(
                "No wallpaper updates between ${s.quietTimeStartHour}:00 and ${s.quietTimeEndHour}:00",
                style = MaterialTheme.typography.bodySmall,
                color = Color.White.copy(alpha = 0.7f),
            )
            var range by remember(s.quietTimeStartHour, s.quietTimeEndHour) {
                mutableStateOf(s.quietTimeStartHour.toFloat()..s.quietTimeEndHour.toFloat())
            }
            RangeSlider(
                value = range,
                onValueChange = { range = it },
                onValueChangeFinished = {
                    scope.launch {
                        repo.setQuietTimeHours(range.start.roundToInt(), range.endInclusive.roundToInt())
                    }
                },
                valueRange = 0f..24f,
                steps = 23,
            )
        }
    }
}

@Composable
private fun UnitsSection(s: Settings, repo: SettingsRepository) {
    val scope = rememberCoroutineScope()

    SectionCard("Units", icon = Icons.Filled.Straighten) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val options = listOf(true to "Metric (°C, km/h)", false to "Imperial (°F, mph)")
            options.forEach { (metric, label) ->
                val selected = s.useMetric == metric
                Button(
                    onClick = { scope.launch { repo.setUseMetric(metric) } },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (selected) MaterialTheme.colorScheme.primary else Color(0xFF2A2B3D),
                    ),
                ) {
                    Text(label, color = Color.White, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

@Composable
private fun ArtStyleSection(s: Settings, repo: SettingsRepository) {
    val scope = rememberCoroutineScope()
    val styles = listOf(
        "default" to "Original",
        "isometric" to "Isometric 3D",
        "voxel" to "Color Bricks",
        "clay" to "Claymation",
        "retro" to "Back to 80s",
        "fantasy" to "Wizard",
    )

    SectionCard("Art style", icon = Icons.Filled.Palette) {
        LazyRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            contentPadding = PaddingValues(vertical = 4.dp),
        ) {
            items(styles) { (id, name) ->
                val selected = s.artStyle == id
                Card(
                    modifier = Modifier
                        .clickable { scope.launch { repo.setArtStyle(id) } },
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = if (selected) MaterialTheme.colorScheme.primary else Color(0xFF2A2B3D),
                    ),
                ) {
                    Text(
                        name,
                        color = Color.White,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
                    )
                }
            }
        }
    }
}
