package br.com.ultron.mobile.core.ai

/**
 * Safe temporary adapter. The mobile app must not call Groq directly with a bundled API key.
 * Replace this adapter only after the protected backend contract and deployment are ready.
 */
class UnconfiguredAIProvider : AIProvider {
    override val providerId: String = "secure-backend-pending"

    override suspend fun generateReply(input: String, context: List<String>): Result<String> =
        Result.failure(IllegalStateException("O serviço protegido de IA ainda não foi configurado."))
}
