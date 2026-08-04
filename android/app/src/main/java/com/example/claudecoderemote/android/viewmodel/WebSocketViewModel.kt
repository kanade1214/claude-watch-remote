package com.example.claudecoderemote.android.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.claudecoderemote.android.network.RelayWebSocketClient
import com.example.claudecoderemote.android.network.RelayWebSocketListener
import com.example.claudecoderemote.android.protocol.Envelope
import com.example.claudecoderemote.android.wearable.WearableBridge
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * Owns the `/ws/mobile` connection to the PC and relays permission/question
 * requests to the Watch, and the Watch's decisions back to the PC. The
 * WearableBridge is injected after construction (rather than via a
 * ViewModel factory) since it needs an Android Context.
 */
class WebSocketViewModel : ViewModel() {
    private var wearableBridge: WearableBridge? = null

    private val _connectionStatus = MutableStateFlow("未接続")
    val connectionStatus: StateFlow<String> = _connectionStatus

    private val _pendingRequests = MutableStateFlow<List<JSONObject>>(emptyList())
    val pendingRequests: StateFlow<List<JSONObject>> = _pendingRequests

    private val _lastActionResult = MutableStateFlow<JSONObject?>(null)
    val lastActionResult: StateFlow<JSONObject?> = _lastActionResult

    private val listener = RelayWebSocketListener(
        onOpenCallback = { _connectionStatus.value = "接続済み" },
        onMessageCallback = { message -> handleIncomingText(message) },
        onFailureCallback = { error -> _connectionStatus.value = "WebSocket エラー: $error" }
    )
    private val client = RelayWebSocketClient(listener)

    fun attachWearableBridge(bridge: WearableBridge) {
        wearableBridge = bridge
    }

    fun connect(baseUrl: String, deviceToken: String) {
        viewModelScope.launch {
            try {
                client.connect(baseUrl, deviceToken)
            } catch (e: Exception) {
                _connectionStatus.value = "接続エラー: ${e.message}"
            }
        }
    }

    fun disconnect() {
        client.close()
        _connectionStatus.value = "未接続"
        _pendingRequests.value = emptyList()
    }

    /**
     * Sends a permission.response / question.response envelope to the PC and
     * drops it from the pending list. Used both for decisions relayed from
     * the Watch (`/watch/action`) and for decisions made directly in this
     * app (spec 5.3's "スマホで回答").
     */
    fun forwardWatchAction(envelope: JSONObject) {
        client.send(envelope)
        removePendingRequest(Envelope.requestId(envelope))
    }

    /** Called when the Watch submits a prompt (voice/quick text) via `/watch/prompt`. */
    fun forwardWatchPrompt(envelope: JSONObject) {
        client.send(envelope)
    }

    private fun handleIncomingText(message: String) {
        val envelope = try {
            JSONObject(message)
        } catch (e: Exception) {
            return
        }

        when (Envelope.type(envelope)) {
            "permission.request", "question.request" -> addPendingRequest(envelope)
            "action.result" -> {
                _lastActionResult.value = envelope
                wearableBridge?.sendActionResultToWatch(envelope)
            }
            "heartbeat" -> Unit
        }
    }

    private fun addPendingRequest(envelope: JSONObject) {
        _pendingRequests.value = _pendingRequests.value + envelope
        wearableBridge?.syncPendingRequests(_pendingRequests.value)
    }

    private fun removePendingRequest(requestId: String?) {
        if (requestId == null) return
        _pendingRequests.value = _pendingRequests.value.filterNot { Envelope.requestId(it) == requestId }
        wearableBridge?.syncPendingRequests(_pendingRequests.value)
    }

    override fun onCleared() {
        super.onCleared()
        client.close()
    }
}
