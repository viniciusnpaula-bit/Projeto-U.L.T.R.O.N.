package br.com.ultron.mobile.core.security

import br.com.ultron.mobile.core.actions.ActionExecutor
import br.com.ultron.mobile.core.actions.ActionRequest
import br.com.ultron.mobile.core.actions.ActionResult

interface SecurityAuditSink {
    fun record(event: String, actionId: String, requestId: String, outcome: String)
}

/**
 * Single policy gate for requests coming from UI/AI.
 *
 * The executor must remain a private implementation detail of the composition root.
 * HIGH-risk actions require both a live owner session and an explicit interactive
 * approval callback. The callback defaults to deny so missing UI wiring cannot
 * silently authorize sensitive work.
 */
class ActionGateway(
    private val executor: ActionExecutor,
    private val confirmations: ConfirmationManager,
    private val audit: SecurityAuditSink,
    private val androidPermissionGranted: (ActionRequest) -> Boolean,
    private val ownerAuthenticated: () -> Boolean,
    private val confirmExplicitly: suspend (ActionRequest) -> Boolean = { false }
) {
    suspend fun execute(request: ActionRequest, confirmationId: String? = null): ActionResult {
        val policy = executor.policyFor(request.actionId)
        if (policy == null) {
            audit.record("ACTION_BLOCKED", request.actionId, request.requestId, "NOT_ALLOWLISTED")
            return ActionResult.Blocked("Ação bloqueada pela política de segurança.")
        }

        val decision = SecurityManager.decide(policy, androidPermissionGranted(request))
        if (decision == Decision.DENY) {
            audit.record("ACTION_BLOCKED", request.actionId, request.requestId, "DENY")
            return ActionResult.Blocked("Ação bloqueada pela política de segurança.")
        }

        if (decision == Decision.REQUIRE_CONFIRMATION) {
            if (!ownerAuthenticated()) {
                audit.record("OWNER_AUTH_REQUIRED", request.actionId, request.requestId, "BLOCKED")
                return ActionResult.Blocked("Autenticação do proprietário necessária.")
            }
            if (confirmationId == null) {
                val challenge = confirmations.issue(request.actionId, request.arguments)
                audit.record("CONFIRMATION_ISSUED", request.actionId, request.requestId, "PENDING")
                return ActionResult.ConfirmationRequired(
                    summary = "Confirme esta ação no dispositivo.",
                    confirmationId = challenge.id
                )
            }

            // Consume first, even when the user declines, to prevent retries/replay.
            if (!confirmations.consume(confirmationId, request.actionId, request.arguments)) {
                audit.record("CONFIRMATION_REJECTED", request.actionId, request.requestId, "BLOCKED")
                return ActionResult.Blocked("Confirmação inválida, expirada ou já utilizada.")
            }
            val approved = try {
                confirmExplicitly(request)
            } catch (_: Exception) {
                false
            }
            if (!approved || !ownerAuthenticated()) {
                audit.record("CONFIRMATION_REJECTED", request.actionId, request.requestId, "OWNER_DECLINED_OR_SESSION_EXPIRED")
                return ActionResult.Blocked("Ação não confirmada pelo proprietário.")
            }
        }

        return try {
            executor.execute(request.copy(confirmationId = null)).also {
                audit.record(
                    "ACTION_EXECUTED", request.actionId, request.requestId,
                    if (it is ActionResult.Success) "SUCCESS" else "FAILED"
                )
            }
        } catch (_: Exception) {
            audit.record("ACTION_FAILED", request.actionId, request.requestId, "FAILED")
            ActionResult.Failure("Falha ao executar a ação.")
        }
    }
}
