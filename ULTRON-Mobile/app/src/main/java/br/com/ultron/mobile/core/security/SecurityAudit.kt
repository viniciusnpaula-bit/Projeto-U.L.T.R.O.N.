package br.com.ultron.mobile.core.security

import android.util.Log

enum class SecurityEventType { AUTH_SUCCESS, AUTH_FAILURE, ACTION_ALLOWED, ACTION_BLOCKED, CONFIRMATION_ISSUED, CONFIRMATION_REJECTED }

data class SecurityEvent(
    val type: SecurityEventType,
    val actionId: String? = null,
    val reasonCode: String,
    val timestampMillis: Long = System.currentTimeMillis()
)

/** Log metadata only. Never pass PINs, tokens, raw arguments, or AI prompts here. */
fun interface SecurityAudit {
    fun record(event: SecurityEvent)
}

class AndroidLogSecurityAudit : SecurityAudit {
    override fun record(event: SecurityEvent) {
        Log.i("ULTRON_SECURITY", "type=${event.type};action=${event.actionId ?: "-"};reason=${event.reasonCode};at=${event.timestampMillis}")
    }
}
