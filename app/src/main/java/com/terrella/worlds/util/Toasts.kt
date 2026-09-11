package com.terrella.worlds.util

import android.content.Context
import android.widget.Toast

object Toasts {
    fun show(context: Context, message: String, long: Boolean = true) {
        Toast.makeText(context, message, if (long) Toast.LENGTH_LONG else Toast.LENGTH_SHORT).show()
    }
}
