package br.com.ultron.mobile.core.actions

import br.com.ultron.mobile.core.security.ActionPolicy

data class ActionRequest(
    val requestId: String,
    val actionId: String,
    val arguments: Map<String, String>
)

sealed interface ActionResult {
    data class Success(val summary: String) : ActionResult
    data class Failure(val reason: String) : ActionResult
    data class ConfirmationRequired(val summary: String) : ActionResult
    data class Blocked(val reason: String) : ActionResult
}

interface ActionExecutor {
    fun policyFor(actionId: String): ActionPolicy?
    suspend fun execute(request: ActionRequest): ActionResult
}
