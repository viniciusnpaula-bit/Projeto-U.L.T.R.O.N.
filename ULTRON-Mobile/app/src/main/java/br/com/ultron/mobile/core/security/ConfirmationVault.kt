package br.com.ultron.mobile.core.security

import android.os.SystemClock
import br.com.ultron.mobile.core.actions.ActionRequest
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

/**
 * In-memory, one-use approvals. The approval binds action ID AND canonical arguments.
 * Monotonic time avoids wall-clock changes extending a confirmation's lifetime.
 * Process death intentionally invalidates all pending approvals.
 */
class ConfirmationVault(
    private val ttlMillis: Long = 60_000L,
    private val nowMillis: () -> Long = { SystemClock.elapsedRealtime() }
) {
    private data class Approval(val fingerprint: String, val expiresAt: Long)
    private val approvals = ConcurrentHashMap<String, Approval>()

    fun issue(request: ActionRequest, ownerAuthenticated: Boolean): String? {
        if (!ownerAuthenticated || request.actionId.isBlank() || request.requestId.isBlank()) return null
        val id = UUID.randomUUID().toString()
        approvals[id] = Approval(fingerprint(request), nowMillis() + ttlMillis)
        return id
    }

    /** Removes the approval before returning; it cannot be replayed even after a failed check. */
    fun consume(id: String?, request: ActionRequest): Boolean {
        if (id.isNullOrBlank()) return false
        val approval = approvals.remove(id) ?: return false
        if (nowMillis() >= approval.expiresAt) return false
        return MessageDigest.isEqual(
            approval.fingerprint.toByteArray(Charsets.UTF_8),
            fingerprint(request).toByteArray(Charsets.UTF_8)
        )
    }

    private fun fingerprint(request: ActionRequest): String {
        val canonical = buildString {
            append(request.actionId).append('\n')
            request.arguments.toSortedMap().forEach { (key, value) ->
                append(key.length).append(':').append(key)
                    .append('=').append(value.length).append(':').append(value).append('\n')
            }
        }
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(canonical.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { "%02x".format(it) }
    }
}
