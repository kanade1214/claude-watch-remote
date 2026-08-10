package com.example.claudecoderemote.android.notifications

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import com.example.claudecoderemote.android.MainActivity
import com.example.claudecoderemote.android.protocol.Envelope
import org.json.JSONObject

/**
 * Posts actionable notifications for permission/question requests (spec 5.6).
 * Wear OS bridges these to the Watch automatically (including their action
 * buttons) — no Watch-side code is needed for this to show up there.
 */
object NotificationHelper {
    const val CHANNEL_PERMISSION = "permission_requests"
    const val CHANNEL_QUESTION = "questions"
    // A channel's importance and vibration are fixed at creation — later
    // createNotificationChannel calls cannot change them — so changing this
    // channel's behaviour means retiring the old id for a new one.
    const val CHANNEL_ASSISTANT = "assistant_messages_v2"
    private const val CHANNEL_ASSISTANT_RETIRED = "assistant_messages"
    const val CHANNEL_SERVICE = "relay_service"

    const val ACTION_RESPOND = "com.example.claudecoderemote.android.ACTION_RESPOND"
    const val EXTRA_REQUEST_ID = "requestId"
    const val EXTRA_MESSAGE_TYPE = "messageType"
    const val EXTRA_DECISION = "decision"
    const val EXTRA_CHOICE_ID = "choiceId"

    fun ensureChannels(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_PERMISSION, "承認要求", NotificationManager.IMPORTANCE_HIGH).apply {
                enableVibration(true)
            }
        )
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_QUESTION, "Claudeからの質問", NotificationManager.IMPORTANCE_HIGH).apply {
                enableVibration(true)
            }
        )
        manager.deleteNotificationChannel(CHANNEL_ASSISTANT_RETIRED)
        manager.createNotificationChannel(
            // Alerting like the other two: the point of the project is to
            // notice things while away from the PC, and a silent channel made
            // replies easy to miss entirely.
            NotificationChannel(CHANNEL_ASSISTANT, "Claudeの応答", NotificationManager.IMPORTANCE_HIGH).apply {
                enableVibration(true)
            }
        )
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_SERVICE, "接続状態", NotificationManager.IMPORTANCE_LOW)
        )
    }

    fun serviceNotification(context: Context, statusText: String): Notification {
        return NotificationCompat.Builder(context, CHANNEL_SERVICE)
            .setContentTitle("Claude Watch Remote")
            .setContentText(statusText)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setOngoing(true)
            .setContentIntent(openAppIntent(context))
            .build()
    }

    fun notifyPermissionRequest(context: Context, envelope: JSONObject) {
        val requestId = Envelope.requestId(envelope) ?: return
        val payload = Envelope.payload(envelope)
        val toolName = payload.optString("toolName")
        val riskLevel = payload.optString("riskLevel")
        val summary = payload.optString("summary", toolName)
        val command = payload.optJSONObject("toolInput")?.optString("command").orEmpty()

        val builder = NotificationCompat.Builder(context, CHANNEL_PERMISSION)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle("承認要求: $toolName (危険度: $riskLevel)")
            .setContentText(if (command.isNotBlank()) command else summary)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setAutoCancel(true)
            .setContentIntent(openAppIntent(context))
            .addAction(
                actionFor(context, requestId, "拒否", "permission.response", decision = "deny")
            )

        // High risk: no one-tap allow from the notification (spec section 12).
        if (riskLevel != "high") {
            builder.addAction(
                actionFor(context, requestId, "承認", "permission.response", decision = "allow")
            )
        }

        notify(context, requestId, builder.build())
    }

    fun notifyQuestionRequest(context: Context, envelope: JSONObject) {
        val requestId = Envelope.requestId(envelope) ?: return
        val payload = Envelope.payload(envelope)
        val question = payload.optString("question")
        val choices = payload.optJSONArray("choices")

        val builder = NotificationCompat.Builder(context, CHANNEL_QUESTION)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Claudeからの質問")
            .setContentText(question)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(openAppIntent(context))

        if (choices != null) {
            for (i in 0 until minOf(choices.length(), 3)) {
                val choice = choices.getJSONObject(i)
                builder.addAction(
                    actionFor(
                        context,
                        requestId,
                        choice.getString("label"),
                        "question.response",
                        choiceId = choice.getString("id")
                    )
                )
            }
        }

        notify(context, requestId, builder.build())
    }

    /**
     * Shows the text Claude just replied with. Display-only — an
     * `assistant.message` carries no requestId and has no action buttons,
     * so BigTextStyle is what makes it useful on a watch face.
     */
    fun notifyAssistantMessage(context: Context, envelope: JSONObject) {
        val payload = Envelope.payload(envelope)
        val text = payload.optString("text")
        if (text.isBlank()) return

        val body = if (payload.optBoolean("truncated")) {
            "$text\n\n… (全${payload.optInt("fullLength")}文字)"
        } else {
            text
        }

        val notification = NotificationCompat.Builder(context, CHANNEL_ASSISTANT)
            .setSmallIcon(android.R.drawable.ic_menu_view)
            .setContentTitle("Claudeの応答")
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setAutoCancel(true)
            // Deliberately NOT setOnlyAlertOnce: each session reuses one
            // notification id (below), and onlyAlertOnce would make every
            // reply after the first update that slot in complete silence.
            .setContentIntent(openAppIntent(context))
            .build()

        // One slot per session, replaced on every reply — a watch should not
        // accumulate a stack of every response Claude has ever produced.
        val sessionId = envelope.optString("sessionId", "default")
        context.getSystemService(NotificationManager::class.java)
            .notify("assistant:$sessionId".hashCode(), notification)
    }

    fun cancel(context: Context, requestId: String) {
        context.getSystemService(NotificationManager::class.java).cancel(requestId.hashCode())
    }

    private fun notify(context: Context, requestId: String, notification: Notification) {
        context.getSystemService(NotificationManager::class.java).notify(requestId.hashCode(), notification)
    }

    private fun actionFor(
        context: Context,
        requestId: String,
        label: String,
        messageType: String,
        decision: String? = null,
        choiceId: String? = null
    ): NotificationCompat.Action {
        val intent = Intent(context, NotificationActionReceiver::class.java).apply {
            action = ACTION_RESPOND
            putExtra(EXTRA_REQUEST_ID, requestId)
            putExtra(EXTRA_MESSAGE_TYPE, messageType)
            decision?.let { putExtra(EXTRA_DECISION, it) }
            choiceId?.let { putExtra(EXTRA_CHOICE_ID, it) }
        }
        val pendingIntent = PendingIntent.getBroadcast(
            context,
            (requestId + label).hashCode(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Action.Builder(0, label, pendingIntent).build()
    }

    private fun openAppIntent(context: Context): PendingIntent {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        return PendingIntent.getActivity(context, 0, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }
}
