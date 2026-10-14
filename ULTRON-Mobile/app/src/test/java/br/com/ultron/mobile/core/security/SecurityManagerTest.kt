package br.com.ultron.mobile.core.security

import org.junit.Assert.assertEquals
import org.junit.Test

class SecurityManagerTest {
    @Test fun lowRiskAllowlistedActionIsAllowed() {
        val policy = ActionPolicy("memory.read", RiskLevel.LOW, allowlisted = true)
        assertEquals(Decision.ALLOW, SecurityManager.decide(policy))
    }

    @Test fun actionOutsideAllowlistIsDenied() {
        val policy = ActionPolicy("unknown", RiskLevel.LOW, allowlisted = false)
        assertEquals(Decision.DENY, SecurityManager.decide(policy))
    }

    @Test fun highRiskActionRequiresConfirmation() {
        val policy = ActionPolicy("message.send", RiskLevel.HIGH, allowlisted = true)
        assertEquals(Decision.REQUIRE_CONFIRMATION, SecurityManager.decide(policy))
    }

    @Test fun criticalActionIsDeniedByDefault() {
        val policy = ActionPolicy("data.wipe", RiskLevel.CRITICAL, allowlisted = true, irreversible = true)
        assertEquals(Decision.DENY, SecurityManager.decide(policy))
    }

    @Test fun missingAndroidPermissionDeniesAction() {
        val policy = ActionPolicy("media.volume", RiskLevel.MEDIUM, allowlisted = true, requiresAndroidPermission = true)
        assertEquals(Decision.DENY, SecurityManager.decide(policy, androidPermissionGranted = false))
    }
}
