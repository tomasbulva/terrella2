package com.terrella.worlds

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.terrella.worlds.ui.theme.TerrellaTheme
import com.terrella.worlds.ui.world.WorldScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            TerrellaTheme {
                WorldScreen()
            }
        }
    }
}
