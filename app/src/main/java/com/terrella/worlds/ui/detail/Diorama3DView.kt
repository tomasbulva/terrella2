package com.terrella.worlds.ui.detail

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.terrella.worlds.data.SavedLocation
import com.terrella.worlds.data.weather.Condition
import com.terrella.worlds.data.weather.WeatherSnapshot
import com.terrella.worlds.util.SunriseSunsetCalculator
import dev.romainguy.kotlin.math.Float3
import io.github.sceneview.SceneView
import io.github.sceneview.math.Color as SceneColor
import io.github.sceneview.math.Position
import io.github.sceneview.math.Rotation
import io.github.sceneview.node.ModelNode
import io.github.sceneview.rememberCameraNode
import io.github.sceneview.rememberEngine
import io.github.sceneview.rememberFillLightNode
import io.github.sceneview.rememberMainLightNode
import io.github.sceneview.rememberModelInstance
import io.github.sceneview.SurfaceType
import java.util.Calendar
import java.util.TimeZone
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

data class SolarLighting(
    val direction: Float3,
    val color: SceneColor,
    val intensity: Float,
    val ambientColor: SceneColor,
    val ambientIntensity: Float
)

object SolarLightingEngine {

    /**
     * Calculates realistic sun position, color temperature, and atmospheric intensity
     * matching the location's real time and NOAA sunrise/sunset curve.
     */
    fun calculate(
        location: SavedLocation?,
        weather: WeatherSnapshot?
    ): SolarLighting {
        val lat = location?.latitude ?: 50.0875
        val lon = location?.longitude ?: 14.4213
        val tz = location?.timezone?.ifBlank { null }?.let { runCatching { TimeZone.getTimeZone(it) }.getOrNull() }
            ?: TimeZone.getDefault()

        val cal = Calendar.getInstance(tz)
        val dayOfYear = cal.get(Calendar.DAY_OF_YEAR)
        val currentMinutes = cal.get(Calendar.HOUR_OF_DAY) * 60 + cal.get(Calendar.MINUTE)
        val offsetMinutes = tz.getOffset(cal.timeInMillis) / 60000

        val (sunriseMin, sunsetMin) = SunriseSunsetCalculator.compute(lat, lon, dayOfYear, offsetMinutes)

        val isDay = currentMinutes in sunriseMin..sunsetMin
        val isDawnDusk = isDay && (currentMinutes <= sunriseMin + 60 || currentMinutes >= sunsetMin - 60)

        // Calculate solar arc from sunrise (0 rad) -> solar noon (PI/2 rad) -> sunset (PI rad)
        val solarProgress = if (isDay && sunsetMin > sunriseMin) {
            ((currentMinutes - sunriseMin).toFloat() / (sunsetMin - sunriseMin).toFloat()).coerceIn(0f, 1f)
        } else {
            0.5f // Default mid-night or fallback
        }

        val sunAngleRad = solarProgress * PI.toFloat()
        val sunDir = if (isDay) {
            val elevation = sin(sunAngleRad).coerceAtLeast(0.2f)
            val azimuth = -cos(sunAngleRad)
            Float3(azimuth * 0.7f, -elevation, -0.6f)
        } else {
            // Moonlight from top-angled direction
            Float3(0.3f, -0.7f, -0.5f)
        }

        // Weather atmospheric dampening
        val weatherDimming = when (weather?.condition) {
            Condition.CLEAR -> 1.0f
            Condition.PARTLY_CLOUDY -> 0.90f
            Condition.CLOUDY -> 0.75f
            Condition.FOG -> 0.65f
            Condition.DRIZZLE, Condition.RAIN -> 0.65f
            Condition.HEAVY_RAIN, Condition.THUNDER -> 0.55f
            Condition.SNOW -> 0.80f
            null -> 1.0f
        }

        return when {
            !isDay -> SolarLighting(
                direction = sunDir,
                color = SceneColor(0.60f, 0.70f, 0.95f), // Clear moonlight
                intensity = 50_000f * weatherDimming,
                ambientColor = SceneColor(0.40f, 0.45f, 0.65f),
                ambientIntensity = 30_000f * weatherDimming
            )
            isDawnDusk -> SolarLighting(
                direction = sunDir,
                color = SceneColor(1.0f, 0.75f, 0.50f), // Golden hour amber
                intensity = 80_000f * weatherDimming,
                ambientColor = SceneColor(0.60f, 0.50f, 0.60f),
                ambientIntensity = 35_000f * weatherDimming
            )
            else -> SolarLighting(
                direction = sunDir,
                color = SceneColor(1.0f, 0.98f, 0.95f), // Daylight
                intensity = 100_000f * weatherDimming,
                ambientColor = SceneColor(0.65f, 0.75f, 0.88f),
                ambientIntensity = 45_000f * weatherDimming
            )
        }
    }
}

@Composable
fun Diorama3DView(
    modelPath: String,
    location: SavedLocation?,
    weather: WeatherSnapshot?,
    modifier: Modifier = Modifier
) {
    val engine = rememberEngine()
    val lighting = remember(location, weather) {
        SolarLightingEngine.calculate(location, weather)
    }

    var isModelReady by remember(modelPath) { mutableStateOf(false) }

    Box(modifier = modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        SceneView(
            modifier = Modifier.fillMaxSize(),
            surfaceType = SurfaceType.TextureSurface,
            isOpaque = false,
            engine = engine,
            cameraNode = rememberCameraNode(engine) {
                // Fixed Isometric Perspective: looking down at 30 deg pitch, 45 deg yaw
                position = Position(x = 1.8f, y = 1.5f, z = 1.8f)
                rotation = Rotation(x = -30f, y = 45f, z = 0f)
            },
            cameraManipulator = null, // Locked camera angle for perfect isometric diorama framing
            mainLightNode = rememberMainLightNode(engine) {
                color = lighting.color
                intensity = lighting.intensity
                lightDirection = lighting.direction
                isShadowCaster = true
            },
            fillLightNode = rememberFillLightNode(engine) {
                color = lighting.ambientColor
                intensity = lighting.ambientIntensity
                isShadowCaster = false
            }
        ) {
            val modelInstance = rememberModelInstance(modelLoader, modelPath)
            if (modelInstance != null) {
                isModelReady = true
                ModelNode(
                    modelInstance = modelInstance,
                    scaleToUnits = 1.0f
                )
            }
        }

        // ── Smooth Diorama Loading Animation Overlay ──
        AnimatedVisibility(
            visible = !isModelReady,
            enter = fadeIn(),
            exit = fadeOut(animationSpec = tween(durationMillis = 500))
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.55f)),
                contentAlignment = Alignment.Center
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier
                        .background(Color(0xFF161C24).copy(alpha = 0.85f), shape = CircleShape)
                        .padding(horizontal = 24.dp, vertical = 20.dp)
                ) {
                    CircularProgressIndicator(
                        color = Color(0xFF64B5F6),
                        strokeWidth = 3.dp,
                        modifier = Modifier.size(36.dp)
                    )
                    Spacer(Modifier.height(12.dp))
                    Text(
                        "Rendering diorama…",
                        color = Color.White.copy(alpha = 0.9f),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Medium,
                        letterSpacing = 0.5.sp
                    )
                }
            }
        }
    }
}
