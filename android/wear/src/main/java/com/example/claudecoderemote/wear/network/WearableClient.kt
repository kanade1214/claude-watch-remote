package com.example.claudecoderemote.wear.network

import android.content.Context
import com.google.android.gms.tasks.Tasks
import com.google.android.gms.wearable.Wearable
import org.json.JSONObject

/**
 * Watch -> Phone side of the Data Layer bridge. The Watch never talks to the
 * PC directly (spec section 19, item 1: "WatchからPCへ直接通信させず") — every
 * message here goes to the paired phone, which relays it over WebSocket.
 */
class WearableClient(context: Context) {
    private val nodeClient = Wearable.getNodeClient(context)
    private val messageClient = Wearable.getMessageClient(context)

    fun sendAction(envelope: JSONObject): Boolean = sendMessage(WATCH_ACTION_PATH, envelope.toString().toByteArray())

    fun sendPrompt(envelope: JSONObject): Boolean = sendMessage(WATCH_PROMPT_PATH, envelope.toString().toByteArray())

    fun requestDetail(requestId: String): Boolean {
        val payload = JSONObject().put("requestId", requestId).toString().toByteArray()
        return sendMessage(WATCH_REQUEST_DETAIL_PATH, payload)
    }

    private fun sendMessage(path: String, payload: ByteArray): Boolean {
        return try {
            val nodes = Tasks.await(nodeClient.connectedNodes)
            for (node in nodes) {
                Tasks.await(messageClient.sendMessage(node.id, path, payload))
            }
            nodes.isNotEmpty()
        } catch (e: Exception) {
            false
        }
    }

    companion object {
        const val WATCH_ACTION_PATH = "/watch/action"
        const val WATCH_PROMPT_PATH = "/watch/prompt"
        const val WATCH_REQUEST_DETAIL_PATH = "/watch/request-detail"
    }
}
