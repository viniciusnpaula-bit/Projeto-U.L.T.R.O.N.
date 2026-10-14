package br.com.ultron.mobile.core.security
import android.content.Context
import android.util.Log
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
class AndroidSecurityAuditLog(context:Context):SecurityAuditSink {
 private val file=File(context.applicationContext.filesDir,"security-audit.log");private val lock=Any()
 override fun record(event:String,actionId:String,requestId:String,outcome:String) {
  val safe=listOf(event,actionId,requestId,outcome).map{it.replace(Regex("[^A-Za-z0-9_.:-]"),"_").take(96)}
  val line="${SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSZ",Locale.US).format(Date())} ${safe.joinToString(" ")}\n"
  synchronized(lock){try{if(file.exists()&&file.length()>512*1024){file.copyTo(File(file.parentFile,"security-audit.previous.log"),true);file.writeText("")};file.appendText(line)}catch(_:Exception){Log.e("ULTRON-Security","Falha ao gravar auditoria de segurança")}}
 }
}