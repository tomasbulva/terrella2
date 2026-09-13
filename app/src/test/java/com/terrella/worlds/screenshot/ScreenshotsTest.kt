package com.terrella.worlds.screenshot

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onRoot
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.github.takahirom.roborazzi.RoborazziRule
import com.github.takahirom.roborazzi.captureRoboImage
import com.terrella.worlds.data.SavedLocation
import com.terrella.worlds.data.weather.Condition
import com.terrella.worlds.data.weather.WeatherSnapshot
import com.terrella.worlds.ui.detail.WeatherEffectsOverlay
import com.terrella.worlds.ui.theme.TerrellaTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(AndroidJUnit4::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w412dp-h915dp-xhdpi", application = TestApp::class)
class ScreenshotsTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @get:Rule
    val roborazziRule = RoborazziRule(
        options = RoborazziRule.Options(
            outputDirectoryPath = "build/outputs/roborazzi"
        )
    )

    @Test
    fun captureRainOverlay() {
        val weather = WeatherSnapshot(
            tempC = 14.0,
            condition = Condition.RAIN,
            isDay = true,
            windKmh = 18.0,
            cloudCoverPct = 80,
            precipMm = 2.5,
        )
        composeTestRule.setContent {
            TerrellaTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = Color(0xFF161C24)) {
                    WeatherEffectsOverlay(weather = weather)
                }
            }
        }
        composeTestRule.onRoot().captureRoboImage("build/outputs/roborazzi/weather_rain.png")
    }

    @Test
    fun captureSnowOverlay() {
        val weather = WeatherSnapshot(
            tempC = -2.0,
            condition = Condition.SNOW,
            isDay = false,
            windKmh = 8.0,
            cloudCoverPct = 95,
            precipMm = 1.0,
        )
        composeTestRule.setContent {
            TerrellaTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = Color(0xFF161C24)) {
                    WeatherEffectsOverlay(weather = weather)
                }
            }
        }
        composeTestRule.onRoot().captureRoboImage("build/outputs/roborazzi/weather_snow.png")
    }

    @Test
    fun captureFogOverlay() {
        val weather = WeatherSnapshot(
            tempC = 8.0,
            condition = Condition.FOG,
            isDay = true,
            windKmh = 5.0,
            cloudCoverPct = 90,
            precipMm = 0.0,
        )
        composeTestRule.setContent {
            TerrellaTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = Color(0xFF161C24)) {
                    WeatherEffectsOverlay(weather = weather)
                }
            }
        }
        composeTestRule.onRoot().captureRoboImage("build/outputs/roborazzi/weather_fog.png")
    }
}

/** Bare Application — the real WorldsApp schedules WorkManager jobs in onCreate, which Robolectric can't run. */
class TestApp : android.app.Application()
