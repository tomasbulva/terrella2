package com.terrella.worlds

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.terrella.worlds.ui.AppNavigation
import com.terrella.worlds.ui.theme.TerrellaTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            TerrellaTheme {
                AppNavigation()
            }
        }
    }
}
