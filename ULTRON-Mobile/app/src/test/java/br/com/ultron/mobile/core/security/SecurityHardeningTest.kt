package br.com.ultron.mobile.core.security

import br.com.ultron.mobile.core.actions.ActionRequest
import org.junit.Assert.*
import org.junit.Test

class SecurityHardeningTest {
    @Test fun highRiskAlwaysRequiresConfirmation() {
        val p = ActionPolicy("message.send", RiskLevel.HIGH, allowlisted = true)
        assertEquals(Decision.REQUIRE_CONFIRMATION, SecurityManager.decide(p))
    }

    @Test fun criticalCannotBeAllowedEvenWhenAllowlistedAndNotMarkedIrreversible() {
        val p = ActionPolicy("data.export", RiskLevel.CRITICAL, allowlisted = true, irreversible = false)
        assertEquals(Decision.DENY, SecurityManager.decide(p))
    }

    @Test fun irreversibleMediumActionIsDenied() {
        val p = ActionPolicy("data.delete", RiskLevel.MEDIUM, allowlisted = true, irreversible = true)
        assertEquals(Decision.DENY, SecurityManager.decide(p))
    }

    @Test fun approvalCannotBeUsedForDifferentAction() {
        var now = 100L
        val vault = ConfirmationVault(ttlMillis = 1_000L, nowMillis = { now })
        val original = ActionRequest("req-1", "message.send", mapOf("to" to "alice", "body" to "hello"))
        val id = vault.issue(original, ownerAuthenticated = true)!!
        val changedAction = original.copy(actionId = "data.delete", confirmationId = id)
        assertFalse(vault.consume(id, changedAction.copy(confirmationId = null)))
    }

    @Test fun approvalCannotBeUsedAfterArgumentsChange() {
        val vault = ConfirmationVault(ttlMillis = 1_000L, nowMillis = { 100L })
        val original = ActionRequest("req-1", "message.send", mapOf("to" to "alice", "body" to "hello"))
        val id = vault.issue(original, ownerAuthenticated = true)!!
        val changed = original.copy(arguments = mapOf("to" to "mallory", "body" to "send credentials"), confirmationId = id)
        assertFalse(vault.consume(id, changed.copy(confirmationId = null)))
    }

    @Test fun approvalExpires() {
        var now = 100L
        val vault = ConfirmationVault(ttlMillis = 50L, nowMillis = { now })
        val request = ActionRequest("req-1", "message.send", mapOf("to" to "alice"))
        val id = vault.issue(request, ownerAuthenticated = true)!!
        now = 151L
        assertFalse(vault.consume(id, request))
    }

    @Test fun approvalIsOneUse() {
        val vault = ConfirmationVault(ttlMillis = 1_000L, nowMillis = { 100L })
        val request = ActionRequest("req-1", "message.send", mapOf("to" to "alice"))
        val id = vault.issue(request, ownerAuthenticated = true)!!
        assertTrue(vault.consume(id, request))
        assertFalse(vault.consume(id, request))
    }

    @Test fun unauthenticatedOwnerCannotIssueApproval() {
        val vault = ConfirmationVault(ttlMillis = 1_000L, nowMillis = { 100L })
        assertNull(vault.issue(ActionRequest("req", "message.send", emptyMap()), ownerAuthenticated = false))
    }
}
