package com.example.claudecoderemote.android.notifications

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.example.claudecoderemote.android.protocol.Envelope
import com.example.claudecoderemote.android.service.RelayConnectionService
import org.json.JSONObject

/** Handles Allow/Deny/choice taps from a notification (works whether the app is open or not). */
class NotificationActionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != NotificationHelper.ACTION_RESPOND) return

        val requestId = intent.getStringExtra(NotificationHelper.EXTRA_REQUEST_ID) ?: return
        val messageType = intent.getStringExtra(NotificationHelper.EXTRA_MESSAGE_TYPE) ?: return

        val payload = JSONObject().apply {
            intent.getStringExtra(NotificationHelper.EXTRA_DECISION)?.let {
                put("decision", it)
                put("respondedByDeviceType", "phone")
            }
            intent.getStringExtra(NotificationHelper.EXTRA_CHOICE_ID)?.let { put("choiceId", it) }
        }

        val envelope = Envelope.build(messageType, payload, requestId = requestId)
        RelayConnectionService.sendResponse(context, envelope)
        NotificationHelper.cancel(context, requestId)
    }
}
