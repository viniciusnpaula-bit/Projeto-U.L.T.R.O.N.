package br.com.ultron.mobile.core.security

import br.com.ultron.mobile.core.actions.ActionExecutor
import br.com.ultron.mobile.core.actions.ActionRequest
import br.com.ultron.mobile.core.actions.ActionResult
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.coroutines.Continuation
import kotlin.coroutines.EmptyCoroutineContext
import kotlin.coroutines.startCoroutine
import org.junit.Assert.*
import org.junit.Test

class ActionGatewaySecurityTest {
    private val request = ActionRequest(
        requestId = "req-1",
        actionId = "message.send",
        arguments = mapOf("to" to "owner-selected-contact", "body" to "hello")
    )

    @Test fun highRiskChallengeCannotExecuteWithoutExplicitApproval() {
        var executions = 0
        val executor = fakeExecutor { executions++; ActionResult.Success("sent") }
        val gateway = ActionGateway(
            executor = executor,
            confirmations = ConfirmationManager(now = { 100L }),
            audit = noOpAudit(),
            androidPermissionGranted = { true },
            ownerAuthenticated = { true }
            // Default explicit approval callback denies.
        )

        val challenge = runSuspend { gateway.execute(request) } as ActionResult.ConfirmationRequired
        val result = runSuspend { gateway.execute(request, challenge.confirmationId) }

        assertTrue(result is ActionResult.Blocked)
        assertEquals(0, executions)
    }

    @Test fun explicitApprovalAllowsExactlyOneBoundExecution() {
        var executions = 0
        var prompts = 0
        val executor = fakeExecutor { executions++; ActionResult.Success("sent") }
        val gateway = ActionGateway(
            executor = executor,
            confirmations = ConfirmationManager(now = { 100L }),
            audit = noOpAudit(),
            androidPermissionGranted = { true },
            ownerAuthenticated = { true },
            confirmExplicitly = { approvedRequest ->
                prompts++
                approvedRequest.actionId == request.actionId &&
                    approvedRequest.arguments == request.arguments
            }
        )

        val challenge = runSuspend { gateway.execute(request) } as ActionResult.ConfirmationRequired
        val approved = runSuspend { gateway.execute(request, challenge.confirmationId) }
        val replay = runSuspend { gateway.execute(request, challenge.confirmationId) }

        assertTrue(approved is ActionResult.Success)
        assertTrue(replay is ActionResult.Blocked)
        assertEquals(1, prompts)
        assertEquals(1, executions)
    }

    @Test fun criticalActionIsDeniedBeforeConfirmationCanBeIssued() {
        var executions = 0
        val executor = object : ActionExecutor {
            override fun policyFor(actionId: String) =
                ActionPolicy(actionId, RiskLevel.CRITICAL, allowlisted = true)
            override suspend fun execute(request: ActionRequest): ActionResult {
                executions++
                return ActionResult.Success("should never run")
            }
        }
        val gateway = ActionGateway(
            executor = executor,
            confirmations = ConfirmationManager(now = { 100L }),
            audit = noOpAudit(),
            androidPermissionGranted = { true },
            ownerAuthenticated = { true },
            confirmExplicitly = { true }
        )

        val result = runSuspend { gateway.execute(request) }
        assertTrue(result is ActionResult.Blocked)
        assertEquals(0, executions)
    }

    private fun fakeExecutor(run: () -> ActionResult) = object : ActionExecutor {
        override fun policyFor(actionId: String) =
            if (actionId == "message.send") ActionPolicy(actionId, RiskLevel.HIGH, allowlisted = true) else null
        override suspend fun execute(request: ActionRequest): ActionResult = run()
    }

    private fun noOpAudit() = object : SecurityAuditSink {
        override fun record(event: String, actionId: String, requestId: String, outcome: String) = Unit
    }

    private fun <T> runSuspend(block: suspend () -> T): T {
        var value: Result<T>? = null
        val latch = CountDownLatch(1)
        block.startCoroutine(object : Continuation<T> {
            override val context = EmptyCoroutineContext
            override fun resumeWith(result: Result<T>) {
                value = result
                latch.countDown()
            }
        })
        check(latch.await(5, TimeUnit.SECONDS)) { "Suspending test timed out" }
        return value!!.getOrThrow()
    }
}
