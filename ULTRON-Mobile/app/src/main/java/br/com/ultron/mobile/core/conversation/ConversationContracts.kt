package br.com.ultron.mobile.core.conversation

/**
 * Domain contracts for the independent Android assistant.
 *
 * These types intentionally contain no Android UI, network client, or PC/Core dependency.
 * Implementations should be injected from the application's composition root.
 */
enum class MessageRole { USER, ASSISTANT }

data class ConversationMessage(
    val id: String,
    val role: MessageRole,
    val content: String,
    val createdAtEpochMillis: Long
)

data class ConversationRequest(
    val requestId: String,
    val userMessage: String,
    /** Bounded, already-sanitized conversation context. Never include credentials or PINs. */
    val recentHistory: List<ConversationMessage> = emptyList()
)

enum class ReplyOrigin {
    ONLINE_AI,
    LOCAL_COMMAND,
    LOCAL_NOTICE
}

data class ConversationReply(
    val requestId: String,
    val text: String,
    val origin: ReplyOrigin,
    /** Null for local replies; otherwise the provider identifier, never a secret. */
    val providerId: String? = null
)

enum class ConnectivityStatus { ONLINE, OFFLINE, UNKNOWN }

sealed interface ConversationFailure {
    data object Offline : ConversationFailure
    data object TimedOut : ConversationFailure
    data object Cancelled : ConversationFailure
    data class ProviderUnavailable(val providerId: String) : ConversationFailure
    data object InvalidRequest : ConversationFailure
    data object Unexpected : ConversationFailure
}

/**
 * Orchestrates local commands and online AI. Local command routing must happen before
 * remote generation, and local commands must remain usable when connectivity is absent.
 * Any action intent returned by the local router must go through ActionGateway.
 */
interface ConversationEngine {
    suspend fun respond(request: ConversationRequest): Result<ConversationReply>
}
