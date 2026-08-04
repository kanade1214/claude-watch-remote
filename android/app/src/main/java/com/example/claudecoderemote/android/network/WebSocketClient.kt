package com.example.claudecoderemote.android.network

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject

/** Wraps the `/ws/mobile` connection (spec section 6.2 / 9.1). */
class RelayWebSocketClient(
    private val listener: WebSocketListener
) {
    private val client = OkHttpClient()
    private var webSocket: WebSocket? = null

    fun connect(baseUrl: String, deviceToken: String) {
        val wsUrl = baseUrl
            .replaceFirst("https://", "wss://")
            .replaceFirst("http://", "ws://")
            .trimEnd('/') + "/ws/mobile?token=$deviceToken"
        val request = Request.Builder().url(wsUrl).build()
        webSocket = client.newWebSocket(request, listener)
    }

    fun send(envelope: JSONObject) {
        webSocket?.send(envelope.toString())
    }

    fun close() {
        webSocket?.close(1000, "Client closed")
        webSocket = null
    }
}
