package br.com.ultron.mobile.core.security

enum class RiskLevel { LOW, MEDIUM, HIGH, CRITICAL }

enum class Decision { ALLOW, REQUIRE_CONFIRMATION, DENY }

data class ActionPolicy(
    val actionId: String,
    val risk: RiskLevel,
    val allowlisted: Boolean,
    val requiresAndroidPermission: Boolean = false,
    val irreversible: Boolean = false
)

object SecurityManager {
    fun decide(policy: ActionPolicy, androidPermissionGranted: Boolean = true): Decision {
        if (!policy.allowlisted) return Decision.DENY
        if (policy.irreversible || policy.risk == RiskLevel.CRITICAL) return Decision.DENY
        if (policy.requiresAndroidPermission && !androidPermissionGranted) return Decision.DENY
        return when (policy.risk) {
            RiskLevel.LOW, RiskLevel.MEDIUM -> Decision.ALLOW
            RiskLevel.HIGH -> Decision.REQUIRE_CONFIRMATION
            RiskLevel.CRITICAL -> Decision.DENY
        }
    }
}
