package br.com.ultron.mobile.core.security

/** Immutable, code-defined allowlist. Never derive risk or allowlist from model output. */
class ActionPolicyRegistry(policies: Collection<ActionPolicy>) {
    private val byId: Map<String, ActionPolicy> = policies.associateBy { it.actionId }

    init {
        require(policies.all { it.actionId.isNotBlank() }) { "Action IDs must not be blank" }
        require(byId.size == policies.size) { "Duplicate action IDs are not allowed" }
    }

    fun policyFor(actionId: String): ActionPolicy? = byId[actionId]
}
