package br.com.ultron.mobile.core.ai

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL

/**
 * Calls the protected ULTRON backend. No provider credential is stored in the Android app.
 * Configure the HTTPS base URL with -PULTRON_AI_BASE_URL=https://your-service.example
 */
class ProtectedBackendAIProvider(
    private val baseUrl: String,
    private val connectTimeoutMillis: Int = 5_000,
    private val readTimeoutMillis: Int = 25_000
) : AIProvider {
    override val providerId: String = "ultron-protected-groq-backend"

    override suspend fun generateReply(input: String, context: List<String>): Result<String> =
        runCatching {
            require(input.isNotBlank() && input.length <= 4_000) { "Mensagem inválida." }
            val normalized = baseUrl.trim().trimEnd('/')
            require(normalized.isNotEmpty()) { "A URL do serviço de IA não foi configurada." }
            val uri = URI(normalized)
            require(uri.scheme == "https" || (uri.scheme == "http" && uri.host in setOf("10.0.2.2", "127.0.0.1", "localhost"))) {
                "O serviço de IA precisa usar HTTPS."
            }
            withContext(Dispatchers.IO) {
                val connection = (URL("$normalized/v1/chat").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    connectTimeout = connectTimeoutMillis
                    readTimeout = readTimeoutMillis
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json; charset=utf-8")
                    setRequestProperty("Accept", "application/json")
                }
                try {
                    val history = JSONArray()
                    context.takeLast(12).forEach { line ->
                        val separator = line.indexOf(':')
                        if (separator > 0) {
                            val role = line.substring(0, separator).trim().lowercase()
                            val content = line.substring(separator + 1).trim()
                            if (role in setOf("user", "assistant") && content.isNotEmpty()) {
                                history.put(JSONObject().put("role", role).put("content", content.take(4_000)))
                            }
                        }
                    }
                    val payload = JSONObject().put("message", input).put("history", history)
                    connection.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
                    val status = connection.responseCode
                    val stream = if (status in 200..299) connection.inputStream else connection.errorStream
                    val body = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
                    if (status !in 200..299) {
                        val detail = runCatching { JSONObject(body).optString("detail") }.getOrNull()
                        throw IllegalStateException(detail?.takeIf { it.isNotBlank() }
                            ?: "O serviço de IA retornou um erro ($status).")
                    }
                    val reply = JSONObject(body).optString("reply").trim()
                    require(reply.isNotEmpty()) { "O serviço de IA retornou uma resposta vazia." }
                    reply
                } finally {
                    connection.disconnect()
                }
            }
        }
}
