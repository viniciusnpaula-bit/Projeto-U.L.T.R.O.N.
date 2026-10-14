package br.com.ultron.mobile.core.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.KeyGenerator
import javax.crypto.Mac
import javax.crypto.SecretKey
import java.security.SecureRandom

/**
 * PIN verifier backed by a non-exportable Android Keystore HMAC key.
 * The PIN is never persisted. Failed-attempt throttling is stored in private app
 * preferences; uninstall/device compromise are outside this class's threat model.
 *
 * Enrollment must be called once from an owner-only setup screen after validating
 * a 6+ digit PIN. This class intentionally does not provide a default PIN.
 */
class AndroidOwnerAuthenticator(
    context: Context,
    private val sessionTtlMillis: Long = 2 * 60_000L,
    private val clock: () -> Long = { android.os.SystemClock.elapsedRealtime() }
) : OwnerAuthenticator {
    private val prefs = context.getSharedPreferences("ultron_owner_auth", Context.MODE_PRIVATE)
    private var authenticatedUntil = 0L
    private val keyAlias = "ultron.owner.pin.hmac.v1"

    @Synchronized
    fun enroll(pin: CharArray): Boolean {
        if (pin.size < 6 || pin.any { !it.isDigit() }) {
            pin.fill('\u0000')
            return false
        }
        return try {
            ensureKey()
            val salt = ByteArray(32).also(SecureRandom()::nextBytes)
            val verifier = hmac(pin, salt)
            prefs.edit()
                .putString("pin_salt", Base64.encodeToString(salt, Base64.NO_WRAP))
                .putString("pin_verifier", Base64.encodeToString(verifier, Base64.NO_WRAP))
                .putInt("failed_attempts", 0)
                .putLong("locked_until", 0L)
                .commit()
        } catch (_: Exception) {
            false
        } finally {
            pin.fill('\u0000')
        }
    }

    /** True when an owner PIN has been enrolled on this installation. */
    @Synchronized
    fun hasEnrollment(): Boolean =
        !prefs.getString("pin_salt", null).isNullOrBlank() &&
            !prefs.getString("pin_verifier", null).isNullOrBlank()

    // Suspend API delegates to a synchronized non-suspending critical section:
    // concurrent attempts cannot race the failure counter or session state.
    override suspend fun verifyPin(pin: CharArray): Boolean = verifyPinSync(pin)

    @Synchronized
    private fun verifyPinSync(pin: CharArray): Boolean {
        try {
            val now = clock()
            if (now < prefs.getLong("locked_until", 0L)) {
                authenticatedUntil = 0L
                return false
            }
            val saltText = prefs.getString("pin_salt", null)
            val verifierText = prefs.getString("pin_verifier", null)
            if (saltText == null || verifierText == null) {
                authenticatedUntil = 0L
                return false
            }
            val salt = Base64.decode(saltText, Base64.NO_WRAP)
            val expected = Base64.decode(verifierText, Base64.NO_WRAP)
            val actual = hmac(pin, salt)
            val valid = java.security.MessageDigest.isEqual(expected, actual)
            if (valid) {
                prefs.edit().putInt("failed_attempts", 0).putLong("locked_until", 0L).apply()
                authenticatedUntil = now + sessionTtlMillis
                return true
            }
            val failures = prefs.getInt("failed_attempts", 0) + 1
            val delay = when {
                failures >= 10 -> 15 * 60_000L
                failures >= 7 -> 5 * 60_000L
                failures >= 5 -> 60_000L
                else -> 0L
            }
            prefs.edit().putInt("failed_attempts", failures)
                .putLong("locked_until", now + delay).apply()
            authenticatedUntil = 0L
            return false
        } catch (_: Exception) {
            authenticatedUntil = 0L
            return false
        } finally {
            pin.fill('\u0000')
        }
    }

    /** Call only after AndroidX BiometricPrompt reports BIOMETRIC_SUCCESS. */
    @Synchronized
    fun acceptBiometricAuthentication() {
        authenticatedUntil = clock() + sessionTtlMillis
    }

    @Synchronized
    override fun isAuthenticated(): Boolean = clock() < authenticatedUntil

    private fun ensureKey() {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (keyStore.containsAlias(keyAlias)) return
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_HMAC_SHA256, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(keyAlias, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
                .setDigests(KeyProperties.DIGEST_SHA256)
                .build()
        )
        generator.generateKey()
    }

    private fun hmac(pin: CharArray, salt: ByteArray): ByteArray {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val key = keyStore.getKey(keyAlias, null) as? SecretKey ?: error("PIN key unavailable")
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(key)
        // Bind the random salt to the PIN verifier; neither value is logged or persisted in plaintext.
        val pinBytes = String(pin).toByteArray(Charsets.UTF_8)
        val input = ByteArray(salt.size + pinBytes.size)
        return try {
            System.arraycopy(salt, 0, input, 0, salt.size)
            System.arraycopy(pinBytes, 0, input, salt.size, pinBytes.size)
            mac.doFinal(input)
        } finally {
            pinBytes.fill(0)
            input.fill(0)
        }
    }
}
