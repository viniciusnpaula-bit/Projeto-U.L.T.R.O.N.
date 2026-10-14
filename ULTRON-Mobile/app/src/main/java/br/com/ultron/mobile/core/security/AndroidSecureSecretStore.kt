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

class AndroidSecureSecretStore(context:Context):SecureSecretStore {
 private val prefs=context.applicationContext.getSharedPreferences("ultron_secure_v1",Context.MODE_PRIVATE)
 private val alias="ultron_secure_store_key_v1"
 override fun read(key:String):String? {
  val raw=prefs.getString(key,null)?:return null
  return try { val b=ByteBuffer.wrap(Base64.decode(raw,Base64.NO_WRAP));val n=b.int;require(n in 12..16&&b.remaining()>n);val iv=ByteArray(n).also(b::get);val data=ByteArray(b.remaining()).also(b::get);Cipher.getInstance("AES/GCM/NoPadding").run{init(Cipher.DECRYPT_MODE,key(),GCMParameterSpec(128,iv));String(doFinal(data),Charsets.UTF_8)} }catch(_:Exception){null}
 }
 override fun write(key:String,value:String) { val c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.ENCRYPT_MODE,key());val iv=c.iv;val data=c.doFinal(value.toByteArray());val encoded=ByteBuffer.allocate(4+iv.size+data.size).putInt(iv.size).put(iv).put(data).array();check(prefs.edit().putString(key,Base64.encodeToString(encoded,Base64.NO_WRAP)).commit()) }
 override fun delete(key:String){check(prefs.edit().remove(key).commit())}
 private fun key():SecretKey { val ks=KeyStore.getInstance("AndroidKeyStore").apply{load(null)};(ks.getKey(alias,null) as? SecretKey)?.let{return it};val g=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");g.init(KeyGenParameterSpec.Builder(alias,KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setRandomizedEncryptionRequired(true).build());return g.generateKey() }
}