package com.terrella.worlds.data

import kotlinx.serialization.Serializable

@Serializable
data class SavedLocation(
    val id: String = java.util.UUID.randomUUID().toString(),
    val name: String,
    val country: String = "",
    val latitude: Double,
    val longitude: Double,
    val timezone: String = "",
)
