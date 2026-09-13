package com.terrella.worlds.data.catalog

import android.content.Context
import android.util.Log
import com.terrella.worlds.data.SavedLocation
import com.terrella.worlds.data.Settings
import com.terrella.worlds.data.SettingsRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.File
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.net.URLEncoder

/**
 * Client for the Terrella Asset Service (see backend/CONTRACT.md).
 *
 * Drives the new-user path: for every saved location without a downloaded
 * diorama it requests generation (or picks a catalog hit), polls real
 * progress, and downloads day/night video clips + poster into app storage.
 */
class AssetCatalogRepository private constructor(private val context: Context) {

    sealed interface AssetState {
        data object Missing : AssetState
        data class Generating(val progress: Float, val stage: String) : AssetState
        data class Failed(val message: String) : AssetState
        data class Ready(val poster: File, val dayVideo: File, val nightVideo: File) : AssetState
    }

    @Serializable
    private data class CatalogAsset(
        val key: String,
        val name: String = "",
        val country: String = "",
        val day_video: String,
        val night_video: String,
        val poster: String,
        val glb: String? = null,
        val duration_s: Int = 6,
    )

    @Serializable
    private data class CatalogResponse(val version: Int = 0, val assets: List<CatalogAsset> = emptyList())

    @Serializable
    private data class JobRequest(val name: String, val country: String, val lat: Double, val lon: Double)

    @Serializable
    private data class JobResponse(
        val job_id: String? = null,
        val key: String? = null,
        val status: String,
        val progress: Float = 0f,
        val stage: String? = null,
        val error: String? = null,
        val asset: CatalogAsset? = null,
    )

    private val json = Json { ignoreUnknownKeys = true }
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val refreshMutex = Mutex()

    private val _states = MutableStateFlow<Map<String, AssetState>>(emptyMap())
    val states: StateFlow<Map<String, AssetState>> = _states

    private val inFlightJobs = mutableMapOf<String, String>() // key -> job id

    // ---- key normalization (must match backend/CONTRACT.md) ----

    fun keyOf(location: SavedLocation): String =
        "${location.name},${location.country}".trim().lowercase().replace(Regex("\\s+"), " ")

    fun assetDir(key: String): File = File(File(context.filesDir, "dioramas"), key)

    private fun posterFile(key: String) = File(assetDir(key), "poster.jpg")
    private fun dayFile(key: String) = File(assetDir(key), "day.mp4")
    private fun nightFile(key: String) = File(assetDir(key), "night.mp4")

    /** Ready purely from what is on disk — no network. */
    private fun diskState(key: String): AssetState =
        if (posterFile(key).exists() && dayFile(key).exists() && nightFile(key).exists()) {
            AssetState.Ready(posterFile(key), dayFile(key), nightFile(key))
        } else AssetState.Missing

    /**
     * Refreshes the catalog and drives every location to Ready:
     * downloaded files -> catalog download -> job create + poll.
     * Safe to call on every app entry; no-ops when the token is unset.
     */
    fun refresh(settings: Settings, locations: List<SavedLocation>) {
        if (settings.assetServerToken.isBlank() || locations.isEmpty()) return
        scope.launch {
            refreshMutex.withLock {
                // Seed state from disk so the UI never flickers
                locations.forEach { loc ->
                    val key = keyOf(loc)
                    if (_states.value[key] !is AssetState.Ready) {
                        _states.value = _states.value + (key to diskState(key))
                    }
                }
                val catalog = runCatching { fetchCatalog(settings) }.getOrNull()
                locations.forEach { loc ->
                    val key = keyOf(loc)
                    val current = _states.value[key] ?: AssetState.Missing
                    if (current is AssetState.Ready) return@forEach
                    val hit = catalog?.assets?.firstOrNull { it.key == key }
                    if (hit != null) {
                        _states.value = _states.value + (key to AssetState.Generating(0.95f, "download"))
                        val ok = runCatching {
                            downloadAll(settings, key, hit)
                        }.getOrDefault(false)
                        _states.value = _states.value + (key to if (ok) diskState(key) else AssetState.Missing)
                        if (!ok) Log.w(TAG, "download failed for $key")
                    } else if (current is AssetState.Missing || current is AssetState.Failed) {
                        requestJob(settings, loc, key)
                    }
                }
            }
        }
    }

    private suspend fun fetchCatalog(settings: Settings): CatalogResponse? {
        val body = api(url(settings, "/catalog"), settings) { it.inputStream.readBytes() }
        return body?.let { json.decodeFromString<CatalogResponse>(String(it)) }
    }

    private fun requestJob(settings: Settings, loc: SavedLocation, key: String) {
        if (inFlightJobs.containsKey(key)) return
        scope.launch {
            val payload = json.encodeToString(
                JobRequest.serializer(),
                JobRequest(loc.name.trim(), loc.country.trim(), loc.latitude, loc.longitude),
            )
            val resp = runCatching {
                post(url(settings, "/jobs"), payload, settings)
            }.getOrNull()
            if (resp == null) {
                _states.value = _states.value + (key to AssetState.Missing)
                return@launch
            }
            when {
                resp.status == "ready" && resp.asset != null -> {
                    _states.value = _states.value + (key to AssetState.Generating(0.95f, "download"))
                    val ok = runCatching { downloadAll(settings, key, resp.asset) }.getOrDefault(false)
                    _states.value = _states.value + (key to if (ok) diskState(key) else AssetState.Failed("download failed"))
                }
                resp.job_id != null -> {
                    inFlightJobs[key] = resp.job_id
                    _states.value = _states.value + (key to AssetState.Generating(resp.progress, resp.stage ?: "queued"))
                    pollJob(settings, key, resp.job_id)
                }
                else -> _states.value = _states.value + (key to AssetState.Failed(resp.error ?: "unexpected response"))
            }
        }
    }

    private fun pollJob(settings: Settings, key: String, jobId: String) {
        scope.launch {
            val deadline = System.currentTimeMillis() + POLL_TIMEOUT_MS
            while (System.currentTimeMillis() < deadline) {
                delay(POLL_INTERVAL_MS)
                val resp = runCatching {
                    val body = api(url(settings, "/jobs/$jobId"), settings) { it.inputStream.readBytes() }
                    body?.let { json.decodeFromString<JobResponse>(String(it)) }
                }.getOrNull()
                if (resp == null) continue // transient network blip — keep polling
                when (resp.status) {
                    "ready" -> {
                        val asset = resp.asset
                        _states.value = _states.value + (key to AssetState.Generating(0.95f, "download"))
                        val ok = asset != null && runCatching { downloadAll(settings, key, asset) }.getOrDefault(false)
                        _states.value = _states.value + (key to if (ok) diskState(key) else AssetState.Failed("download failed"))
                        inFlightJobs.remove(key)
                        return@launch
                    }
                    "failed" -> {
                        _states.value = _states.value + (key to AssetState.Failed(resp.error ?: "generation failed"))
                        inFlightJobs.remove(key)
                        return@launch
                    }
                    else -> _states.value =
                        _states.value + (key to AssetState.Generating(resp.progress, resp.stage ?: ""))
                }
            }
            _states.value = _states.value + (key to AssetState.Failed("timed out"))
            inFlightJobs.remove(key)
        }
    }

    private suspend fun downloadAll(settings: Settings, key: String, asset: CatalogAsset): Boolean {
        assetDir(key).mkdirs()
        val ok = listOf(
            Triple(asset.day_video, dayFile(key), 10_000_000L),
            Triple(asset.night_video, nightFile(key), 10_000_000L),
            Triple(asset.poster, posterFile(key), 5_000_000L),
        ).all { (path, target, max) ->
            runCatching {
                downloadBinary(url(settings, path), settings, target, max)
            }.getOrElse {
                Log.w(TAG, "download ${target.name} failed: ${it.message}")
                false
            }
        }
        return ok
    }

    // ---- HTTP plumbing (HttpURLConnection to match the app's zero-dep stack) ----

    private fun url(settings: Settings, path: String): String {
        val p = path.trim()
        if (p.startsWith("http")) return p
        val base = settings.assetServerUrl.trimEnd('/')
        // Root-relative paths (e.g. "/terrella/assets/<key>/day.mp4" from the
        // catalog) must resolve against the DOMAIN root — joining them onto the
        // API base would double the prefix and 404.
        return if (p.startsWith("/")) absoluteFor(base, p) else "$base/$p"
    }

    private fun absoluteFor(base: String, rootPath: String): String =
        runCatching { URI(base).resolve(rootPath).toString() }.getOrDefault(base + rootPath)

    private fun <T> api(target: String, settings: Settings, block: (HttpURLConnection) -> T): T? {
        val conn = (URL(target).openConnection() as HttpURLConnection).apply {
            connectTimeout = 10_000
            readTimeout = 30_000
            setRequestProperty("Authorization", "Bearer ${settings.assetServerToken}")
            setRequestProperty("Accept", "application/json")
        }
        return runCatching { block(conn) }
            .onFailure { Log.w(TAG, "GET $target failed: ${it.message}") }
            .getOrNull()
            .also { conn.disconnect() }
    }

    private fun post(target: String, payload: String, settings: Settings): JobResponse? {
        val conn = (URL(target).openConnection() as HttpURLConnection).apply {
            connectTimeout = 10_000
            readTimeout = 30_000
            requestMethod = "POST"
            doOutput = true
            setRequestProperty("Authorization", "Bearer ${settings.assetServerToken}")
            setRequestProperty("Content-Type", "application/json")
        }
        return runCatching {
            conn.outputStream.use { it.write(payload.toByteArray()) }
            val stream = if (conn.responseCode in 200..299) conn.inputStream else conn.errorStream
            val body = stream?.readBytes()?.toString(Charsets.UTF_8) ?: ""
            if (body.isBlank()) null else json.decodeFromString<JobResponse>(body)
        }.onFailure { Log.w(TAG, "POST $target failed: ${it.message}") }
            .getOrNull()
            .also { conn.disconnect() }
    }

    private fun downloadBinary(target: String, settings: Settings, targetFile: File, maxBytes: Long): Boolean {
        val tmp = File(targetFile.absolutePath + ".part")
        val conn = (URL(target).openConnection() as HttpURLConnection).apply {
            connectTimeout = 10_000
            readTimeout = 60_000
            setRequestProperty("Authorization", "Bearer ${settings.assetServerToken}")
        }
        try {
            if (conn.responseCode !in 200..299) return false
            conn.inputStream.use { input ->
                tmp.outputStream().use { out ->
                    val buf = ByteArray(64 * 1024)
                    var total = 0L
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        total += n
                        if (total > maxBytes) return false
                        out.write(buf, 0, n)
                    }
                }
            }
            return if (tmp.length() > 0) {
                if (targetFile.exists()) targetFile.delete()
                tmp.renameTo(targetFile)
            } else {
                tmp.delete()
                false
            }
        } finally {
            conn.disconnect()
        }
    }

    companion object {
        private const val TAG = "AssetCatalog"
        private const val POLL_INTERVAL_MS = 5_000L
        private const val POLL_TIMEOUT_MS = 45 * 60_000L

        @Volatile private var instance: AssetCatalogRepository? = null
        fun get(context: Context): AssetCatalogRepository =
            instance ?: synchronized(this) {
                instance ?: AssetCatalogRepository(context.applicationContext).also { instance = it }
            }
    }
}
