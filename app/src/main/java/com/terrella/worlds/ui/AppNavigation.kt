package com.terrella.worlds.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.terrella.worlds.data.LocationsRepository
import com.terrella.worlds.data.SettingsRepository
import com.terrella.worlds.ui.detail.LocationDetailScreen
import com.terrella.worlds.ui.locations.LocationsScreen
import com.terrella.worlds.ui.settings.SettingsScreen
import com.terrella.worlds.ui.world.WorldScreen

object Routes {
    const val WORLD = "world"
    const val LOCATIONS = "locations"
    const val DETAIL = "detail"
    const val SETTINGS = "settings"
}

@Composable
fun AppNavigation() {
    val navController = rememberNavController()
    val settingsRepository = SettingsRepository.get(LocalContext.current)
    val locationsRepository = LocationsRepository.get(LocalContext.current)

    NavHost(navController = navController, startDestination = Routes.LOCATIONS) {
        composable("${Routes.WORLD}?locationId={locationId}") { backStackEntry ->
            com.terrella.worlds.ui.world.WorldScreen(
                onNavigateToSettings = { navController.navigate(Routes.SETTINGS) },
                onNavigateToLocations = { navController.popBackStack() },
                locationId = backStackEntry.arguments?.getString("locationId"),
            )
        }
        composable(Routes.LOCATIONS) {
            com.terrella.worlds.ui.locations.LocationsScreen(
                onOpenDetail = { id -> navController.navigate("${Routes.DETAIL}/$id") },
                onNavigateToSettings = { navController.navigate(Routes.SETTINGS) },
                locationsRepository = locationsRepository,
                settingsRepository = settingsRepository,
            )
        }
        composable("${Routes.DETAIL}/{locationId}") { backStackEntry ->
            LocationDetailScreen(
                locationId = backStackEntry.arguments?.getString("locationId"),
                onNavigateBack = { navController.popBackStack() },
                onNavigateToWorld = { navController.navigate("${Routes.WORLD}") },
                onNavigateToSettings = { navController.navigate(Routes.SETTINGS) },
                locationsRepository = locationsRepository,
                settingsRepository = settingsRepository,
            )
        }
        composable(Routes.SETTINGS) {
            com.terrella.worlds.ui.settings.SettingsScreen(
                onNavigateToWorld = { navController.popBackStack() },
                settingsRepository = settingsRepository,
            )
        }
    }
}
