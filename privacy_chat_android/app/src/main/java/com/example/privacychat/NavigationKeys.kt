package com.example.privacychat

import androidx.navigation3.runtime.NavKey
import kotlinx.serialization.Serializable

@Serializable data object Config : NavKey
@Serializable data object Auth : NavKey
@Serializable data object Chat : NavKey

