package com.example.claudecoderemote.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import com.example.claudecoderemote.android.protocol.Envelope
import com.example.claudecoderemote.android.ui.MainScreen
import com.example.claudecoderemote.android.ui.theme.ClaudeCodeRemoteTheme
import com.example.claudecoderemote.android.viewmodel.MainViewModel
import com.example.claudecoderemote.android.viewmodel.WebSocketViewModel
import com.example.claudecoderemote.android.wearable.WearableBridge
import com.example.claudecoderemote.android.wearable.WearableCommandProcessor
import org.json.JSONObject

class MainActivity : ComponentActivity() {
    private val viewModel: MainViewModel by viewModels()
    private val wsViewModel: WebSocketViewModel by viewModels()
    private lateinit var wearableBridge: WearableBridge
    private lateinit var wearableCommandProcessor: WearableCommandProcessor

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        wearableBridge = WearableBridge(this)
        wsViewModel.attachWearableBridge(wearableBridge)

        wearableCommandProcessor = WearableCommandProcessor(
            context = this,
            onWatchAction = { envelope -> wsViewModel.forwardWatchAction(envelope) },
            onWatchPrompt = { envelope -> wsViewModel.forwardWatchPrompt(envelope) },
            onRequestDetailRequested = { /* no detail screen yet; the request is already visible in-app */ }
        )
        wearableCommandProcessor.start()

        setContent {
            ClaudeCodeRemoteTheme {
                val status by viewModel.status.collectAsState()
                val isPaired by viewModel.isPaired.collectAsState()
                val wsStatus by wsViewModel.connectionStatus.collectAsState()
                val pendingRequests by wsViewModel.pendingRequests.collectAsState()

                MainScreen(
                    isPaired = isPaired,
                    status = status,
                    webSocketStatus = wsStatus,
                    pendingRequests = pendingRequests,
                    onPair = { baseUrl, displayName -> viewModel.pair(baseUrl, displayName) },
                    onUnpair = {
                        viewModel.unpair()
                        wsViewModel.disconnect()
                    },
                    onConnectWebSocket = {
                        val baseUrl = viewModel.pcBaseUrl
                        val token = viewModel.deviceToken
                        if (baseUrl != null && token != null) {
                            wsViewModel.connect(baseUrl, token)
                        }
                    },
                    onRefresh = { viewModel.refreshStatus() },
                    onSendPrompt = { viewModel.sendPrompt(it) },
                    onRespondPermission = { requestId, decision ->
                        val payload = JSONObject()
                            .put("decision", decision)
                            .put("respondedByDeviceType", "phone")
                        wsViewModel.forwardWatchAction(
                            Envelope.build("permission.response", payload, requestId = requestId)
                        )
                    },
                    onRespondQuestionChoice = { requestId, choiceId ->
                        val payload = JSONObject().put("choiceId", choiceId)
                        wsViewModel.forwardWatchAction(
                            Envelope.build("question.response", payload, requestId = requestId)
                        )
                    },
                    onRespondQuestionText = { requestId, text ->
                        val payload = JSONObject().put("text", text)
                        wsViewModel.forwardWatchAction(
                            Envelope.build("question.response", payload, requestId = requestId)
                        )
                    }
                )
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        wearableCommandProcessor.stop()
    }
}
