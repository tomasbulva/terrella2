package com.terrella.worlds.ui.world

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
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

/**
 * Spike v1: loads the optimized Amsterdam diorama (worlds/amsterdam.glb),
 * default orbit camera (drag to rotate, pinch to zoom).
 */
@Composable
fun WorldScreen(modifier: Modifier = Modifier) {
    Box(modifier = modifier.fillMaxSize()) {
        SceneView(modifier = Modifier.fillMaxSize()) {
            rememberModelInstance(modelLoader, "worlds/amsterdam.glb")?.let {
                ModelNode(modelInstance = it, scaleToUnits = 1.0f)
            }
        }
        Text(
            text = "Terrella2 · Amsterdam diorama (spike)",
            style = MaterialTheme.typography.labelLarge,
            color = Color.White,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 32.dp)
                .background(
                    Color.Black.copy(alpha = 0.4f),
                    MaterialTheme.shapes.large
                )
                .padding(horizontal = 16.dp, vertical = 8.dp)
        )
    }
}
