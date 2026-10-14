package br.com.ultron.mobile.core.conversation

/**
 * Small, deterministic offline command set. It performs no device actions and never
 * interprets arbitrary user text as an executable command.
 */
class BasicLocalCommandRouter(
    private val appVersion: String = "0.1.0",
    private val statusText: () -> String = { "ULTRON Mobile está funcionando localmente." }
) : LocalCommandRouter {
    override suspend fun route(requestId: String, input: String): LocalCommandResult {
        return when (input.trim().lowercase()) {
            "ajuda", "comandos", "o que você consegue fazer offline", "o que voce consegue fazer offline" ->
                LocalCommandResult.Reply(
                    "Comandos offline disponíveis: ajuda, status e versão. " +
                        "A conversa com a IA exige conexão com a internet."
                )
            "status", "status do ultron", "como você está", "como voce esta" ->
                LocalCommandResult.Reply(statusText())
            "versão", "versao", "versão do app", "versao do app" ->
                LocalCommandResult.Reply("ULTRON Mobile versão $appVersion.")
            else -> LocalCommandResult.NotHandled
        }
    }
}
