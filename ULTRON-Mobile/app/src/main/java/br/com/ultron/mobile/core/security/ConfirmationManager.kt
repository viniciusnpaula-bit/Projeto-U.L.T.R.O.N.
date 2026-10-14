package br.com.ultron.mobile.core.security
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64
import java.util.concurrent.ConcurrentHashMap

data class ConfirmationChallenge(val id:String,val actionId:String,val expiresAtEpochMs:Long)
class ConfirmationManager(private val ttlMs:Long=60_000L, private val now:()->Long=System::currentTimeMillis, private val random:SecureRandom=SecureRandom()) {
 private data class Entry(val fingerprint:String,val expiresAt:Long)
 private val pending=ConcurrentHashMap<String,Entry>()
 fun issue(actionId:String,arguments:Map<String,String>):ConfirmationChallenge {
  require(actionId.isNotBlank())
  val id=ByteArray(32).also(random::nextBytes).let{Base64.getUrlEncoder().withoutPadding().encodeToString(it)}
  val expiry=now()+ttlMs; pending[id]=Entry(fingerprint(actionId,arguments),expiry)
  return ConfirmationChallenge(id,actionId,expiry)
 }
 fun consume(id:String,actionId:String,arguments:Map<String,String>):Boolean {
  val entry=pending.remove(id)?:return false
  if(now()>=entry.expiresAt)return false
  return MessageDigest.isEqual(entry.fingerprint.toByteArray(),fingerprint(actionId,arguments).toByteArray())
 }
 private fun fingerprint(actionId:String,args:Map<String,String>):String {
  val canonical=buildString { append(actionId.length).append(':').append(actionId); args.toSortedMap().forEach{(k,v)->append('|').append(k.length).append(':').append(k).append('=').append(v.length).append(':').append(v)} }
  return MessageDigest.getInstance("SHA-256").digest(canonical.toByteArray()).joinToString(""){"%02x".format(it)}
 }
}