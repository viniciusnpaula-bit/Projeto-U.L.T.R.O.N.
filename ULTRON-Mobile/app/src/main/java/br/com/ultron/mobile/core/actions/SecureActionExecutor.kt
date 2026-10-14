package br.com.ultron.mobile.core.actions

import br.com.ultron.mobile.core.security.ActionPolicyRegistry
import br.com.ultron.mobile.core.security.ConfirmationVault
import br.com.ultron.mobile.core.security.Decision
import br.com.ultron.mobile.core.security.OwnerAuthenticator
import br.com.ultron.mobile.core.security.SecurityAudit
import br.com.ultron.mobile.core.security.SecurityEvent
import br.com.ultron.mobile.core.security.SecurityEventType
import br.com.ultron.mobile.core.security.SecurityManager

/**
 * Mandatory policy gate. Keep the delegate private to the composition root and
 * never expose it directly to UI/AI callers.
 *
 * A valid vault token is necessary but not sufficient: sensitive execution also
 * requires a positive explicit-approval callback. Missing UI wiring fails closed.
 */
class SecureActionExecutor(
    private val policies: ActionPolicyRegistry,
    private val owner: OwnerAuthenticator,
    private val confirmations: ConfirmationVault,
    private val audit: SecurityAudit,
    private val permissionGranted: (String) -> Boolean = { true },
    private val delegate: ActionExecutor,
    private val confirmExplicitly: suspend (ActionRequest) -> Boolean = { false }
) : ActionExecutor {
    override fun policyFor(actionId: String) = policies.policyFor(actionId)

    /** Creates a short-lived challenge, not a final authorization to execute. */
    fun requestConfirmation(request: ActionRequest): String? {
        val policy = policies.policyFor(request.actionId)
        if (policy == null || SecurityManager.decide(policy, permissionGranted(request.actionId)) != Decision.REQUIRE_CONFIRMATION) {
            audit.record(SecurityEvent(SecurityEventType.ACTION_BLOCKED, request.actionId, "NOT_CONFIRMABLE"))
            return null
        }
        if (!owner.isAuthenticated()) {
            audit.record(SecurityEvent(SecurityEventType.ACTION_BLOCKED, request.actionId, "OWNER_AUTH_REQUIRED"))
            return null
        }
        val id = confirmations.issue(request, ownerAuthenticated = true)
        audit.record(
            SecurityEvent(
                SecurityEventType.CONFIRMATION_ISSUED,
                request.actionId,
                if (id == null) "ISSUE_FAILED" else "PENDING_EXPLICIT_APPROVAL"
            )
        )
        return id
    }

    override suspend fun execute(request: ActionRequest): ActionResult {
        val policy = policies.policyFor(request.actionId)
        if (policy == null) return blocked(request, "NOT_ALLOWLISTED")
        val decision = SecurityManager.decide(policy, permissionGranted(request.actionId))
        if (decision == Decision.DENY) return blocked(request, "POLICY_DENY")
        if (decision == Decision.REQUIRE_CONFIRMATION) {
            if (!owner.isAuthenticated()) return blocked(request, "OWNER_AUTH_REQUIRED")
            if (!confirmations.consume(request.confirmationId, request.copy(confirmationId = null))) {
                audit.record(SecurityEvent(SecurityEventType.CONFIRMATION_REJECTED, request.actionId, "INVALID_EXPIRED_OR_REPLAYED"))
                return ActionResult.ConfirmationRequired("Confirmação válida necessária para esta ação.")
            }
            val approved = try {
                confirmExplicitly(request.copy(confirmationId = null))
            } catch (_: Exception) {
                false
            }
            if (!approved || !owner.isAuthenticated()) {
                audit.record(SecurityEvent(SecurityEventType.CONFIRMATION_REJECTED, request.actionId, "OWNER_DECLINED_OR_SESSION_EXPIRED"))
                return ActionResult.Blocked("Ação não confirmada pelo proprietário.")
            }
        }
        audit.record(SecurityEvent(SecurityEventType.ACTION_ALLOWED, request.actionId, if (decision == Decision.ALLOW) "POLICY_ALLOW" else "CONFIRMED"))
        return try {
            delegate.execute(request.copy(confirmationId = null))
        } catch (_: Exception) {
            audit.record(SecurityEvent(SecurityEventType.ACTION_BLOCKED, request.actionId, "EXECUTION_EXCEPTION"))
            ActionResult.Failure("Falha ao executar ação.")
        }
    }

    private fun blocked(request: ActionRequest, reason: String): ActionResult.Blocked {
        audit.record(SecurityEvent(SecurityEventType.ACTION_BLOCKED, request.actionId, reason))
        return ActionResult.Blocked("Ação bloqueada pela segurança: $reason")
    }
}
