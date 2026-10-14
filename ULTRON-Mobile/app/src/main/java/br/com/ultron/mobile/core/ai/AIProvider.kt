package br.com.ultron.mobile.core.ai

interface AIProvider {
    val providerId: String
    suspend fun generateReply(input: String, context: List<String> = emptyList()): Result<String>
}
