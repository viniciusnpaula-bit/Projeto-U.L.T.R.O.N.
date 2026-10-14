package br.com.ultron.mobile.core.conversation

import br.com.ultron.mobile.core.ai.AIProvider
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.withTimeout

/**
 * Local-first conversation orchestration. The Android UI and PC Core are not dependencies.
 * Provider calls are made only when online connectivity is reported.
 */
class DefaultConversationEngine(
    private val localRouter: LocalCommandRouter,
    private val connectivity: ConnectivityMonitor,
    private val aiProvider: AIProvider,
    private val timeoutMillis: Long = 20_000L,
    private val maxHistoryMessages: Int = 12,
    private val maxMessageLength: Int = 4_000
) : ConversationEngine {
    override suspend fun respond(request: ConversationRequest): Result<ConversationReply> = runCatching {
        require(request.requestId.isNotBlank()) { "Identificador da solicitação inválido." }
        val input = request.userMessage.trim()
        require(input.isNotEmpty() && input.length <= maxMessageLength) {
            "A mensagem está vazia ou excede o limite permitido."
        }

        when (val local = localRouter.route(request.requestId, input)) {
            is LocalCommandResult.Reply -> return@runCatching ConversationReply(
                requestId = request.requestId,
                text = local.text,
                origin = ReplyOrigin.LOCAL_COMMAND
            )
            is LocalCommandResult.ActionIntent -> throw UnsupportedOperationException(
                "Intenções de ação precisam ser encaminhadas ao ActionGateway pela camada de aplicação."
            )
            LocalCommandResult.NotHandled -> Unit
        }

        if (connectivity.status() != ConnectivityStatus.ONLINE) {
            return@runCatching ConversationReply(
                requestId = request.requestId,
                text = "Estou sem conexão com a internet. Os comandos locais continuam disponíveis; a IA online está indisponível.",
                origin = ReplyOrigin.LOCAL_NOTICE
            )
        }

        val history = request.recentHistory.takeLast(maxHistoryMessages).map { message ->
            "${message.role.name}: ${message.content.take(maxMessageLength)}"
        }
        val generated = withTimeout(timeoutMillis) {
            aiProvider.generateReply(input, history).getOrThrow()
        }.trim()
        require(generated.isNotEmpty()) { "O provedor de IA retornou uma resposta vazia." }
        ConversationReply(
            requestId = request.requestId,
            text = generated,
            origin = ReplyOrigin.ONLINE_AI,
            providerId = aiProvider.providerId
        )
    }.recoverCatching { error ->
        if (error is CancellationException) throw error
        throw error
    }
}
