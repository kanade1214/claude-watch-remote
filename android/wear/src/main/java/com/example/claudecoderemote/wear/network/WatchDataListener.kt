package com.example.claudecoderemote.wear.network

import android.content.Context
import android.util.Log
import com.google.android.gms.tasks.Tasks
import com.google.android.gms.wearable.DataClient
import com.google.android.gms.wearable.DataEvent
import com.google.android.gms.wearable.DataEventBuffer
import com.google.android.gms.wearable.DataMapItem
import com.google.android.gms.wearable.Wearable
import org.json.JSONArray
import org.json.JSONObject

private const val TAG = "WatchDataListener"
private const val PENDING_REQUESTS_PATH = "/state/pending-requests"
private const val REQUESTS_FIELD = "requestsJson"

/** Receives the phone's `/state/pending-requests` DataClient sync (spec 6.1). */
class WatchDataListener(
    private val onPendingRequestsChanged: (List<JSONObject>) -> Unit
) : DataClient.OnDataChangedListener {
    override fun onDataChanged(dataEvents: DataEventBuffer) {
        Log.d(TAG, "onDataChanged: ${dataEvents.count} event(s)")
        for (event in dataEvents) {
            Log.d(TAG, "onDataChanged: type=${event.type} path=${event.dataItem.uri.path}")
            if (event.type != DataEvent.TYPE_CHANGED) continue
            if (event.dataItem.uri.path != PENDING_REQUESTS_PATH) continue

            val dataMap = DataMapItem.fromDataItem(event.dataItem).dataMap
            val requestsJson = dataMap.getString(REQUESTS_FIELD) ?: "[]"
            val requests = runCatching { parseRequests(requestsJson) }.getOrDefault(emptyList())
            Log.d(TAG, "onDataChanged: parsed ${requests.size} pending request(s)")
            onPendingRequestsChanged(requests)
        }
    }

    companion object {
        /**
         * DataClient listeners only fire on *future* changes; fetch the
         * current snapshot once at startup so a request created before this
         * activity was open (or while it was backgrounded) isn't missed.
         */
        fun fetchCurrent(context: Context): List<JSONObject> {
            return try {
                val dataItems = Tasks.await(Wearable.getDataClient(context).dataItems)
                Log.d(TAG, "fetchCurrent: ${dataItems.count} total DataItem(s)")
                var result: List<JSONObject> = emptyList()
                for (item in dataItems) {
                    Log.d(TAG, "fetchCurrent: path=${item.uri.path}")
                    if (item.uri.path == PENDING_REQUESTS_PATH) {
                        val dataMap = DataMapItem.fromDataItem(item).dataMap
                        result = runCatching { parseRequests(dataMap.getString(REQUESTS_FIELD) ?: "[]") }
                            .getOrDefault(emptyList())
                    }
                }
                dataItems.release()
                Log.d(TAG, "fetchCurrent: parsed ${result.size} pending request(s)")
                result
            } catch (e: Exception) {
                Log.e(TAG, "fetchCurrent: FAILED", e)
                emptyList()
            }
        }

        private fun parseRequests(json: String): List<JSONObject> {
            val array = JSONArray(json)
            return (0 until array.length()).map { array.getJSONObject(it) }
        }
    }
}
