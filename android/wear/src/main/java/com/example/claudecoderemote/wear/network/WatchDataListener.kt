package com.example.claudecoderemote.wear.network

import com.google.android.gms.wearable.DataClient
import com.google.android.gms.wearable.DataEvent
import com.google.android.gms.wearable.DataEventBuffer
import com.google.android.gms.wearable.DataMapItem
import org.json.JSONArray
import org.json.JSONObject

/** Receives the phone's `/state/pending-requests` DataClient sync (spec 6.1). */
class WatchDataListener(
    private val onPendingRequestsChanged: (List<JSONObject>) -> Unit
) : DataClient.OnDataChangedListener {
    override fun onDataChanged(dataEvents: DataEventBuffer) {
        for (event in dataEvents) {
            if (event.type != DataEvent.TYPE_CHANGED) continue
            if (event.dataItem.uri.path != PENDING_REQUESTS_PATH) continue

            val dataMap = DataMapItem.fromDataItem(event.dataItem).dataMap
            val requestsJson = dataMap.getString(REQUESTS_FIELD) ?: "[]"
            val requests = runCatching { parseRequests(requestsJson) }.getOrDefault(emptyList())
            onPendingRequestsChanged(requests)
        }
    }

    private fun parseRequests(json: String): List<JSONObject> {
        val array = JSONArray(json)
        return (0 until array.length()).map { array.getJSONObject(it) }
    }

    companion object {
        const val PENDING_REQUESTS_PATH = "/state/pending-requests"
        const val REQUESTS_FIELD = "requestsJson"
    }
}
