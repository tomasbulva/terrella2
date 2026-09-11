package com.terrella.worlds.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

private val TerrellaDark = darkColorScheme(
    primary = TerrellaDarkPrimary,
    onPrimary = TerrellaDarkOnPrimary,
    background = TerrellaDarkBackground,
    onBackground = TerrellaDarkOnBackground,
    surface = TerrellaDarkSurface,
    onSurface = TerrellaDarkOnSurface,
    surfaceVariant = TerrellaDarkSurfaceVariant,
    onSurfaceVariant = TerrellaDarkOnSurfaceVariant,
    outline = TerrellaDarkOutline,
)

private val TerrellaLight = lightColorScheme(
    primary = TerrellaLightPrimary,
    onPrimary = TerrellaLightOnPrimary,
    background = TerrellaLightBackground,
    onBackground = TerrellaLightOnBackground,
    surface = TerrellaLightSurface,
    onSurface = TerrellaLightOnSurface,
    surfaceVariant = TerrellaLightSurfaceVariant,
    onSurfaceVariant = TerrellaLightOnSurfaceVariant,
    outline = TerrellaLightOutline,
)

@Composable
fun TerrellaTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colorScheme = if (darkTheme) TerrellaDark else TerrellaLight

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content,
    )
}
