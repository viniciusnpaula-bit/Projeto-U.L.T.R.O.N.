package br.com.ultron.mobile.core.security

/** Storage abstraction for secrets encrypted at rest by platform implementations. */
interface SecureSecretStore {
    fun read(key: String): String?
    fun write(key: String, value: String)
    fun delete(key: String)
}
