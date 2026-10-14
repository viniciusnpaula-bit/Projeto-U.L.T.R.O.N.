package br.com.ultron.mobile.core.security

import android.os.SystemClock
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64
import java.util.concurrent.ConcurrentHashMap

data class ConfirmationChallenge(
    val id: String,
    val actionId: String,
    val expiresAtMonotonicMs: Long
)

/**
 * In-memory, one-use confirmation challenges. Monotonic time prevents wall-clock
 * adjustments from extending validity. Process death invalidates all challenges.
 */
class ConfirmationManager(
    private val ttlMs: Long = 60_000L,
    private val now: () -> Long = { SystemClock.elapsedRealtime() },
    private val random: SecureRandom = SecureRandom()
) {
    private data class Entry(val fingerprint: String, val expiresAt: Long)
    private val pending = ConcurrentHashMap<String, Entry>()

    init {
        require(ttlMs in 1..300_000L) { "Confirmation TTL must be between 1 ms and 5 minutes" }
    }

    fun issue(actionId: String, arguments: Map<String, String>): ConfirmationChallenge {
        require(actionId.isNotBlank())
        // Bound memory use if an untrusted caller floods confirmation requests.
        val current = now()
        pending.entries.removeIf { current >= it.value.expiresAt }
        check(pending.size < 128) { "Too many pending confirmations" }

        val id = ByteArray(32).also(random::nextBytes)
            .let { Base64.getUrlEncoder().withoutPadding().encodeToString(it) }
        val expiry = current + ttlMs
        pending[id] = Entry(fingerprint(actionId, arguments), expiry)
        return ConfirmationChallenge(id, actionId, expiry)
    }

    fun consume(id: String, actionId: String, arguments: Map<String, String>): Boolean {
        val entry = pending.remove(id) ?: return false
        if (now() >= entry.expiresAt) return false
        return MessageDigest.isEqual(
            entry.fingerprint.toByteArray(Charsets.UTF_8),
            fingerprint(actionId, arguments).toByteArray(Charsets.UTF_8)
        )
    }

    private fun fingerprint(actionId: String, args: Map<String, String>): String {
        val canonical = buildString {
            append(actionId.length).append(':').append(actionId)
            args.toSortedMap().forEach { (key, value) ->
                append('|').append(key.length).append(':').append(key)
                    .append('=').append(value.length).append(':').append(value)
            }
        }
        return MessageDigest.getInstance("SHA-256")
            .digest(canonical.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
    }
}
