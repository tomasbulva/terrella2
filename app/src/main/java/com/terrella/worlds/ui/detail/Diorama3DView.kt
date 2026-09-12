package com.terrella.worlds.ui.detail

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.terrella.worlds.data.weather.WeatherSnapshot
import io.github.sceneview.SceneView
import io.github.sceneview.node.ModelNode
import io.github.sceneview.rememberModelInstance

@Composable
fun Diorama3DView(
    modelPath: String,
    weather: WeatherSnapshot?,
    modifier: Modifier = Modifier
) {
    SceneView(
        modifier = modifier.fillMaxSize()
    ) {
        rememberModelInstance(modelLoader, modelPath)?.let { modelInstance ->
            ModelNode(
                modelInstance = modelInstance,
                scaleToUnits = 1.0f
            )
        }
    }
}
