package com.terrella.worlds.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.terrella.worlds.data.SettingsRepository
import com.terrella.worlds.ui.locations.LocationsScreen
import com.terrella.worlds.ui.settings.SettingsScreen
import com.terrella.worlds.ui.world.WorldScreen

object Routes {
    const val WORLD = "world"
    const val LOCATIONS = "locations"
    const val SETTINGS = "settings"
}

@Composable
fun AppNavigation() {
    val navController = rememberNavController()
    val settingsRepository = SettingsRepository.get(LocalContext.current)

    NavHost(navController = navController, startDestination = Routes.WORLD) {
        composable(Routes.WORLD) {
            WorldScreen(
                onNavigateToSettings = { navController.navigate(Routes.SETTINGS) },
                onNavigateToLocations = { navController.navigate(Routes.LOCATIONS) },
            )
        }
        composable(Routes.LOCATIONS) {
            LocationsScreen(
                onNavigateToWorld = { navController.popBackStack() },
                onNavigateToSettings = { navController.navigate(Routes.SETTINGS) },
                locationsRepository = locationsRepository,
                settingsRepository = settingsRepository,
            )
        }
        composable(Routes.SETTINGS) {
            SettingsScreen(
                onNavigateToWorld = { navController.popBackStack() },
                settingsRepository = settingsRepository,
            )
        }
    }
}
