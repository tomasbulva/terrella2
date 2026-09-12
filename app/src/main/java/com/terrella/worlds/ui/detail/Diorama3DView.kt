package com.terrella.worlds.ui.detail

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import com.terrella.worlds.data.SavedLocation
import com.terrella.worlds.data.weather.Condition
import com.terrella.worlds.data.weather.WeatherSnapshot
import com.terrella.worlds.util.SunriseSunsetCalculator
import dev.romainguy.kotlin.math.Float3
import io.github.sceneview.SceneView
import io.github.sceneview.math.Color
import io.github.sceneview.node.ModelNode
import io.github.sceneview.rememberEngine
import io.github.sceneview.rememberFillLightNode
import io.github.sceneview.rememberMainLightNode
import io.github.sceneview.rememberModelInstance
import java.util.Calendar
import java.util.TimeZone
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

data class SolarLighting(
    val direction: Float3,
    val color: Color,
    val intensity: Float,
    val ambientColor: Color,
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
                color = Color(0.60f, 0.70f, 0.95f), // Clear moonlight
                intensity = 50_000f * weatherDimming,
                ambientColor = Color(0.40f, 0.45f, 0.65f),
                ambientIntensity = 30_000f * weatherDimming
            )
            isDawnDusk -> SolarLighting(
                direction = sunDir,
                color = Color(1.0f, 0.75f, 0.50f), // Golden hour amber
                intensity = 80_000f * weatherDimming,
                ambientColor = Color(0.60f, 0.50f, 0.60f),
                ambientIntensity = 35_000f * weatherDimming
            )
            else -> SolarLighting(
                direction = sunDir,
                color = Color(1.0f, 0.98f, 0.95f), // Daylight
                intensity = 100_000f * weatherDimming,
                ambientColor = Color(0.65f, 0.75f, 0.88f),
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

    SceneView(
        modifier = modifier.fillMaxSize(),
        engine = engine,
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
        rememberModelInstance(modelLoader, modelPath)?.let { modelInstance ->
            ModelNode(
                modelInstance = modelInstance,
                scaleToUnits = 1.0f
            )
        }
    }
}
