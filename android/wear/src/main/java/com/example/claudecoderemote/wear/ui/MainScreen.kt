package com.example.claudecoderemote.wear.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.wear.compose.material.Button
import androidx.wear.compose.material.MaterialTheme
import androidx.wear.compose.material.Text
import com.example.claudecoderemote.wear.protocol.Envelope
import org.json.JSONObject

private val QUICK_PROMPTS = listOf("テストを実行して", "続けて", "変更を元に戻して")

@Composable
fun MainScreen(
    phoneConnectionState: String,
    pendingRequests: List<JSONObject>,
    pendingVoiceText: String?,
    lastResultMessage: String,
    onStartVoicePrompt: () -> Unit,
    onSendQuickPrompt: (String) -> Unit,
    onConfirmVoicePrompt: () -> Unit,
    onCancelVoicePrompt: () -> Unit,
    onRespondPermission: (requestId: String, decision: String) -> Unit,
    onRespondQuestionChoice: (requestId: String, choiceId: String) -> Unit,
    onRequestDetail: (requestId: String) -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        when {
            pendingVoiceText != null -> VoiceConfirmScreen(pendingVoiceText, onConfirmVoicePrompt, onCancelVoicePrompt)
            pendingRequests.isNotEmpty() -> RequestScreen(
                envelope = pendingRequests.first(),
                onRespondPermission = onRespondPermission,
                onRespondQuestionChoice = onRespondQuestionChoice,
                onRequestDetail = onRequestDetail
            )
            else -> HomeScreen(phoneConnectionState, lastResultMessage, onStartVoicePrompt, onSendQuickPrompt)
        }
    }
}

@Composable
private fun HomeScreen(
    phoneConnectionState: String,
    lastResultMessage: String,
    onStartVoicePrompt: () -> Unit,
    onSendQuickPrompt: (String) -> Unit
) {
    Text(text = "Claude Remote", style = MaterialTheme.typography.title3, textAlign = TextAlign.Center)
    Text(text = "PC: $phoneConnectionState", textAlign = TextAlign.Center)
    if (lastResultMessage.isNotBlank()) {
        Text(text = lastResultMessage, textAlign = TextAlign.Center)
    }
    Button(onClick = onStartVoicePrompt) { Text(text = "音声で指示") }
    QUICK_PROMPTS.forEach { prompt ->
        Button(onClick = { onSendQuickPrompt(prompt) }) { Text(text = prompt) }
    }
}

@Composable
private fun VoiceConfirmScreen(recognizedText: String, onConfirm: () -> Unit, onCancel: () -> Unit) {
    Text(text = "送信内容", style = MaterialTheme.typography.title3, textAlign = TextAlign.Center)
    Text(text = "「$recognizedText」", textAlign = TextAlign.Center)
    Button(onClick = onConfirm) { Text(text = "送信") }
    Button(onClick = onCancel) { Text(text = "やり直す") }
}

@Composable
private fun RequestScreen(
    envelope: JSONObject,
    onRespondPermission: (String, String) -> Unit,
    onRespondQuestionChoice: (String, String) -> Unit,
    onRequestDetail: (String) -> Unit
) {
    val requestId = Envelope.requestId(envelope) ?: return
    val payload = Envelope.payload(envelope)

    when (Envelope.type(envelope)) {
        "permission.request" -> {
            val riskLevel = payload.optString("riskLevel")
            Text(text = "承認要求", style = MaterialTheme.typography.title3, textAlign = TextAlign.Center)
            Text(text = payload.optString("toolName"), textAlign = TextAlign.Center)
            Text(text = payload.optJSONObject("toolInput")?.optString("command") ?: "", textAlign = TextAlign.Center)
            Text(text = "危険度: $riskLevel", textAlign = TextAlign.Center)

            if (riskLevel == "high") {
                // spec section 12: 時計単体のワンタップ承認を禁止する。
                Text(text = "高危険度のためスマートフォンで確認してください", textAlign = TextAlign.Center)
                Button(onClick = { onRequestDetail(requestId) }) { Text(text = "スマホで確認") }
            } else {
                Button(onClick = { onRespondPermission(requestId, "allow") }) { Text(text = "承認") }
                Button(onClick = { onRespondPermission(requestId, "deny") }) { Text(text = "拒否") }
            }
        }
        "question.request" -> {
            Text(text = "Claudeからの質問", style = MaterialTheme.typography.title3, textAlign = TextAlign.Center)
            Text(text = payload.optString("question"), textAlign = TextAlign.Center)

            val choices = payload.optJSONArray("choices")
            if (choices != null && choices.length() > 0) {
                for (i in 0 until choices.length()) {
                    val choice = choices.getJSONObject(i)
                    Button(onClick = { onRespondQuestionChoice(requestId, choice.getString("id")) }) {
                        Text(text = choice.getString("label"))
                    }
                }
            } else {
                Text(text = "スマートフォンで回答してください", textAlign = TextAlign.Center)
                Button(onClick = { onRequestDetail(requestId) }) { Text(text = "スマホで回答") }
            }
        }
    }
}
