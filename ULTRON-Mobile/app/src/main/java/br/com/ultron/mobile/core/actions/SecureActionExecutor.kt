package br.com.ultron.mobile.core.actions

import br.com.ultron.mobile.core.security.ActionPolicyRegistry
import br.com.ultron.mobile.core.security.ConfirmationVault
import br.com.ultron.mobile.core.security.Decision
import br.com.ultron.mobile.core.security.OwnerAuthenticator
import br.com.ultron.mobile.core.security.RiskLevel
import br.com.ultron.mobile.core.security.SecurityAudit
import br.com.ultron.mobile.core.security.SecurityEvent
import br.com.ultron.mobile.core.security.SecurityEventType
import br.com.ultron.mobile.core.security.SecurityManager

/**
 * Mandatory gateway for action execution. Platform-specific executors should be
 * private implementation details and never exposed directly to UI/AI callers.
 */
class SecureActionExecutor(
    private val policies: ActionPolicyRegistry,
    private val owner: OwnerAuthenticator,
    private val confirmations: ConfirmationVault,
    private val audit: SecurityAudit,
    private val permissionGranted: (String) -> Boolean = { true },
    private val delegate: ActionExecutor
) : ActionExecutor {
    override fun policyFor(actionId: String) = policies.policyFor(actionId)

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
        audit.record(SecurityEvent(SecurityEventType.CONFIRMATION_ISSUED, request.actionId, if (id == null) "ISSUE_FAILED" else "OWNER_CONFIRMED"))
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
        }
        audit.record(SecurityEvent(SecurityEventType.ACTION_ALLOWED, request.actionId, if (decision == Decision.ALLOW) "POLICY_ALLOW" else "CONFIRMED"))
        // Do not pass confirmation capability downstream; authorization is consumed here.
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
