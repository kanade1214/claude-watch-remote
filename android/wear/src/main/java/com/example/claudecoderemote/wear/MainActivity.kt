package com.example.claudecoderemote.wear

import android.content.Intent
import android.os.Bundle
import android.speech.RecognizerIntent
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import com.example.claudecoderemote.wear.network.WatchDataListener
import com.example.claudecoderemote.wear.network.WatchMessageListener
import com.example.claudecoderemote.wear.ui.MainScreen
import com.example.claudecoderemote.wear.ui.theme.ClaudeCodeRemoteWearTheme
import com.example.claudecoderemote.wear.viewmodel.MainViewModel
import com.google.android.gms.wearable.Wearable
import java.util.Locale

class MainActivity : ComponentActivity() {
    private val viewModel: MainViewModel by viewModels()

    private val dataListener = WatchDataListener(onPendingRequestsChanged = { viewModel.onPendingRequestsChanged(it) })
    private val messageListener = WatchMessageListener(
        onActionResult = { viewModel.onActionResult(it) },
        onConnectionState = { viewModel.onConnectionState(it) }
    )

    private val voiceLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val text = result.data
            ?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
            ?.firstOrNull()
        if (!text.isNullOrBlank()) {
            viewModel.onVoiceRecognized(text)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        Wearable.getDataClient(this).addListener(dataListener)
        Wearable.getMessageClient(this).addListener(messageListener)

        setContent {
            ClaudeCodeRemoteWearTheme {
                val pendingRequests by viewModel.pendingRequests.collectAsState()
                val pendingVoiceText by viewModel.pendingVoiceText.collectAsState()
                val lastResultMessage by viewModel.lastResultMessage.collectAsState()
                val phoneConnectionState by viewModel.phoneConnectionState.collectAsState()

                MainScreen(
                    phoneConnectionState = phoneConnectionState,
                    pendingRequests = pendingRequests,
                    pendingVoiceText = pendingVoiceText,
                    lastResultMessage = lastResultMessage,
                    onStartVoicePrompt = { launchVoiceInput() },
                    onSendQuickPrompt = { viewModel.sendQuickPrompt(it) },
                    onConfirmVoicePrompt = { viewModel.confirmVoicePrompt() },
                    onCancelVoicePrompt = { viewModel.cancelVoicePrompt() },
                    onRespondPermission = { requestId, decision -> viewModel.respondPermission(requestId, decision) },
                    onRespondQuestionChoice = { requestId, choiceId -> viewModel.respondQuestionChoice(requestId, choiceId) },
                    onRequestDetail = { requestId -> viewModel.requestDetail(requestId) }
                )
            }
        }
    }

    private fun launchVoiceInput() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.JAPAN.toString())
        }
        voiceLauncher.launch(intent)
    }

    override fun onDestroy() {
        super.onDestroy()
        Wearable.getDataClient(this).removeListener(dataListener)
        Wearable.getMessageClient(this).removeListener(messageListener)
    }
}
