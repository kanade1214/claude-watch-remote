package com.example.claudecoderemote.android.service

import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.util.Log
import com.example.claudecoderemote.android.data.DeviceCredentialStore
import com.example.claudecoderemote.android.network.RelayWebSocketClient
import com.example.claudecoderemote.android.network.RelayWebSocketListener
import com.example.claudecoderemote.android.notifications.NotificationHelper
import com.example.claudecoderemote.android.protocol.Envelope
import com.example.claudecoderemote.android.wearable.WearableBridge
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import org.json.JSONObject

private const val TAG = "RelayConnectionService"

/**
 * Foreground Service owning the `/ws/mobile` connection (spec 10.2: "常時
 * WebSocketが必要なため、接続中はForeground Serviceを使用する"). Living here
 * instead of in a ViewModel means incoming requests can be turned into
 * notifications, and notification action taps can send a response, even
 * when no Activity is on screen.
 */
class RelayConnectionService : Service() {
    private lateinit var wearableBridge: WearableBridge
    private lateinit var credentialStore: DeviceCredentialStore
    private var client: RelayWebSocketClient? = null
    private val scope = CoroutineScope(Dispatchers.IO + Job())
    private var reconnectJob: Job? = null
    private var reconnectAttempt = 0
    @Volatile private var reconnectPending = false
    @Volatile private var stopped = false

    override fun onCreate() {
        super.onCreate()
        NotificationHelper.ensureChannels(this)
        wearableBridge = WearableBridge(this)
        credentialStore = DeviceCredentialStore(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(SERVICE_NOTIFICATION_ID, NotificationHelper.serviceNotification(this, connectionStatus.value))

        when (intent?.action) {
            ACTION_SEND_RESPONSE, ACTION_SEND_PROMPT -> {
                val envelopeJson = intent.getStringExtra(EXTRA_ENVELOPE_JSON)
                if (envelopeJson != null) {
                    sendEnvelope(JSONObject(envelopeJson))
                }
            }
            ACTION_STOP -> {
                disconnect()
                stopSelf()
                return START_NOT_STICKY
            }
            else -> connect()
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        disconnect()
        scope.cancel()
        super.onDestroy()
    }

    private fun connect() {
        val baseUrl = credentialStore.pcBaseUrl
        val token = credentialStore.deviceToken
        if (baseUrl == null || token == null || client != null) return

        stopped = false
        val listener = RelayWebSocketListener(
            onOpenCallback = {
                reconnectAttempt = 0
                updateStatus("接続済み")
            },
            onMessageCallback = { message -> handleIncomingText(message) },
            onFailureCallback = { error ->
                updateStatus("WebSocket エラー: $error")
                scheduleReconnect()
            },
            onClosedCallback = {
                updateStatus("切断されました")
                scheduleReconnect()
            }
        )
        client = RelayWebSocketClient(listener).also { it.connect(baseUrl, token) }
        updateStatus("接続中...")
    }

    /**
     * OkHttp does not retry a dropped WebSocket, so without this the service
     * stays alive while silently delivering nothing — a PC agent restart or a
     * brief loss of signal was enough to stop notifications for good. Backoff
     * is capped so a PC that is off overnight does not turn the phone into a
     * tight reconnect loop.
     */
    private fun scheduleReconnect() {
        // Guard with a flag rather than reconnectJob?.isActive: closing the
        // socket below makes OkHttp fire onClosed on its own thread, which
        // re-enters here before the job exists.
        if (stopped || reconnectPending) return
        reconnectPending = true
        client?.close()
        client = null

        val delayMillis = minOf(
            RECONNECT_MAX_DELAY_MS,
            RECONNECT_BASE_DELAY_MS shl minOf(reconnectAttempt, RECONNECT_MAX_SHIFT)
        )
        reconnectAttempt++
        reconnectJob = scope.launch {
            updateStatus("再接続待機中 (${delayMillis / 1000}秒)")
            delay(delayMillis)
            reconnectPending = false
            connect()
        }
    }

    private fun disconnect() {
        stopped = true
        reconnectPending = false
        reconnectJob?.cancel()
        reconnectJob = null
        client?.close()
        client = null
        updateStatus("未接続")
    }

    private fun sendEnvelope(envelope: JSONObject) {
        if (client == null) connect()
        client?.send(envelope)
        if (Envelope.type(envelope) == "permission.response" || Envelope.type(envelope) == "question.response") {
            removePendingRequest(Envelope.requestId(envelope))
        }
    }

    private fun handleIncomingText(message: String) {
        val envelope = runCatching { JSONObject(message) }.getOrNull() ?: return
        when (Envelope.type(envelope)) {
            "permission.request" -> {
                addPendingRequest(envelope)
                NotificationHelper.notifyPermissionRequest(this, envelope)
            }
            "question.request" -> {
                addPendingRequest(envelope)
                NotificationHelper.notifyQuestionRequest(this, envelope)
            }
            // Display-only: nothing to add to pendingRequests, nothing to
            // resolve — the notification (bridged to the Watch by Wear OS) is
            // the whole feature.
            "assistant.message" -> NotificationHelper.notifyAssistantMessage(this, envelope)
            "action.result" -> {
                _lastActionResult.value = envelope
                scope.launch { wearableBridge.sendActionResultToWatch(envelope) }
                Envelope.requestId(envelope)?.let { NotificationHelper.cancel(this, it) }
            }
            "heartbeat" -> Unit
        }
    }

    private fun addPendingRequest(envelope: JSONObject) {
        _pendingRequests.value = _pendingRequests.value + envelope
        scope.launch { wearableBridge.syncPendingRequests(_pendingRequests.value) }
    }

    private fun removePendingRequest(requestId: String?) {
        if (requestId == null) return
        _pendingRequests.value = _pendingRequests.value.filterNot { Envelope.requestId(it) == requestId }
        scope.launch { wearableBridge.syncPendingRequests(_pendingRequests.value) }
    }

    private fun updateStatus(status: String) {
        Log.d(TAG, "status: $status")
        _connectionStatus.value = status
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(SERVICE_NOTIFICATION_ID, NotificationHelper.serviceNotification(this, status))
    }

    companion object {
        private const val SERVICE_NOTIFICATION_ID = 1
        private const val RECONNECT_BASE_DELAY_MS = 1_000L
        private const val RECONNECT_MAX_DELAY_MS = 60_000L
        private const val RECONNECT_MAX_SHIFT = 6
        private const val ACTION_SEND_RESPONSE = "com.example.claudecoderemote.android.SEND_RESPONSE"
        private const val ACTION_SEND_PROMPT = "com.example.claudecoderemote.android.SEND_PROMPT"
        private const val ACTION_STOP = "com.example.claudecoderemote.android.STOP"
        private const val EXTRA_ENVELOPE_JSON = "envelopeJson"

        private val _connectionStatus = MutableStateFlow("未接続")
        val connectionStatus: StateFlow<String> = _connectionStatus

        private val _pendingRequests = MutableStateFlow<List<JSONObject>>(emptyList())
        val pendingRequests: StateFlow<List<JSONObject>> = _pendingRequests

        private val _lastActionResult = MutableStateFlow<JSONObject?>(null)
        val lastActionResult: StateFlow<JSONObject?> = _lastActionResult

        fun start(context: Context) {
            context.startForegroundService(Intent(context, RelayConnectionService::class.java))
        }

        fun stop(context: Context) {
            context.startService(Intent(context, RelayConnectionService::class.java).setAction(ACTION_STOP))
        }

        fun sendResponse(context: Context, envelope: JSONObject) {
            val intent = Intent(context, RelayConnectionService::class.java)
                .setAction(ACTION_SEND_RESPONSE)
                .putExtra(EXTRA_ENVELOPE_JSON, envelope.toString())
            context.startForegroundService(intent)
        }

        fun sendPrompt(context: Context, envelope: JSONObject) {
            val intent = Intent(context, RelayConnectionService::class.java)
                .setAction(ACTION_SEND_PROMPT)
                .putExtra(EXTRA_ENVELOPE_JSON, envelope.toString())
            context.startForegroundService(intent)
        }
    }
}
