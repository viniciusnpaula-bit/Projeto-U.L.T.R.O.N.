package br.com.ultron.mobile.core.security

interface OwnerAuthenticator {
    /** True only while a recent, explicit owner-authentication proof is valid. */
    fun isAuthenticated(): Boolean
    suspend fun verifyPin(pin: CharArray): Boolean
}
