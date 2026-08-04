package com.example.claudecoderemote.android.protocol

import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.UUID

/**
 * Mirrors app/protocol.py's message envelope (spec section 7). Kept as a
 * thin JSONObject wrapper rather than a data class + serializer library so
 * this module doesn't need a new JSON dependency beyond what Android ships.
 */
object Envelope {
    const val PROTOCOL_VERSION = 1

    fun newId(): String = UUID.randomUUID().toString().replace("-", "")

    fun nowIso(): String {
        val format = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US)
        format.timeZone = TimeZone.getTimeZone("UTC")
        return format.format(Date())
    }

    fun build(
        type: String,
        payload: JSONObject,
        requestId: String? = null,
        sessionId: String? = null,
        pcId: String? = null,
        messageId: String = newId()
    ): JSONObject = JSONObject().apply {
        put("protocolVersion", PROTOCOL_VERSION)
        put("messageId", messageId)
        put("type", type)
        put("timestamp", nowIso())
        if (pcId != null) put("pcId", pcId)
        if (sessionId != null) put("sessionId", sessionId)
        if (requestId != null) put("requestId", requestId)
        put("payload", payload)
    }

    fun type(envelope: JSONObject): String = envelope.optString("type", "")
    fun requestId(envelope: JSONObject): String? =
        if (envelope.has("requestId") && !envelope.isNull("requestId")) envelope.getString("requestId") else null
    fun payload(envelope: JSONObject): JSONObject = envelope.optJSONObject("payload") ?: JSONObject()
}
