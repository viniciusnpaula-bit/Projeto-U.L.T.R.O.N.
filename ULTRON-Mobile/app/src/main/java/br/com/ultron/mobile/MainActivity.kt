package br.com.ultron.mobile

import android.os.Bundle
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
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val Background = Color(0xFF08090D)
private val Panel = Color(0xFF15171E)
private val Red = Color(0xFFE53945)
private val Muted = Color(0xFF969AA8)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { UltronApp() }
    }
}

@Composable
private fun UltronApp() {
    var status by remember { mutableStateOf("SISTEMA PRONTO") }
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
                    Box(
                        modifier = Modifier.clip(RoundedCornerShape(20.dp)).background(Panel).padding(horizontal = 12.dp, vertical = 8.dp)
                    ) {
                        Text("● LOCAL", color = Red, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                    }
                }

                Spacer(Modifier.height(38.dp))
                Box(contentAlignment = Alignment.Center, modifier = Modifier.size(250.dp)) {
                    Box(
                        Modifier.size(238.dp).alpha(glow * 0.18f).clip(CircleShape)
                            .background(Brush.radialGradient(listOf(Red, Color.Transparent)))
                    )
                    Box(
                        Modifier.size(190.dp).clip(CircleShape)
                            .background(Brush.radialGradient(listOf(Color(0xFF45151B), Color(0xFF171017), Background)))
                    )
                    Box(
                        Modifier.size(142.dp).clip(CircleShape)
                            .background(Brush.radialGradient(listOf(Color(0xFFFF6870), Color(0xFF9F1C2B), Color(0xFF240B10))))
                    )
                    Box(
                        Modifier.size(104.dp).clip(CircleShape)
                            .background(Brush.radialGradient(listOf(Color(0xFF171920), Color(0xFF050609))))
                    )
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("U", color = Color.White, fontSize = 48.sp, fontWeight = FontWeight.ExtraLight)
                        Text("CORE", color = Red, fontSize = 9.sp, letterSpacing = 3.sp)
                    }
                }

                Spacer(Modifier.height(12.dp))
                Text(status, color = Red, fontSize = 11.sp, letterSpacing = 2.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(25.dp))
                Button(
                    onClick = { status = "VOZ AINDA NÃO CONFIGURADA" },
                    colors = ButtonDefaults.buttonColors(containerColor = Red),
                    shape = RoundedCornerShape(16.dp),
                    modifier = Modifier.fillMaxWidth().height(54.dp)
                ) {
                    Text("INICIAR VOZ", color = Color.White, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                }
                Spacer(Modifier.height(14.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                    QuickCard("CONVERSAS", "Histórico", Modifier.weight(1f)) { selectedTab = "CONVERSAS"; status = "MÓDULO EM CONSTRUÇÃO" }
                    QuickCard("CONTROLES", "Ações locais", Modifier.weight(1f)) { selectedTab = "CONTROLES"; status = "MÓDULO EM CONSTRUÇÃO" }
                }
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                    QuickCard("ATIVIDADES", "Auditoria", Modifier.weight(1f)) { selectedTab = "ATIVIDADES"; status = "MÓDULO EM CONSTRUÇÃO" }
                    QuickCard("CONFIGURAÇÕES", "IA e segurança", Modifier.weight(1f)) { selectedTab = "CONFIGURAÇÕES"; status = "MÓDULO EM CONSTRUÇÃO" }
                }
                Spacer(Modifier.weight(1f))
                Text("FASE 1 • BASE NATIVA", color = Muted, fontSize = 10.sp, letterSpacing = 1.5.sp)
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
