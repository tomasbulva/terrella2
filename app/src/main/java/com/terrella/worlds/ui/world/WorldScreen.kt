package com.terrella.worlds.ui.world

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import io.github.sceneview.SceneView
import io.github.sceneview.node.ModelNode
import io.github.sceneview.rememberModelInstance

@Composable
fun WorldScreen(
    modifier: Modifier = Modifier,
    onNavigateToSettings: () -> Unit = {},
    onNavigateToLocations: () -> Unit = {},
    locationId: String? = null,
) {
    Box(modifier = modifier.fillMaxSize()) {
        SceneView(modifier = Modifier.fillMaxSize()) {
            rememberModelInstance(modelLoader, "worlds/amsterdam.glb")?.let {
                ModelNode(modelInstance = it, scaleToUnits = 1.0f)
            }
        }
        Row(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(12.dp),
        ) {
            IconButton(onClick = onNavigateToLocations) {
                Icon(
                    imageVector = Icons.Filled.Place,
                    contentDescription = "Places",
                    tint = Color.White,
                )
            }
            IconButton(onClick = onNavigateToSettings) {
                Icon(
                    imageVector = Icons.Filled.Settings,
                    contentDescription = "Settings",
                    tint = Color.White,
                )
            }
        }
        Text(
            text = "Terrella2 · Amsterdam diorama (spike)",
            style = MaterialTheme.typography.labelLarge,
            color = Color.White,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 32.dp)
                .background(Color.Black.copy(alpha = 0.4f), MaterialTheme.shapes.large)
                .padding(horizontal = 16.dp, vertical = 8.dp),
        )
    }
}
