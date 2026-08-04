package com.example.claudecoderemote.android.network

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.UUID

/** REST client for the PC relay server's `/api/v1/...` endpoints (spec section 9.1). */
class RelayApi(private val baseUrl: String) {
    private val client = OkHttpClient()
    private val jsonMediaType = "application/json".toMediaType()

    fun getStatus(): JSONObject {
        val request = Request.Builder().url("$baseUrl/api/v1/status").build()
        return executeJson(request)
    }

    /** Step 1 of pairing: ask the PC for a one-time token (spec 5.1 / 9.1). */
    fun pairStart(displayName: String): JSONObject {
        val body = JSONObject().put("displayName", displayName).toString().toRequestBody(jsonMediaType)
        val request = Request.Builder().url("$baseUrl/api/v1/pair/start").post(body).build()
        return executeJson(request)
    }

    /** Step 2 of pairing: exchange the one-time token for a long-lived device token. */
    fun pairComplete(token: String, deviceName: String, publicKey: String = ""): JSONObject {
        val body = JSONObject()
            .put("token", token)
            .put("deviceName", deviceName)
            .put("publicKey", publicKey)
            .toString()
            .toRequestBody(jsonMediaType)
        val request = Request.Builder().url("$baseUrl/api/v1/pair/complete").post(body).build()
        return executeJson(request)
    }

    /** Fallback prompt submission over plain HTTP (spec 5.4); the WebSocket path is preferred. */
    fun submitPrompt(
        deviceToken: String,
        text: String,
        source: String = "phone",
        clientRequestId: String = UUID.randomUUID().toString()
    ): JSONObject {
        val body = JSONObject()
            .put("text", text)
            .put("source", source)
            .put("clientRequestId", clientRequestId)
            .toString()
            .toRequestBody(jsonMediaType)
        val request = Request.Builder()
            .url("$baseUrl/api/v1/prompts")
            .header("Authorization", "Bearer $deviceToken")
            .post(body)
            .build()
        return executeJson(request)
    }

    private fun executeJson(request: Request): JSONObject {
        client.newCall(request).execute().use { response ->
            val bodyText = response.body?.string() ?: "{}"
            if (!response.isSuccessful) {
                throw RelayApiException(response.code, bodyText)
            }
            return JSONObject(bodyText)
        }
    }
}

class RelayApiException(val statusCode: Int, val bodyText: String) :
    Exception("Relay API error $statusCode: $bodyText")
