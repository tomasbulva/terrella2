package com.terrella.worlds.ui.detail

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import com.terrella.worlds.data.weather.Condition
import com.terrella.worlds.data.weather.WeatherSnapshot
import kotlin.math.sin
import kotlin.random.Random

private class RainDrop(
    var x: Float,
    var y: Float,
    val length: Float,
    val speed: Float,
    val alpha: Float,
    val width: Float
)

private class Snowflake(
    var x: Float,
    var y: Float,
    val radius: Float,
    val speed: Float,
    val alpha: Float,
    val swingOffset: Float
)

@Composable
fun WeatherEffectsOverlay(
    weather: WeatherSnapshot?,
    modifier: Modifier = Modifier
) {
    if (weather == null) return

    val infiniteTransition = rememberInfiniteTransition(label = "weather_anim")
    val animationProgress by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 2000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "progress"
    )

    when (weather.condition) {
        Condition.RAIN, Condition.DRIZZLE, Condition.HEAVY_RAIN -> {
            RainOverlay(
                isHeavy = weather.condition == Condition.HEAVY_RAIN,
                progress = animationProgress,
                modifier = modifier
            )
        }
        Condition.SNOW -> {
            SnowOverlay(
                progress = animationProgress,
                modifier = modifier
            )
        }
        Condition.FOG -> {
            FogOverlay(
                progress = animationProgress,
                modifier = modifier
            )
        }
        Condition.THUNDER -> {
            ThunderOverlay(
                progress = animationProgress,
                modifier = modifier
            )
        }
        Condition.CLEAR, Condition.PARTLY_CLOUDY, Condition.CLOUDY -> {
            // Ambient subtle lighting glow if clear day or starry night
            if (weather.condition == Condition.CLEAR && !weather.isDay) {
                NightAtmosphereOverlay(modifier = modifier)
            }
        }
    }
}

@Composable
private fun RainOverlay(
    isHeavy: Boolean,
    progress: Float,
    modifier: Modifier = Modifier
) {
    val dropCount = if (isHeavy) 120 else 60
    val drops = remember(isHeavy) {
        val r = Random(42)
        List(dropCount) {
            RainDrop(
                x = r.nextFloat(),
                y = r.nextFloat(),
                length = if (isHeavy) r.nextFloat() * 35f + 30f else r.nextFloat() * 20f + 15f,
                speed = if (isHeavy) r.nextFloat() * 1.8f + 1.2f else r.nextFloat() * 1.2f + 0.8f,
                alpha = if (isHeavy) r.nextFloat() * 0.45f + 0.25f else r.nextFloat() * 0.35f + 0.15f,
                width = if (isHeavy) r.nextFloat() * 1.5f + 1.2f else r.nextFloat() * 1.0f + 0.8f
            )
        }
    }

    Canvas(modifier = modifier.fillMaxSize()) {
        val width = size.width
        val height = size.height

        // Wind slant offset
        val slantX = -12f

        for (drop in drops) {
            // Calculate current y based on speed and global progress loop
            val currentY = ((drop.y + progress * drop.speed) % 1.0f) * (height + 100f) - 50f
            val currentX = drop.x * width + (currentY / height) * slantX

            drawLine(
                color = Color(0xFFB0D6FF).copy(alpha = drop.alpha),
                start = Offset(currentX, currentY),
                end = Offset(currentX + slantX * (drop.length / 50f), currentY + drop.length),
                strokeWidth = drop.width,
                cap = StrokeCap.Round
            )
        }
    }
}

@Composable
private fun SnowOverlay(
    progress: Float,
    modifier: Modifier = Modifier
) {
    val flakeCount = 70
    val flakes = remember {
        val r = Random(77)
        List(flakeCount) {
            Snowflake(
                x = r.nextFloat(),
                y = r.nextFloat(),
                radius = r.nextFloat() * 3.5f + 1.5f,
                speed = r.nextFloat() * 0.6f + 0.3f,
                alpha = r.nextFloat() * 0.5f + 0.3f,
                swingOffset = r.nextFloat() * 6.28f
            )
        }
    }

    Canvas(modifier = modifier.fillMaxSize()) {
        val width = size.width
        val height = size.height

        for (flake in flakes) {
            val currentY = ((flake.y + progress * flake.speed) % 1.0f) * (height + 50f) - 25f
            val swing = sin((progress * 6.28f * 2f) + flake.swingOffset) * 20f
            val currentX = flake.x * width + swing

            drawCircle(
                color = Color.White.copy(alpha = flake.alpha),
                radius = flake.radius,
                center = Offset(currentX, currentY)
            )
        }
    }
}

@Composable
private fun FogOverlay(
    progress: Float,
    modifier: Modifier = Modifier
) {
    Canvas(modifier = modifier.fillMaxSize()) {
        val drift = sin(progress * 6.28f) * 30f

        // Soft atmospheric mist band across lower half and plinth
        drawRect(
            brush = Brush.verticalGradient(
                colors = listOf(
                    Color.Transparent,
                    Color(0xFFBACEE0).copy(alpha = 0.08f),
                    Color(0xFFD6E6F5).copy(alpha = 0.28f),
                    Color(0xFFEAF2FB).copy(alpha = 0.38f),
                    Color(0xFFCADBEA).copy(alpha = 0.15f),
                    Color.Transparent
                ),
                startY = size.height * 0.35f + drift,
                endY = size.height * 0.85f + drift
            )
        )
    }
}

@Composable
private fun ThunderOverlay(
    progress: Float,
    modifier: Modifier = Modifier
) {
    // Rain underneath
    RainOverlay(isHeavy = true, progress = progress, modifier = modifier)

    // Lightning flashes at specific progress intervals
    val flashAlpha = when {
        progress in 0.12f..0.15f -> 0.35f
        progress in 0.16f..0.18f -> 0.55f
        progress in 0.68f..0.70f -> 0.40f
        else -> 0f
    }

    if (flashAlpha > 0f) {
        Canvas(modifier = modifier.fillMaxSize()) {
            drawRect(color = Color(0xFFEEF3FF).copy(alpha = flashAlpha))
        }
    }
}

@Composable
private fun NightAtmosphereOverlay(
    modifier: Modifier = Modifier
) {
    Canvas(modifier = modifier.fillMaxSize()) {
        // Deep magical vignette on night scenes
        drawRect(
            brush = Brush.radialGradient(
                colors = listOf(
                    Color.Transparent,
                    Color(0xFF030712).copy(alpha = 0.45f)
                ),
                center = Offset(size.width * 0.5f, size.height * 0.5f),
                radius = size.width * 0.85f
            )
        )
    }
}
