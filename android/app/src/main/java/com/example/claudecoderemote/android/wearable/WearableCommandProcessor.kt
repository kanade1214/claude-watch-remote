package com.example.claudecoderemote.android.wearable

import android.content.Context
import com.google.android.gms.wearable.MessageClient
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.Wearable
import org.json.JSONObject

/** Watch -> Phone side of the Data Layer bridge: paths prefixed `/watch/...` (spec 6.1). */
class WearableCommandProcessor(
    context: Context,
    private val onWatchAction: (JSONObject) -> Unit = {},
    private val onWatchPrompt: (JSONObject) -> Unit = {},
    private val onRequestDetailRequested: (String) -> Unit = {}
) : MessageClient.OnMessageReceivedListener {
    private val messageClient = Wearable.getMessageClient(context)

    override fun onMessageReceived(event: MessageEvent) {
        val text = String(event.data)
        when (event.path) {
            WATCH_ACTION_PATH -> runCatching { JSONObject(text) }.onSuccess(onWatchAction)
            WATCH_PROMPT_PATH -> runCatching { JSONObject(text) }.onSuccess(onWatchPrompt)
            WATCH_REQUEST_DETAIL_PATH -> runCatching { JSONObject(text).getString("requestId") }
                .onSuccess(onRequestDetailRequested)
        }
    }

    fun start() {
        messageClient.addListener(this)
    }

    fun stop() {
        messageClient.removeListener(this)
    }

    companion object {
        const val WATCH_ACTION_PATH = "/watch/action"
        const val WATCH_PROMPT_PATH = "/watch/prompt"
        const val WATCH_REQUEST_DETAIL_PATH = "/watch/request-detail"
    }
}
