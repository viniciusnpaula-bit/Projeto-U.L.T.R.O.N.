package br.com.ultron.mobile.core.conversation

import br.com.ultron.mobile.core.ai.AIProvider
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DefaultConversationEngineTest {
    private class FakeProvider(
        private val answer: Result<String> = Result.success("Resposta da IA")
    ) : AIProvider {
        override val providerId: String = "fake"
        var calls = 0
        override suspend fun generateReply(input: String, context: List<String>): Result<String> {
            calls++
            return answer
        }
    }

    private class FakeConnectivity(var current: ConnectivityStatus) : ConnectivityMonitor {
        override fun status(): ConnectivityStatus = current
    }

    @Test
    fun localStatusWorksOfflineWithoutCallingAi() = runBlocking {
        val provider = FakeProvider()
        val engine = DefaultConversationEngine(
            BasicLocalCommandRouter(), FakeConnectivity(ConnectivityStatus.OFFLINE), provider
        )
        val result = engine.respond(ConversationRequest("req-1", "status")).getOrThrow()
        assertEquals(ReplyOrigin.LOCAL_COMMAND, result.origin)
        assertTrue(result.text.contains("funcionando localmente"))
        assertEquals(0, provider.calls)
    }

    @Test
    fun unknownQuestionOfflineReturnsExplicitLocalNotice() = runBlocking {
        val provider = FakeProvider()
        val engine = DefaultConversationEngine(
            BasicLocalCommandRouter(), FakeConnectivity(ConnectivityStatus.OFFLINE), provider
        )
        val result = engine.respond(ConversationRequest("req-2", "Explique relatividade")).getOrThrow()
        assertEquals(ReplyOrigin.LOCAL_NOTICE, result.origin)
        assertTrue(result.text.contains("sem conexão"))
        assertEquals(0, provider.calls)
    }

    @Test
    fun unknownQuestionOnlineUsesProvider() = runBlocking {
        val provider = FakeProvider()
        val engine = DefaultConversationEngine(
            BasicLocalCommandRouter(), FakeConnectivity(ConnectivityStatus.ONLINE), provider
        )
        val result = engine.respond(ConversationRequest("req-3", "Explique relatividade")).getOrThrow()
        assertEquals(ReplyOrigin.ONLINE_AI, result.origin)
        assertEquals("fake", result.providerId)
        assertEquals("Resposta da IA", result.text)
        assertEquals(1, provider.calls)
    }

    @Test
    fun invalidInputIsRejected() = runBlocking {
        val provider = FakeProvider()
        val engine = DefaultConversationEngine(
            BasicLocalCommandRouter(), FakeConnectivity(ConnectivityStatus.ONLINE), provider
        )
        val result = engine.respond(ConversationRequest("req-4", "  "))
        assertFalse(result.isSuccess)
        assertEquals(0, provider.calls)
    }
}
