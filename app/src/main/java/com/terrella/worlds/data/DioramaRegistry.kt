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

    val STYLES = listOf(
        DioramaStyle(
            id = "young_wizard",
            name = "Young Wizard",
            tagline = "Magical Gothic diorama with spires & floating towers",
            modelAssetPath = "models/prague_wizard.glb",
            defaultScale = 1.0f
        ),
        DioramaStyle(
            id = "original",
            name = "Classic Canal",
            tagline = "Historic illuminated canal side with vintage tram",
            modelAssetPath = "models/prague_wizard.glb", // fallback or default asset
            defaultScale = 1.0f
        ),
        DioramaStyle(
            id = "halfling_village",
            name = "Halfling Village",
            tagline = "Cozy fantasy cottages with lush terrain & bridges",
            modelAssetPath = "models/prague_wizard.glb",
            defaultScale = 1.0f
        ),
        DioramaStyle(
            id = "retro_80s",
            name = "Back to the 80's",
            tagline = "Retro futuristic neon vibes & arcade flair",
            modelAssetPath = "models/prague_wizard.glb",
            defaultScale = 1.0f
        )
    )

    fun getStyleForLocation(location: SavedLocation?, artStyleId: String?): DioramaStyle {
        return STYLES.firstOrNull { it.id == artStyleId }
            ?: STYLES.first()
    }
}
