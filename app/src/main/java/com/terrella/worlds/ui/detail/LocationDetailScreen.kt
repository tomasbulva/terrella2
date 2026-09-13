package com.terrella.worlds.ui.detail

import android.graphics.BitmapFactory
import android.media.MediaPlayer
import android.view.Surface
import android.view.TextureView
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.terrella.worlds.R
import com.terrella.worlds.data.LocationsRepository
import com.terrella.worlds.data.SettingsRepository
import com.terrella.worlds.data.catalog.AssetCatalogRepository
import com.terrella.worlds.data.catalog.AssetCatalogRepository.AssetState
import com.terrella.worlds.data.telemetry.Telemetry
import com.terrella.worlds.data.weather.WeatherProviders
import com.terrella.worlds.data.weather.WeatherSnapshot
import com.terrella.worlds.util.DioramaHumor
import com.terrella.worlds.util.Toasts
import com.terrella.worlds.wallpaper.WallpaperInstaller
import kotlinx.coroutines.launch
import java.io.File
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale
import java.util.TimeZone
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
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
    var showApplySheet by remember { mutableStateOf(false) }
    var applying by remember { mutableStateOf(false) }
    var weather by remember { mutableStateOf<WeatherSnapshot?>(null) }
    var liveWallpaperActive by remember { mutableStateOf(false) }

    val catalog = AssetCatalogRepository.get(context)
    val assetKey = remember(location) { location?.let { catalog.keyOf(it) } }
    val catalogStates by catalog.states.collectAsStateWithLifecycle()
    val assetState = assetKey?.let { catalogStates[it] }

    // Drive catalog/asset progress even if the user opens detail while cooking
    LaunchedEffect(location?.id, s.assetServerToken, s.assetServerUrl) {
        val loc = location ?: return@LaunchedEffect
        catalog.refresh(s, listOf(loc))
    }

    LaunchedEffect(location?.id, s.weatherProviderId) {
        val loc = location ?: return@LaunchedEffect
        runCatching {
            WeatherProviders.byId(s.weatherProviderId).current(loc.latitude, loc.longitude, s.owmApiKey.ifBlank { null })
        }.getOrNull()?.let { weather = it }
    }

    LaunchedEffect(Unit) { liveWallpaperActive = WallpaperInstaller.isOurLiveWallpaperActive(context) }

    val isAppliedHere = remember(s.appliedLocationId, liveWallpaperActive, location?.id) {
        s.appliedLocationId == location?.id && (liveWallpaperActive || s.wallpaperType == "static")
    }

    // Dynamic local time & date computation for the selected place
    val localTimeAndDate = remember(location?.timezone) {
        val tz = location?.timezone?.ifBlank { null }?.let { runCatching { TimeZone.getTimeZone(it) }.getOrNull() }
            ?: TimeZone.getDefault()
        val cal = Calendar.getInstance(tz)
        val timeFmt = SimpleDateFormat("HH:mm", Locale.getDefault()).apply { timeZone = tz }
        val dateFmt = SimpleDateFormat("EEE, MMM d", Locale.getDefault()).apply { timeZone = tz }
        Pair(timeFmt.format(cal.time), dateFmt.format(cal.time))
    }

    val ready = assetState as? AssetState.Ready

    fun applyToHome() {
        val loc = location ?: return
        scope.launch {
            applying = true
            locationsRepository.select(loc.id)
            val result = if (s.wallpaperType == "live") {
                WallpaperInstaller.launchLiveWallpaperPicker(context)
            } else {
                val st = catalogStates[catalog.keyOf(loc)] as? AssetState.Ready
                val isDay = weather?.isDay != false
                val bmp = st?.let {
                    WallpaperInstaller.captureVideoFrame(
                        (if (isDay) it.dayVideo else it.nightVideo).absolutePath,
                    )
                } ?: st?.let { BitmapFactory.decodeFile(it.poster.absolutePath) }
                if (bmp == null) WallpaperInstaller.Result.Error("no asset frame")
                else WallpaperInstaller.setStaticBitmap(context, bmp)
            }
            if (result is WallpaperInstaller.Result.Ok) {
                settingsRepository.setAppliedLocationId(loc.id)
                Toasts.show(context, "Wallpaper set for ${loc.name}")
                Telemetry.event("wallpaper_applied", mapOf("type" to s.wallpaperType, "location" to loc.name))
            } else if (result is WallpaperInstaller.Result.Error) {
                Toasts.show(context, "Couldn't set wallpaper: ${result.message}")
            }
            applying = false
        }
    }

    fun applyToLock() {
        val loc = location ?: return
        scope.launch {
            applying = true
            val st = catalogStates[catalog.keyOf(loc)] as? AssetState.Ready
            val isDay = weather?.isDay != false
            val bmp = st?.let {
                WallpaperInstaller.captureVideoFrame(
                    (if (isDay) it.dayVideo else it.nightVideo).absolutePath,
                )
            } ?: st?.let { BitmapFactory.decodeFile(it.poster.absolutePath) }
            if (bmp == null) {
                Toasts.show(context, "Couldn't capture a frame from the diorama")
            } else {
                val result = WallpaperInstaller.setLockScreenStatic(context, bmp)
                if (result is WallpaperInstaller.Result.Ok) {
                    settingsRepository.setAppliedLocationId(loc.id)
                    Toasts.show(context, "Lock screen set for ${loc.name}")
                    Telemetry.event("wallpaper_applied", mapOf("type" to "lock", "location" to loc.name))
                } else {
                    Toasts.show(context, "Couldn't set lock screen: ${(result as WallpaperInstaller.Result.Error).message}")
                }
            }
            applying = false
        }
    }

    fun removeWallpaper() {
        val loc = location ?: return
        scope.launch {
            WallpaperInstaller.clear(context)
            settingsRepository.setAppliedLocationId("")
            liveWallpaperActive = false
            Toasts.show(context, "Wallpaper removed")
            Telemetry.event("wallpaper_unset", mapOf("location" to loc.name))
        }
    }

    Box(modifier = Modifier.fillMaxSize()) {
        Image(
            painter = painterResource(id = R.drawable.app_background),
            contentDescription = null,
            modifier = Modifier.fillMaxSize(),
            contentScale = ContentScale.Crop,
        )

        if (ready == null) {
            // ── Pending: the diorama is still cooking — no broken loaders ──
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .statusBarsPadding()
                    .clickable(enabled = false) {},
                contentAlignment = Alignment.Center,
            ) {
                IconButton(
                    onClick = onNavigateBack,
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .padding(8.dp),
                ) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back", tint = Color.White)
                }
                PendingDiorama(state = assetState ?: AssetState.Missing, name = location?.name ?: "…")
            }
        } else {
            // ── Ready: fully rendered diorama video + weather effects + HUD ──
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(top = 110.dp, bottom = 120.dp),
                contentAlignment = Alignment.Center,
            ) {
                DioramaVideoPlayer(
                    video = if (weather?.isDay == false) ready.nightVideo else ready.dayVideo,
                    modifier = Modifier.fillMaxSize(),
                )
                WeatherEffectsOverlay(
                    weather = weather,
                    modifier = Modifier.fillMaxSize(),
                )
            }

            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .statusBarsPadding(),
            ) {
                // Top bar: back | name + country | 3-dot menu
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
                                text = { Text("Refresh weather") },
                                onClick = {
                                    showMenu = false
                                    scope.launch {
                                        val loc = location
                                        val snap = loc?.let {
                                            runCatching {
                                                WeatherProviders.byId(s.weatherProviderId)
                                                    .current(it.latitude, it.longitude, s.owmApiKey.ifBlank { null })
                                            }.getOrNull()
                                        }
                                        if (snap != null) weather = snap
                                    }
                                },
                            )
                            DropdownMenuItem(
                                text = { Text("Remove wallpaper") },
                                enabled = isAppliedHere || liveWallpaperActive,
                                onClick = {
                                    showMenu = false
                                    removeWallpaper()
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

                // Live Weather, Time & Date HUD Overlay
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 4.dp),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    // Time & Date Capsule
                    Row(
                        modifier = Modifier
                            .background(Color.Black.copy(alpha = 0.45f), RoundedCornerShape(20.dp))
                            .padding(horizontal = 12.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(Icons.Filled.Schedule, contentDescription = null, tint = Color.White.copy(alpha = 0.8f), modifier = Modifier.size(14.dp))
                        Spacer(Modifier.width(4.dp))
                        Text(
                            localTimeAndDate.first,
                            color = Color.White,
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold,
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            "·",
                            color = Color.White.copy(alpha = 0.5f),
                            style = MaterialTheme.typography.labelMedium,
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            localTimeAndDate.second,
                            color = Color.White.copy(alpha = 0.85f),
                            style = MaterialTheme.typography.labelMedium,
                        )
                    }

                    Spacer(Modifier.width(8.dp))

                    // Weather Condition & Temp Capsule
                    weather?.let { w ->
                        val temp = if (s.useMetric) "${w.tempC.roundToInt()}°C" else "${(w.tempC * 9 / 5 + 32).roundToInt()}°F"
                        Row(
                            modifier = Modifier
                                .background(Color.Black.copy(alpha = 0.45f), RoundedCornerShape(20.dp))
                                .padding(horizontal = 12.dp, vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                "$temp · ${w.condition.name.lowercase().replace('_', ' ')}",
                                color = Color.White,
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.SemiBold,
                            )
                        }
                    }
                }

                Spacer(Modifier.weight(1f))

                // The one and only action: blue, always "ready to go"
                Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    if (applying) {
                        CircularProgressIndicator(color = Color.White)
                    } else {
                        Box(
                            modifier = Modifier
                                .size(72.dp)
                                .background(MaterialTheme.colorScheme.primary, CircleShape)
                                .clickable { showApplySheet = true },
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                "SET",
                                color = Color.White,
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                }
                Text(
                    "SET WALLPAPER",
                    color = Color.White,
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 2.sp,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 8.dp, bottom = 32.dp),
                    textAlign = TextAlign.Center,
                )
            }

            if (showApplySheet) {
                ModalBottomSheet(onDismissRequest = { showApplySheet = false }) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 32.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(
                            "Where should the diorama live?",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(bottom = 4.dp),
                        )
                        Text(
                            if (s.wallpaperType == "live")
                                "Home screen uses the live video — Android asks for one confirm tap."
                            else
                                "Static diorama images apply instantly in the background.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            textAlign = TextAlign.Center,
                            modifier = Modifier.padding(horizontal = 32.dp, vertical = 8.dp),
                        )
                        ApplyOption("Home screen") { showApplySheet = false; applyToHome() }
                        ApplyOption("Lock screen") { showApplySheet = false; applyToLock() }
                        ApplyOption("Both") {
                            showApplySheet = false
                            applyToLock()
                            applyToHome()
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ApplyOption(label: String, onClick: () -> Unit) {
    Text(
        text = label,
        style = MaterialTheme.typography.titleMedium,
        color = MaterialTheme.colorScheme.primary,
        fontWeight = FontWeight.SemiBold,
        textAlign = TextAlign.Center,
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 32.dp, vertical = 14.dp),
    )
}

/** Pending state for the detail screen: same nerdy line + progress fill as the card. */
@Composable
private fun PendingDiorama(state: AssetState, name: String) {
    val progress = when (state) {
        is AssetState.Generating -> state.progress.coerceIn(0.03f, 0.98f)
        is AssetState.Failed -> 0f
        AssetState.Missing -> 0.03f
        is AssetState.Ready -> 1f
    }
    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(horizontal = 40.dp)) {
        Text(
            text = DioramaHumor.forName(name, ""),
            style = MaterialTheme.typography.titleMedium,
            fontStyle = FontStyle.Italic,
            color = Color.White,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(16.dp))
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(6.dp)
                .background(Color.White.copy(alpha = 0.15f), RoundedCornerShape(3.dp)),
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth(progress)
                    .height(6.dp)
                    .background(
                        Brush.horizontalGradient(
                            listOf(MaterialTheme.colorScheme.primary, Color.White.copy(alpha = 0.8f))
                        ),
                        RoundedCornerShape(3.dp),
                    ),
            )
        }
        if (state is AssetState.Failed) {
            Spacer(Modifier.height(12.dp))
            Text(
                "We'll pick this back up on your next visit.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
        }
    }
}

/** Seamless-loop diorama clip player; day/night clip chosen by the caller. */
@Composable
private fun DioramaVideoPlayer(video: File, modifier: Modifier) {
    var aspect by remember { mutableStateOf(720f / 1280f) }
    Box(modifier = modifier, contentAlignment = Alignment.Center) {
        key(video.absolutePath) {
            AndroidView(
                modifier = Modifier
                    .fillMaxSize()
                    .aspectRatio(aspect),
                factory = { ctx ->
                    TextureView(ctx).apply {
                        surfaceTextureListener = object : TextureView.SurfaceTextureListener {
                            var player: MediaPlayer? = null

                            override fun onSurfaceTextureAvailable(st: android.graphics.SurfaceTexture, w: Int, h: Int) {
                                val p = MediaPlayer()
                                player = p
                                runCatching {
                                    p.setDataSource(video.absolutePath)
                                    p.setSurface(Surface(st))
                                    p.isLooping = true
                                    p.setVolume(0f, 0f) // preview is silent too
                                    p.setOnVideoSizeChangedListener { _, vw, vh ->
                                        aspect = vw.toFloat() / vh.toFloat()
                                        st.setDefaultBufferSize(vw, vh)
                                    }
                                    p.setOnPreparedListener { it.start() }
                                    p.prepareAsync()
                                }.onFailure { p.release(); player = null }
                            }

                            override fun onSurfaceTextureSizeChanged(st: android.graphics.SurfaceTexture, w: Int, h: Int) = Unit
                            override fun onSurfaceTextureDestroyed(st: android.graphics.SurfaceTexture): Boolean {
                                runCatching { player?.release() }
                                player = null
                                return true
                            }
                            override fun onSurfaceTextureUpdated(st: android.graphics.SurfaceTexture) = Unit
                        }
                    }
                },
            )
        }
    }
}
