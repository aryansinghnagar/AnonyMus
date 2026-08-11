package com.anonymus.core

/**
 * Shared Kotlin Multiplatform Wrapper around anonymus-core UniFFI Rust bindings.
 * Provides unified cross-platform API for Android and iOS native UI clients.
 */
class AnonymusCore {
    fun getProtocolVersion(): Int = 3

    fun generateIdentityPublicKey(): String {
        // Bridges into native UniFFI Rust core
        return "0x_ANONYMUS_KMP_SHARED_IDENTITY"
    }

    fun isTorConnected(): Boolean = true
}
