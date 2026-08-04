package com.example.claudecoderemote.android.network

import android.util.Log
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString

class RelayWebSocketListener(
    private val onOpenCallback: () -> Unit = {},
    private val onMessageCallback: (String) -> Unit = {},
    private val onFailureCallback: (String) -> Unit = {}
) : WebSocketListener() {
    override fun onOpen(webSocket: WebSocket, response: Response) {
        Log.d("RelayWebSocket", "Connected")
        onOpenCallback()
    }

    override fun onMessage(webSocket: WebSocket, text: String) {
        Log.d("RelayWebSocket", "Received: $text")
        onMessageCallback(text)
    }

    override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
        Log.d("RelayWebSocket", "Received bytes")
        onMessageCallback(bytes.utf8())
    }

    override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
        webSocket.close(code, reason)
        Log.d("RelayWebSocket", "Closing: $code / $reason")
    }

    override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
        Log.e("RelayWebSocket", "Error", t)
        onFailureCallback(t.message ?: "Unknown WebSocket failure")
    }
}
