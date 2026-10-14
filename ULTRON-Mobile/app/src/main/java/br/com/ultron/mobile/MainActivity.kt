package br.com.ultron.mobile

import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.com.ultron.mobile.core.actions.ActionExecutor
import br.com.ultron.mobile.core.actions.ActionRequest
import br.com.ultron.mobile.core.actions.ActionResult
import br.com.ultron.mobile.core.security.ActionGateway
import br.com.ultron.mobile.core.security.ActionPolicy
import br.com.ultron.mobile.core.security.AndroidOwnerAuthenticator
import br.com.ultron.mobile.core.security.ConfirmationManager
import br.com.ultron.mobile.core.security.RiskLevel
import br.com.ultron.mobile.core.security.SecurityAuditSink
import kotlinx.coroutines.launch
import java.util.UUID

private val Background = Color(0xFF08090D)
private val Panel = Color(0xFF15171E)
private val Red = Color(0xFFE53945)
private val Muted = Color(0xFF969AA8)
private const val STATUS_ACTION_ID = "mobile.security_status"

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { UltronApp() }
    }
}

/**
 * Only a harmless security-status diagnostic is currently allowlisted here.
 * No Windows/system-control actions are registered until their real handlers exist.
 */
private class MobileStatusExecutor : ActionExecutor {
    private val statusPolicy = ActionPolicy(
        actionId = STATUS_ACTION_ID,
        risk = RiskLevel.LOW,
        allowlisted = true
    )

    override fun policyFor(actionId: String): ActionPolicy? =
        if (actionId == statusPolicy.actionId) statusPolicy else null

    override suspend fun execute(request: ActionRequest): ActionResult =
        if (request.actionId == STATUS_ACTION_ID) {
            ActionResult.Success("Gateway ativo. Ações de sistema ainda não conectadas.")
        } else {
            ActionResult.Blocked("Ação não permitida.")
        }
}

@Composable
private fun UltronApp() {
    val context = androidx.compose.ui.platform.LocalContext.current
    val authenticator = remember(context) { AndroidOwnerAuthenticator(context.applicationContext) }
    val gateway = remember(authenticator) {
        ActionGateway(
            executor = MobileStatusExecutor(),
            confirmations = ConfirmationManager(),
            audit = SecurityAuditSink { event, actionId, requestId, outcome ->
                // Metadata only: never log PINs, arguments, confirmation IDs or secrets.
                Log.i("ULTRON_SECURITY", "event=$event;action=$actionId;request=$requestId;outcome=$outcome")
            },
            androidPermissionGranted = { true },
            ownerAuthenticated = { authenticator.isAuthenticated() },
            confirmExplicitly = { false }
        )
    }
    val scope = rememberCoroutineScope()
    var pin by remember { mutableStateOf("") }
    var enrolled by remember { mutableStateOf(authenticator.hasEnrollment()) }
    var authenticated by remember { mutableStateOf(authenticator.isAuthenticated()) }
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("AUTENTICAÇÃO NECESSÁRIA") }
    var selectedTab by remember { mutableStateOf("INÍCIO") }

    val pulse = rememberInfiniteTransition(label = "corePulse")
    val glow by pulse.animateFloat(
        initialValue = 0.55f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1500), RepeatMode.Reverse),
        label = "glow"
    )

    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize(), color = Background) {
            Column(
                modifier = Modifier.fillMaxSize().padding(horizontal = 22.dp, vertical = 18.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text("ULTRON", color = Color.White, fontSize = 25.sp, fontWeight = FontWeight.Black, letterSpacing = 3.sp)
                        Text("ASSISTENTE PESSOAL", color = Muted, fontSize = 10.sp, letterSpacing = 2.sp)
                    }
                    Box(modifier = Modifier.clip(RoundedCornerShape(20.dp)).background(Panel).padding(horizontal = 12.dp, vertical = 8.dp)) {
                        Text(if (authenticated) "● AUTENTICADO" else "● BLOQUEADO", color = if (authenticated) Color(0xFF69D69A) else Red, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                    }
                }

                Spacer(Modifier.height(20.dp))
                Box(contentAlignment = Alignment.Center, modifier = Modifier.size(190.dp)) {
                    Box(Modifier.size(184.dp).alpha(glow * 0.18f).clip(CircleShape).background(Brush.radialGradient(listOf(Red, Color.Transparent))))
                    Box(Modifier.size(148.dp).clip(CircleShape).background(Brush.radialGradient(listOf(Color(0xFF45151B), Color(0xFF171017), Background))))
                    Box(Modifier.size(108.dp).clip(CircleShape).background(Brush.radialGradient(listOf(Color(0xFFFF6870), Color(0xFF9F1C2B), Color(0xFF240B10)))))
                    Box(Modifier.size(78.dp).clip(CircleShape).background(Brush.radialGradient(listOf(Color(0xFF171920), Color(0xFF050609)))))
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("U", color = Color.White, fontSize = 38.sp, fontWeight = FontWeight.ExtraLight)
                        Text("CORE", color = Red, fontSize = 8.sp, letterSpacing = 3.sp)
                    }
                }

                Spacer(Modifier.height(8.dp))
                Text(status, color = Red, fontSize = 11.sp, letterSpacing = 1.3.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(16.dp))

                if (!authenticated) {
                    Text(
                        if (enrolled) "Digite seu PIN de proprietário" else "Crie um PIN de proprietário com 6 ou mais dígitos",
                        color = Color.White,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium
                    )
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = pin,
                        onValueChange = { value -> if (value.length <= 12 && value.all(Char::isDigit)) pin = value },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        enabled = !busy,
                        label = { Text("PIN", color = Muted) },
                        visualTransformation = PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White,
                            focusedBorderColor = Red,
                            unfocusedBorderColor = Muted,
                            cursorColor = Red
                        )
                    )
                    Spacer(Modifier.height(10.dp))
                    Button(
                        enabled = !busy && pin.length >= 6,
                        onClick = {
                            val submittedPin = pin.toCharArray()
                            pin = ""
                            busy = true
                            scope.launch {
                                try {
                                    if (!enrolled) {
                                        val success = authenticator.enroll(submittedPin)
                                        enrolled = authenticator.hasEnrollment()
                                        authenticated = authenticator.isAuthenticated()
                                        status = if (success && authenticated) "PIN CONFIGURADO" else "NÃO FOI POSSÍVEL CONFIGURAR O PIN"
                                    } else {
                                        val success = authenticator.verifyPin(submittedPin)
                                        authenticated = success && authenticator.isAuthenticated()
                                        status = if (authenticated) "AUTENTICAÇÃO CONCLUÍDA" else "PIN INVÁLIDO OU ACESSO TEMPORARIAMENTE BLOQUEADO"
                                    }
                                } catch (_: Exception) {
                                    status = "FALHA DE AUTENTICAÇÃO"
                                    authenticated = false
                                } finally {
                                    submittedPin.fill('\u0000')
                                    busy = false
                                }
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = Red),
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth().height(50.dp)
                    ) {
                        Text(if (busy) "AGUARDE..." else if (enrolled) "AUTENTICAR" else "CONFIGURAR PIN", color = Color.White, fontWeight = FontWeight.Bold)
                    }
                    Text("O PIN não é registrado nos logs. A sessão expira automaticamente.", color = Muted, fontSize = 10.sp)
                } else {
                    Text("Sessão do proprietário ativa", color = Color(0xFF69D69A), fontSize = 14.sp, fontWeight = FontWeight.Medium)
                    Spacer(Modifier.height(10.dp))
                    Button(
                        onClick = {
                            busy = true
                            scope.launch {
                                val result = gateway.execute(
                                    ActionRequest(
                                        requestId = UUID.randomUUID().toString(),
                                        actionId = STATUS_ACTION_ID,
                                        arguments = emptyMap()
                                    )
                                )
                                status = when (result) {
                                    is ActionResult.Success -> result.summary
                                    is ActionResult.Failure -> result.reason
                                    is ActionResult.Blocked -> result.reason
                                    is ActionResult.ConfirmationRequired -> "A confirmação é necessária antes de continuar."
                                }
                                authenticated = authenticator.isAuthenticated()
                                busy = false
                            }
                        },
                        enabled = !busy && authenticator.isAuthenticated(),
                        colors = ButtonDefaults.buttonColors(containerColor = Red),
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth().height(50.dp)
                    ) {
                        Text(if (busy) "VERIFICANDO..." else "TESTAR ACTION GATEWAY", color = Color.White, fontWeight = FontWeight.Bold)
                    }
                    Spacer(Modifier.height(8.dp))
                    Text("Teste inofensivo: não controla o telefone nem o PC.", color = Muted, fontSize = 10.sp)
                }

                Spacer(Modifier.height(18.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                    QuickCard("CONVERSAS", "Histórico indisponível", Modifier.weight(1f)) { selectedTab = "CONVERSAS"; status = "HISTÓRICO AINDA NÃO CONECTADO" }
                    QuickCard("CONTROLES", "Ações protegidas", Modifier.weight(1f)) { selectedTab = "CONTROLES"; status = "AÇÕES DE SISTEMA NÃO CONECTADAS" }
                }
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                    QuickCard("ATIVIDADES", "Auditoria", Modifier.weight(1f)) { selectedTab = "ATIVIDADES"; status = "AUDITORIA DE SEGURANÇA ATIVA" }
                    QuickCard("CONFIGURAÇÕES", "PIN e segurança", Modifier.weight(1f)) { selectedTab = "CONFIGURAÇÕES"; status = if (enrolled) "PIN CONFIGURADO" else "CONFIGURE O PIN DO PROPRIETÁRIO" }
                }
                Spacer(Modifier.weight(1f))
                Text("FASE 1 • SEGURANÇA NATIVA", color = Muted, fontSize = 10.sp, letterSpacing = 1.5.sp)
                Text("Selecionado: $selectedTab", color = Muted.copy(alpha = 0.65f), fontSize = 9.sp)
            }
        }
    }
}

@Composable
private fun QuickCard(title: String, subtitle: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        modifier = modifier.height(88.dp),
        color = Panel,
        shape = RoundedCornerShape(16.dp)
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.Center) {
            Text(title, color = Color.White, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.5.sp)
            Spacer(Modifier.height(5.dp))
            Text(subtitle, color = Muted, fontSize = 11.sp)
        }
    }
}
