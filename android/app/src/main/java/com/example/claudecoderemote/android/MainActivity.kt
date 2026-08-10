package com.example.claudecoderemote.android

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import com.example.claudecoderemote.android.protocol.Envelope
import com.example.claudecoderemote.android.service.RelayConnectionService
import com.example.claudecoderemote.android.ui.MainScreen
import com.example.claudecoderemote.android.ui.theme.ClaudeCodeRemoteTheme
import com.example.claudecoderemote.android.viewmodel.MainViewModel
import com.example.claudecoderemote.android.wearable.WearableCommandProcessor
import org.json.JSONObject

class MainActivity : ComponentActivity() {
    private val viewModel: MainViewModel by viewModels()
    private lateinit var wearableCommandProcessor: WearableCommandProcessor

    private val notificationPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { /* no-op either way */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }

        wearableCommandProcessor = WearableCommandProcessor(
            context = this,
            onWatchAction = { envelope -> RelayConnectionService.sendResponse(this, envelope) },
            onWatchPrompt = { envelope -> RelayConnectionService.sendPrompt(this, envelope) },
            onRequestDetailRequested = { /* no detail screen yet; the request is already visible in-app */ }
        )
        wearableCommandProcessor.start()

        setContent {
            ClaudeCodeRemoteTheme {
                val status by viewModel.status.collectAsState()
                val isPaired by viewModel.isPaired.collectAsState()
                val wsStatus by RelayConnectionService.connectionStatus.collectAsState()
                val pendingRequests by RelayConnectionService.pendingRequests.collectAsState()

                LaunchedEffect(isPaired) {
                    if (isPaired) RelayConnectionService.start(this@MainActivity)
                }

                MainScreen(
                    isPaired = isPaired,
                    status = status,
                    webSocketStatus = wsStatus,
                    pendingRequests = pendingRequests,
                    onPair = { baseUrl, displayName -> viewModel.pair(baseUrl, displayName) },
                    onUnpair = {
                        RelayConnectionService.stop(this)
                        viewModel.unpair()
                    },
                    onConnectWebSocket = { RelayConnectionService.start(this) },
                    onRefresh = { viewModel.refreshStatus() },
                    onSendPrompt = { viewModel.sendPrompt(it) },
                    onRespondPermission = { requestId, decision ->
                        val payload = JSONObject()
                            .put("decision", decision)
                            .put("respondedByDeviceType", "phone")
                        RelayConnectionService.sendResponse(
                            this,
                            Envelope.build("permission.response", payload, requestId = requestId)
                        )
                    },
                    onRespondQuestionChoice = { requestId, choiceId ->
                        val payload = JSONObject().put("choiceId", choiceId)
                        RelayConnectionService.sendResponse(
                            this,
                            Envelope.build("question.response", payload, requestId = requestId)
                        )
                    },
                    onRespondQuestionText = { requestId, text ->
                        val payload = JSONObject().put("text", text)
                        RelayConnectionService.sendResponse(
                            this,
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
