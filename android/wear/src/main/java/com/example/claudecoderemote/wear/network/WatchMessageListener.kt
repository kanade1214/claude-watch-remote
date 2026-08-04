package com.example.claudecoderemote.wear.network

import com.google.android.gms.wearable.MessageClient
import com.google.android.gms.wearable.MessageEvent
import org.json.JSONObject

/** Receives the phone's `/mobile/...` MessageClient pushes (spec 6.1). */
class WatchMessageListener(
    private val onActionResult: (JSONObject) -> Unit = {},
    private val onConnectionState: (JSONObject) -> Unit = {}
) : MessageClient.OnMessageReceivedListener {
    override fun onMessageReceived(event: MessageEvent) {
        val text = String(event.data)
        when (event.path) {
            ACTION_RESULT_PATH -> runCatching { JSONObject(text) }.onSuccess(onActionResult)
            CONNECTION_STATE_PATH -> runCatching { JSONObject(text) }.onSuccess(onConnectionState)
        }
    }

    companion object {
        const val ACTION_RESULT_PATH = "/mobile/action-result"
        const val CONNECTION_STATE_PATH = "/mobile/connection-state"
    }
}
