package com.terrella.worlds.data

/**
 * Diorama style and asset definition.
 */
data class DioramaStyle(
    val id: String,
    val name: String,
    val tagline: String,
    val modelAssetPath: String,
    val defaultScale: Float = 1.0f
)

object DioramaRegistry {

    /**
     * Per-location 3D asset overrides, keyed by normalized place name.
     * To add a new city: drop its GLB into `app/src/main/assets/models/`
     * and register `"amsterdam" to "models/amsterdam_canal.glb"` here.
     * Locations without an entry use their art style's default asset.
     */
    private val LOCATION_OVERRIDES = mapOf(
        "prague" to "models/prague_wizard.glb",
        "amsterdam" to "models/amsterdam_canal.glb",
    )

    /**
     * Style IDs must match the ids persisted by the Settings screen
     * (SettingsScreen.ART_STYLES) so selections resolve instead of
     * silently falling back to the first entry.
     *
     * Today only one 3D asset is bundled (`prague_wizard.glb`), so every
     * style resolves to it; new GLBs from the TRELLIS pipeline slot in by
     * changing each style's modelAssetPath.
     */
    val STYLES = listOf(
        DioramaStyle(
            id = "original",
            name = "Original",
            tagline = "Clean & minimal",
            modelAssetPath = "models/prague_wizard.glb",
        ),
        DioramaStyle(
            id = "video_game",
            name = "Video Game",
            tagline = "Action packed",
            modelAssetPath = "models/prague_wizard.glb",
        ),
        DioramaStyle(
            id = "lego",
            name = "Color Bricks",
            tagline = "Brick by brick",
            modelAssetPath = "models/prague_wizard.glb",
        ),
        DioramaStyle(
            id = "trolls_claymation",
            name = "Glitter Claymation",
            tagline = "Glittery & fun",
            modelAssetPath = "models/prague_wizard.glb",
        ),
        DioramaStyle(
            id = "back_to_the_future",
            name = "Back to the 80's",
            tagline = "Retro futuristic",
            modelAssetPath = "models/prague_wizard.glb",
        ),
        DioramaStyle(
            id = "lord_of_the_ring",
            name = "Halfling Village",
            tagline = "Medieval fantasy",
            modelAssetPath = "models/prague_wizard.glb",
        ),
        DioramaStyle(
            id = "harry_potter",
            name = "Young Wizard",
            tagline = "Magical world",
            modelAssetPath = "models/prague_wizard.glb",
        ),
        DioramaStyle(
            id = "zombie_apocalypse",
            name = "Zombie Apocalypse",
            tagline = "Post-apocalyptic",
            modelAssetPath = "models/prague_wizard.glb",
        ),
        DioramaStyle(
            id = "plastic_dollhouse",
            name = "Plastic Dollhouse",
            tagline = "Toy world",
            modelAssetPath = "models/prague_wizard.glb",
        ),
    )

    fun getStyleForLocation(location: SavedLocation?, artStyleId: String?): DioramaStyle {
        val style = STYLES.firstOrNull { it.id == artStyleId } ?: STYLES.first()
        val override = location?.name?.trim()?.lowercase()?.let { LOCATION_OVERRIDES[it] }
        return if (override != null) style.copy(modelAssetPath = override) else style
    }
}
