package com.example.claudecoderemote.android.wearable

import android.content.Context
import com.google.android.gms.tasks.Tasks
import com.google.android.gms.wearable.DataClient
import com.google.android.gms.wearable.MessageClient
import com.google.android.gms.wearable.NodeClient
import com.google.android.gms.wearable.PutDataMapRequest
import com.google.android.gms.wearable.Wearable
import org.json.JSONArray
import org.json.JSONObject

/**
 * Phone -> Watch side of the Wear OS Data Layer bridge (spec section 6.1).
 *
 * New/updated pending requests go through the DataClient path
 * `/state/pending-requests` (durable state sync); low-latency acks go
 * through MessageClient paths prefixed `/mobile/...` (messages the phone
 * originates for the watch to consume immediately).
 */
class WearableBridge(context: Context) {
    private val nodeClient: NodeClient = Wearable.getNodeClient(context)
    private val messageClient: MessageClient = Wearable.getMessageClient(context)
    private val dataClient: DataClient = Wearable.getDataClient(context)

    fun syncPendingRequests(requests: List<JSONObject>) {
        val array = JSONArray()
        requests.forEach { array.put(it) }

        val request = PutDataMapRequest.create(PENDING_REQUESTS_PATH).apply {
            dataMap.putString(REQUESTS_FIELD, array.toString())
            dataMap.putLong(UPDATED_AT_FIELD, System.currentTimeMillis())
        }
        dataClient.putDataItem(request.asPutDataRequest().setUrgent())
    }

    fun sendActionResultToWatch(envelope: JSONObject): Boolean =
        sendMessage(ACTION_RESULT_PATH, envelope.toString().toByteArray())

    fun sendConnectionStateToWatch(stateJson: JSONObject): Boolean =
        sendMessage(CONNECTION_STATE_PATH, stateJson.toString().toByteArray())

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
        const val PENDING_REQUESTS_PATH = "/state/pending-requests"
        const val REQUESTS_FIELD = "requestsJson"
        const val UPDATED_AT_FIELD = "updatedAt"
        const val ACTION_RESULT_PATH = "/mobile/action-result"
        const val CONNECTION_STATE_PATH = "/mobile/connection-state"
    }
}
