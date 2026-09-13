package com.terrella.worlds.util

/** Rotating nerdy "your diorama is cooking" one-liners for pending asset cards. */
object DioramaHumor {
    private val lines = listOf(
        "Our monkeys are shizzling your diorama from pure vibranium",
        "Convincing tiny electrons to build your city…",
        "Folding a miniature skyline out of good vibes…",
        "Teaching gravity to mind its own business…",
        "Warming up the world's smallest construction cranes…",
        "Bribing the weather gods for your postcode…",
        "3D-printing a city, one vibe at a time…",
        "Duct-taping clouds to a very small sky…",
    )

    fun forName(name: String, country: String): String =
        lines[kotlin.math.abs("$name,$country".hashCode()) % lines.size]
}
