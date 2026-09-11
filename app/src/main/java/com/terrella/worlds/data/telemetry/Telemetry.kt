package com.terrella.worlds.data.telemetry

import android.content.Context
import com.terrella.worlds.data.SettingsRepository
import com.terrella.worlds.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

/**
 * Minimal, privacy-light analytics:
 *  - events appended to a local JSONL queue
 *  - batched upload to OUR backend (BuildConfig.TELEMETRY_URL, empty = disabled)
 *  - user-visible opt-out (Settings), no third-party SDK, no ad identifiers
 *  - only a random install UUID leaves the device
 */
object Telemetry {
    private const val MAX_QUEUE_LINES = 500
    private const val MAX_BATCH = 100

    private var appContext: Context? = null
    private var installId: String? = null

    fun init(context: Context) {
        appContext = context.applicationContext
    }

    fun event(name: String, params: Map<String, String> = emptyMap()) {
        val ctx = appContext ?: return
        // Opt-out check is synchronous; settings write is rare.
        val enabled = kotlinx.coroutines.runBlocking {
            try { SettingsRepository.get(ctx).current().telemetryEnabled } catch (e: Exception) { false }
        }
        if (!enabled) return
        val line = buildJsonObject {
            put("event", name)
            put("ts", System.currentTimeMillis() / 1000)
            put("install_id", installId ?: UUID.randomUUID().toString().also { installId = it })
            params.forEach { (k, v) -> put(k, v) }
        }.toString()
        runCatching {
            queueFile(ctx).apply {
                appendText(line + "\n")
                if (readLines().size > MAX_QUEUE_LINES) {
                    writeText(readLines().takeLast(MAX_QUEUE_LINES).joinToString("\n") + "\n")
                }
            }
        }
    }

    /** Upload queued events. Returns number of events sent. Safe to call from WorkManager. */
    suspend fun flush(): Int = withContext(Dispatchers.IO) {
        val ctx = appContext ?: return@withContext 0
        val endpoint = BuildConfig.TELEMETRY_URL
        if (endpoint.isBlank()) return@withContext 0
        val file = queueFile(ctx)
        val lines = file.readLines().take(MAX_BATCH)
        if (lines.isEmpty()) return@withContext 0
        val body = "[" + lines.joinToString(",") + "]"
        val conn = URL(endpoint).openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/json")
        try {
            conn.outputStream.use { it.write(body.toByteArray()) }
            if (conn.responseCode in 200..299) {
                val rest = file.readLines().drop(lines.size)
                file.writeText(if (rest.isEmpty()) "" else rest.joinToString("\n") + "\n")
                lines.size
            } else 0
        } catch (e: Exception) {
            0
        } finally {
            conn.disconnect()
        }
    }

    private fun queueFile(ctx: Context): File =
        File(ctx.filesDir, "telemetry").apply { mkdirs() }.resolve("events.jsonl")
}
