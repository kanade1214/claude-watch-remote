package com.example.claudecoderemote.android.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.Button
import androidx.compose.material.Card
import androidx.compose.material.MaterialTheme
import androidx.compose.material.OutlinedTextField
import androidx.compose.material.Surface
import androidx.compose.material.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.example.claudecoderemote.android.protocol.Envelope
import org.json.JSONObject

@Composable
fun MainScreen(
    isPaired: Boolean,
    status: String,
    webSocketStatus: String,
    pendingRequests: List<JSONObject>,
    onPair: (baseUrl: String, displayName: String) -> Unit,
    onUnpair: () -> Unit,
    onConnectWebSocket: () -> Unit,
    onRefresh: () -> Unit,
    onSendPrompt: (String) -> Unit,
    onRespondPermission: (requestId: String, decision: String) -> Unit,
    onRespondQuestionChoice: (requestId: String, choiceId: String) -> Unit,
    onRespondQuestionText: (requestId: String, text: String) -> Unit
) {
    Surface(modifier = Modifier.fillMaxWidth(), color = MaterialTheme.colors.background) {
        if (!isPaired) {
            PairingForm(onPair = onPair)
        } else {
            PairedScreen(
                status = status,
                webSocketStatus = webSocketStatus,
                pendingRequests = pendingRequests,
                onUnpair = onUnpair,
                onConnectWebSocket = onConnectWebSocket,
                onRefresh = onRefresh,
                onSendPrompt = onSendPrompt,
                onRespondPermission = onRespondPermission,
                onRespondQuestionChoice = onRespondQuestionChoice,
                onRespondQuestionText = onRespondQuestionText
            )
        }
    }
}

@Composable
private fun PairingForm(onPair: (String, String) -> Unit) {
    val baseUrl = remember { mutableStateOf("http://10.0.2.2:8000") }
    val displayName = remember { mutableStateOf("My Phone") }

    Column(
        modifier = Modifier.padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text(text = "PCとペアリング", style = MaterialTheme.typography.h5)
        OutlinedTextField(
            value = baseUrl.value,
            onValueChange = { baseUrl.value = it },
            label = { Text(text = "PCのURL") },
            modifier = Modifier.fillMaxWidth()
        )
        OutlinedTextField(
            value = displayName.value,
            onValueChange = { displayName.value = it },
            label = { Text(text = "この端末の表示名") },
            modifier = Modifier.fillMaxWidth()
        )
        Button(onClick = { onPair(baseUrl.value, displayName.value) }) {
            Text(text = "ペアリング開始")
        }
    }
}

@Composable
private fun PairedScreen(
    status: String,
    webSocketStatus: String,
    pendingRequests: List<JSONObject>,
    onUnpair: () -> Unit,
    onConnectWebSocket: () -> Unit,
    onRefresh: () -> Unit,
    onSendPrompt: (String) -> Unit,
    onRespondPermission: (String, String) -> Unit,
    onRespondQuestionChoice: (String, String) -> Unit,
    onRespondQuestionText: (String, String) -> Unit
) {
    val promptText = remember { mutableStateOf("こんにちは Claude Code") }

    LazyColumn(
        modifier = Modifier.padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Text(text = "Claude Code Remote", style = MaterialTheme.typography.h5)
            Text(text = "PC 状態: $status")
            Text(text = "WebSocket 状態: $webSocketStatus")
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onRefresh) { Text(text = "状態更新") }
                Button(onClick = onConnectWebSocket) { Text(text = "WebSocket 接続") }
                Button(onClick = onUnpair) { Text(text = "ペアリング解除") }
            }
        }

        item {
            OutlinedTextField(
                value = promptText.value,
                onValueChange = { promptText.value = it },
                label = { Text(text = "送信するプロンプト") },
                modifier = Modifier.fillMaxWidth()
            )
            Button(onClick = { onSendPrompt(promptText.value) }) {
                Text(text = "プロンプト送信")
            }
        }

        if (pendingRequests.isNotEmpty()) {
            item { Text(text = "保留中の要求", style = MaterialTheme.typography.h6) }
        }

        items(pendingRequests) { envelope ->
            PendingRequestCard(
                envelope = envelope,
                onRespondPermission = onRespondPermission,
                onRespondQuestionChoice = onRespondQuestionChoice,
                onRespondQuestionText = onRespondQuestionText
            )
        }
    }
}

@Composable
private fun PendingRequestCard(
    envelope: JSONObject,
    onRespondPermission: (String, String) -> Unit,
    onRespondQuestionChoice: (String, String) -> Unit,
    onRespondQuestionText: (String, String) -> Unit
) {
    val requestId = Envelope.requestId(envelope) ?: return
    val payload = Envelope.payload(envelope)
    val type = Envelope.type(envelope)

    Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            when (type) {
                "permission.request" -> {
                    val toolName = payload.optString("toolName")
                    val summary = payload.optString("summary")
                    val riskLevel = payload.optString("riskLevel")
                    Text(text = "承認要求: $toolName")
                    Text(text = summary)
                    Text(text = "危険度: $riskLevel")
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { onRespondPermission(requestId, "allow") }) { Text(text = "承認") }
                        Button(onClick = { onRespondPermission(requestId, "deny") }) { Text(text = "拒否") }
                    }
                }
                "question.request" -> {
                    val question = payload.optString("question")
                    val choices = payload.optJSONArray("choices")
                    Text(text = "質問: $question")
                    if (choices != null && choices.length() > 0) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            for (i in 0 until choices.length()) {
                                val choice = choices.getJSONObject(i)
                                Button(onClick = {
                                    onRespondQuestionChoice(requestId, choice.getString("id"))
                                }) {
                                    Text(text = choice.getString("label"))
                                }
                            }
                        }
                    } else {
                        val answerText = remember { mutableStateOf("") }
                        OutlinedTextField(
                            value = answerText.value,
                            onValueChange = { answerText.value = it },
                            label = { Text(text = "回答") },
                            modifier = Modifier.fillMaxWidth()
                        )
                        Button(onClick = { onRespondQuestionText(requestId, answerText.value) }) {
                            Text(text = "回答を送信")
                        }
                    }
                }
            }
        }
    }
}
