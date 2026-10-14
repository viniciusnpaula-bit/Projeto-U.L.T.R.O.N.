package br.com.ultron.mobile.core.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.nio.ByteBuffer
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** AES-GCM encrypted preferences backed by a non-exportable Android Keystore key. */
class AndroidSecureSecretStore(context: Context) : SecureSecretStore {
    private val prefs = context.applicationContext.getSharedPreferences("ultron_secure_v1", Context.MODE_PRIVATE)
    private val alias = "ultron_secure_store_key_v1"

    override fun read(key: String): String? {
        if (key.isBlank()) return null
        val raw = prefs.getString(key, null) ?: return null
        return try {
            val buffer = ByteBuffer.wrap(Base64.decode(raw, Base64.NO_WRAP))
            val ivLength = buffer.int
            require(ivLength in 12..16 && buffer.remaining() > ivLength + 16)
            val iv = ByteArray(ivLength).also(buffer::get)
            val encrypted = ByteArray(buffer.remaining()).also(buffer::get)
            Cipher.getInstance("AES/GCM/NoPadding").run {
                init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, iv))
                updateAAD(key.toByteArray(Charsets.UTF_8))
                String(doFinal(encrypted), Charsets.UTF_8)
            }
        } catch (_: Exception) {
            null
        }
    }

    override fun write(key: String, value: String) {
        require(key.isNotBlank()) { "Secret key must not be blank" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        cipher.updateAAD(key.toByteArray(Charsets.UTF_8))
        val iv = cipher.iv
        val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val packed = ByteBuffer.allocate(4 + iv.size + encrypted.size)
            .putInt(iv.size).put(iv).put(encrypted).array()
        check(prefs.edit().putString(key, Base64.encodeToString(packed, Base64.NO_WRAP)).commit()) {
            "Could not persist encrypted secret"
        }
    }

    override fun delete(key: String) {
        require(key.isNotBlank()) { "Secret key must not be blank" }
        check(prefs.edit().remove(key).commit()) { "Could not delete secret" }
    }

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                alias,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build()
        )
        return generator.generateKey()
    }
}
