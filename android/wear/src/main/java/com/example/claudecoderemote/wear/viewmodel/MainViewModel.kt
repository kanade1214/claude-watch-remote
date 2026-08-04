package com.example.claudecoderemote.wear.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.claudecoderemote.wear.network.WearableClient
import com.example.claudecoderemote.wear.protocol.Envelope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import org.json.JSONObject

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val wearableClient = WearableClient(application)

    private val _pendingRequests = MutableStateFlow<List<JSONObject>>(emptyList())
    val pendingRequests: StateFlow<List<JSONObject>> = _pendingRequests

    private val _lastResultMessage = MutableStateFlow("")
    val lastResultMessage: StateFlow<String> = _lastResultMessage

    private val _phoneConnectionState = MutableStateFlow("不明")
    val phoneConnectionState: StateFlow<String> = _phoneConnectionState

    private val _pendingVoiceText = MutableStateFlow<String?>(null)
    val pendingVoiceText: StateFlow<String?> = _pendingVoiceText

    fun onVoiceRecognized(text: String) {
        _pendingVoiceText.value = text
    }

    fun cancelVoicePrompt() {
        _pendingVoiceText.value = null
    }

    /** Confirming is required — spec 11.1: "音声認識結果を確認なしで自動送信しない". */
    fun confirmVoicePrompt() {
        val text = _pendingVoiceText.value ?: return
        sendPrompt(text, source = "watch_voice")
        _pendingVoiceText.value = null
    }

    fun sendQuickPrompt(text: String) {
        sendPrompt(text, source = "watch_quick")
    }

    private fun sendPrompt(text: String, source: String) {
        val payload = JSONObject().put("text", text).put("source", source)
        viewModelScope.launch(Dispatchers.IO) {
            wearableClient.sendPrompt(Envelope.build("prompt.submit", payload))
        }
    }

    fun onPendingRequestsChanged(requests: List<JSONObject>) {
        _pendingRequests.value = requests
    }

    fun onActionResult(envelope: JSONObject) {
        val payload = Envelope.payload(envelope)
        _lastResultMessage.value = payload.optString("message", "")
    }

    fun onConnectionState(stateJson: JSONObject) {
        _phoneConnectionState.value = stateJson.optString("status", "不明")
    }

    fun respondPermission(requestId: String, decision: String) {
        send(Envelope.build("permission.response", JSONObject().put("decision", decision).put("respondedByDeviceType", "watch"), requestId))
        removePending(requestId)
    }

    fun respondQuestionChoice(requestId: String, choiceId: String) {
        send(Envelope.build("question.response", JSONObject().put("choiceId", choiceId), requestId))
        removePending(requestId)
    }

    fun requestDetail(requestId: String) {
        viewModelScope.launch(Dispatchers.IO) {
            wearableClient.requestDetail(requestId)
        }
    }

    private fun send(envelope: JSONObject) {
        viewModelScope.launch(Dispatchers.IO) {
            wearableClient.sendAction(envelope)
        }
    }

    private fun removePending(requestId: String) {
        _pendingRequests.value = _pendingRequests.value.filterNot { Envelope.requestId(it) == requestId }
    }
}
