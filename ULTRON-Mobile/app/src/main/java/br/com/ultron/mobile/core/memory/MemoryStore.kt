package br.com.ultron.mobile.core.memory

data class MemoryEntry(
    val id: String,
    val content: String,
    val createdAtEpochMillis: Long,
    val category: String
)

interface MemoryStore {
    suspend fun search(query: String, limit: Int = 20): List<MemoryEntry>
    suspend fun save(entry: MemoryEntry)
    suspend fun delete(id: String)
}
