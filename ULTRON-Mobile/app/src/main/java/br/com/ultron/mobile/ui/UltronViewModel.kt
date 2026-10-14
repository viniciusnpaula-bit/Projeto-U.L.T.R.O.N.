package br.com.ultron.mobile.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.com.ultron.mobile.core.ai.UnconfiguredAIProvider
import br.com.ultron.mobile.core.conversation.AndroidConnectivityMonitor
import br.com.ultron.mobile.core.conversation.BasicLocalCommandRouter
import br.com.ultron.mobile.core.conversation.ConversationEngine
import br.com.ultron.mobile.core.conversation.ConversationMessage
import br.com.ultron.mobile.core.conversation.ConversationRequest
import br.com.ultron.mobile.core.conversation.DefaultConversationEngine
import br.com.ultron.mobile.core.conversation.MessageRole
import br.com.ultron.mobile.core.conversation.ReplyOrigin
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.UUID

data class ChatLine(
    val id: String,
    val role: MessageRole,
    val text: String,
    val origin: ReplyOrigin? = null
)

data class ChatUiState(
    val messages: List<ChatLine> = listOf(
        ChatLine(
            id = "welcome",
            role = MessageRole.ASSISTANT,
            text = "Olá, senhor. Sou o ULTRON Mobile. Posso responder a comandos locais como “ajuda”, “status” e “versão”."
        )
    ),
    val input: String = "",
    val isProcessing: Boolean = false,
    val notice: String? = "IA online ainda não configurada; comandos locais funcionam sem o PC."
)

class UltronViewModel(application: Application) : AndroidViewModel(application) {
    private val engine: ConversationEngine = DefaultConversationEngine(
        localRouter = BasicLocalCommandRouter(),
        connectivity = AndroidConnectivityMonitor(application),
        aiProvider = UnconfiguredAIProvider()
    )

    private val _state = MutableStateFlow(ChatUiState())
    val state: StateFlow<ChatUiState> = _state.asStateFlow()

    fun updateInput(value: String) {
        if (value.length <= 4_000) _state.value = _state.value.copy(input = value)
    }

    fun send() {
        val current = _state.value
        val text = current.input.trim()
        if (text.isEmpty() || current.isProcessing) return

        val requestId = UUID.randomUUID().toString()
        val userLine = ChatLine(UUID.randomUUID().toString(), MessageRole.USER, text)
        _state.value = current.copy(
            messages = current.messages + userLine,
            input = "",
            isProcessing = true,
            notice = null
        )

        viewModelScope.launch {
            try {
                val history = _state.value.messages.takeLast(12).map {
                    ConversationMessage(
                        id = it.id,
                        role = it.role,
                        content = it.text,
                        createdAtEpochMillis = 0L
                    )
                }
                val result = engine.respond(
                    ConversationRequest(
                        requestId = requestId,
                        userMessage = text,
                        recentHistory = history
                    )
                )
                val reply = result.getOrElse { error ->
                    val message = when (error) {
                        is CancellationException -> throw error
                        else -> "Não foi possível processar a mensagem. A integração segura com a IA online ainda está pendente."
                    }
                    br.com.ultron.mobile.core.conversation.ConversationReply(
                        requestId = requestId,
                        text = message,
                        origin = ReplyOrigin.LOCAL_NOTICE
                    )
                }
                val newNotice = when (reply.origin) {
                    ReplyOrigin.ONLINE_AI -> "IA online"
                    ReplyOrigin.LOCAL_COMMAND -> "Processado localmente"
                    ReplyOrigin.LOCAL_NOTICE -> "Aviso"
                    ReplyOrigin.ACTION_RESULT -> "Resultado de segurança"
                }
                _state.value = _state.value.copy(
                    messages = _state.value.messages + ChatLine(
                        id = UUID.randomUUID().toString(),
                        role = MessageRole.ASSISTANT,
                        text = reply.text,
                        origin = reply.origin
                    ),
                    isProcessing = false,
                    notice = newNotice
                )
            } catch (error: CancellationException) {
                throw error
            } catch (_: Exception) {
                _state.value = _state.value.copy(
                    messages = _state.value.messages + ChatLine(
                        id = UUID.randomUUID().toString(),
                        role = MessageRole.ASSISTANT,
                        text = "Ocorreu um erro ao processar a mensagem."
                    ),
                    isProcessing = false,
                    notice = "Erro"
                )
            }
        }
    }
}
