package br.com.ultron.mobile.core.security
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

interface SecureSecretStore { fun read(key:String):String?; fun write(key:String,value:String); fun delete(key:String) }
class OwnerAuthenticator(private val store:SecureSecretStore,private val random:SecureRandom=SecureRandom(),private val iterations:Int=210_000) {
 fun isConfigured()=store.read(SALT)!=null&&store.read(HASH)!=null
 fun configurePin(pin:CharArray) {
  require(pin.size in 6..12&&pin.all(Char::isDigit)){"PIN deve ter de 6 a 12 dígitos."}
  val salt=ByteArray(16).also(random::nextBytes); val hash=derive(pin,salt)
  try { store.write(SALT,salt.hex()); store.write(HASH,hash.hex()) } finally { pin.fill('\u0000'); hash.fill(0) }
 }
 fun verifyPin(pin:CharArray):Boolean=try {
  if(!isConfigured()||pin.size !in 6..12||!pin.all(Char::isDigit)) false else {
   val salt=store.read(SALT)!!.bytes(); val expected=store.read(HASH)!!.bytes(); val actual=derive(pin,salt)
   try { MessageDigest.isEqual(expected,actual) } finally { expected.fill(0);actual.fill(0) }
  }
 } finally { pin.fill('\u0000') }
 fun removePin(){store.delete(SALT);store.delete(HASH)}
 private fun derive(pin:CharArray,salt:ByteArray):ByteArray { val spec=PBEKeySpec(pin,salt,iterations,256); return try{SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded}finally{spec.clearPassword()} }
 private fun ByteArray.hex()=joinToString(""){"%02x".format(it)}
 private fun String.bytes():ByteArray { require(length%2==0&&all{it in "0123456789abcdef"});return chunked(2).map{it.toInt(16).toByte()}.toByteArray() }
 private companion object { const val SALT="owner_pin_salt_v1";const val HASH="owner_pin_hash_v1" }
}