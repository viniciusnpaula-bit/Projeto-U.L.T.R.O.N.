package br.com.ultron.mobile.core.conversation

import br.com.ultron.mobile.core.actions.ActionRequest

/**
 * Recognizes only explicit, app-owned local commands. Implementations must not infer
 * arbitrary actions from model output or execute actions themselves.
 */
interface LocalCommandRouter {
    suspend fun route(requestId: String, input: String): LocalCommandResult
}

sealed interface LocalCommandResult {
    /** The input is not a recognized local command; the online AI may handle it. */
    data object NotHandled : LocalCommandResult

    /** Safe informational response produced entirely on-device. */
    data class Reply(val text: String) : LocalCommandResult

    /** Intent only: the caller must submit this request to ActionGateway. */
    data class ActionIntent(val request: ActionRequest) : LocalCommandResult
}
