package br.com.ultron.mobile.core.security
import br.com.ultron.mobile.core.actions.ActionExecutor
import br.com.ultron.mobile.core.actions.ActionRequest
import br.com.ultron.mobile.core.actions.ActionResult
interface SecurityAuditSink { fun record(event:String,actionId:String,requestId:String,outcome:String) }
class ActionGateway(private val executor:ActionExecutor,private val confirmations:ConfirmationManager,private val audit:SecurityAuditSink,private val androidPermissionGranted:(ActionRequest)->Boolean,private val ownerAuthenticated:()->Boolean) {
 suspend fun execute(request:ActionRequest,confirmationId:String?=null):ActionResult {
  val policy=executor.policyFor(request.actionId)
  val decision=SecurityManager.decide(policy,androidPermissionGranted(request))
  if(decision==Decision.DENY){audit.record("ACTION_BLOCKED",request.actionId,request.requestId,"DENY");return ActionResult.Blocked("Ação bloqueada pela política de segurança.")}
  if(decision==Decision.REQUIRE_CONFIRMATION) {
   if(!ownerAuthenticated()){audit.record("OWNER_AUTH_REQUIRED",request.actionId,request.requestId,"BLOCKED");return ActionResult.Blocked("Autenticação do proprietário necessária.")}
   if(confirmationId==null){val c=confirmations.issue(request.actionId,request.arguments);audit.record("CONFIRMATION_ISSUED",request.actionId,request.requestId,"PENDING");return ActionResult.ConfirmationRequired(c.id,"Confirme esta ação no dispositivo.")}
   if(!confirmations.consume(confirmationId,request.actionId,request.arguments)){audit.record("CONFIRMATION_REJECTED",request.actionId,request.requestId,"BLOCKED");return ActionResult.Blocked("Confirmação inválida, expirada ou já utilizada.")}
  }
  return try{executor.executeApproved(request).also{audit.record("ACTION_EXECUTED",request.actionId,request.requestId,if(it is ActionResult.Success)"SUCCESS" else "FAILED")}}catch(_:Exception){audit.record("ACTION_FAILED",request.actionId,request.requestId,"FAILED");ActionResult.Failure("Falha ao executar a ação.")}
 }
}