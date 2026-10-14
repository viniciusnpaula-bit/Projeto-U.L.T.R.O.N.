package br.com.ultron.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import br.com.ultron.mobile.core.conversation.MessageRole
import br.com.ultron.mobile.ui.ChatLine
import br.com.ultron.mobile.ui.UltronViewModel

private val Background = Color(0xFF08090D)
private val Panel = Color(0xFF15171E)
private val Red = Color(0xFFE53945)
private val Muted = Color(0xFF969AA8)
private val AssistantBubble = Color(0xFF1B1D25)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { UltronChatScreen() }
    }
}

@Composable
private fun UltronChatScreen(viewModel: UltronViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    val listState = rememberLazyListState()

    LaunchedEffect(state.messages.size) {
        if (state.messages.isNotEmpty()) listState.animateScrollToItem(state.messages.lastIndex)
    }

    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize(), color = Background) {
            Column(
                modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 12.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column {
                        Text("ULTRON", color = Color.White, fontSize = 25.sp, fontWeight = FontWeight.Black, letterSpacing = 3.sp)
                        Text("ASSISTENTE PESSOAL", color = Muted, fontSize = 10.sp, letterSpacing = 2.sp)
                    }
                    Row(
                        modifier = Modifier.clip(RoundedCornerShape(20.dp)).background(Panel).padding(horizontal = 10.dp, vertical = 7.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Box(Modifier.width(7.dp).height(7.dp).clip(CircleShape).background(Red))
                        Spacer(Modifier.width(7.dp))
                        Text("LOCAL", color = Red, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                    }
                }

                Spacer(Modifier.height(14.dp))
                Text(
                    state.notice ?: "PRONTO PARA RECEBER COMANDOS",
                    color = Muted,
                    fontSize = 10.sp,
                    letterSpacing = 0.7.sp
                )
                Spacer(Modifier.height(10.dp))

                LazyColumn(
                    state = listState,
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(state.messages, key = { it.id }) { line ->
                        MessageBubble(line)
                    }
                    if (state.isProcessing) {
                        item(key = "processing") {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                CircularProgressIndicator(
                                    modifier = Modifier.width(16.dp).height(16.dp),
                                    color = Red,
                                    strokeWidth = 2.dp
                                )
                                Spacer(Modifier.width(9.dp))
                                Text("Processando...", color = Muted, fontSize = 12.sp)
                            }
                        }
                    }
                }

                Spacer(Modifier.height(10.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.Bottom
                ) {
                    OutlinedTextField(
                        value = state.input,
                        onValueChange = viewModel::updateInput,
                        modifier = Modifier.weight(1f),
                        enabled = !state.isProcessing,
                        placeholder = { Text("Fale com o ULTRON...", color = Muted) },
                        maxLines = 4,
                        shape = RoundedCornerShape(16.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White,
                            focusedBorderColor = Red,
                            unfocusedBorderColor = Color(0xFF343743),
                            cursorColor = Red,
                            focusedContainerColor = Panel,
                            unfocusedContainerColor = Panel
                        ),
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                        keyboardActions = KeyboardActions(onSend = { viewModel.send() })
                    )
                    Spacer(Modifier.width(8.dp))
                    Button(
                        onClick = viewModel::send,
                        enabled = state.input.isNotBlank() && !state.isProcessing,
                        modifier = Modifier.height(54.dp),
                        shape = RoundedCornerShape(15.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Red,
                            disabledContainerColor = Color(0xFF4A252A)
                        )
                    ) {
                        Text("ENVIAR", fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    }
                }
                Spacer(Modifier.height(5.dp))
                Text(
                    "Comandos locais: ajuda • status • versão",
                    color = Muted,
                    fontSize = 10.sp,
                    modifier = Modifier.padding(start = 4.dp, top = 4.dp, bottom = 2.dp)
                )
            }
        }
    }
}

@Composable
private fun MessageBubble(line: ChatLine) {
    val isUser = line.role == MessageRole.USER
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth(if (isUser) 0.88f else 0.94f)
                .clip(RoundedCornerShape(16.dp))
                .background(if (isUser) Color(0xFF492027) else AssistantBubble)
                .padding(horizontal = 13.dp, vertical = 11.dp)
        ) {
            Text(
                if (isUser) "SENHOR" else "ULTRON",
                color = if (isUser) Color(0xFFFF9BA2) else Red,
                fontSize = 9.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 1.2.sp
            )
            Spacer(Modifier.height(4.dp))
            Text(line.text, color = Color(0xFFF1F1F4), fontSize = 14.sp, lineHeight = 20.sp)
        }
    }
}
