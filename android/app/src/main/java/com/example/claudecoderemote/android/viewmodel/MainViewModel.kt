package com.example.claudecoderemote.android.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.claudecoderemote.android.data.DeviceCredentialStore
import com.example.claudecoderemote.android.network.RelayApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** Pairing (spec 5.1) and HTTP status/prompt fallback. */
class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val credentialStore = DeviceCredentialStore(application)

    private val _status = MutableStateFlow("未接続")
    val status: StateFlow<String> = _status

    private val _isPaired = MutableStateFlow(credentialStore.isPaired)
    val isPaired: StateFlow<Boolean> = _isPaired

    val pcBaseUrl: String?
        get() = credentialStore.pcBaseUrl

    val deviceToken: String?
        get() = credentialStore.deviceToken

    fun pair(baseUrl: String, displayName: String) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val api = RelayApi(baseUrl)
                val startResult = api.pairStart(displayName)
                val token = startResult.getString("token")
                val completeResult = api.pairComplete(token, displayName)

                credentialStore.pcBaseUrl = baseUrl
                credentialStore.deviceId = completeResult.getString("deviceId")
                credentialStore.deviceToken = completeResult.getString("deviceToken")
                _isPaired.value = true
                _status.value = "ペアリング完了"
            } catch (e: Exception) {
                _status.value = "ペアリングエラー: ${e.message}"
            }
        }
    }

    fun unpair() {
        credentialStore.clear()
        _isPaired.value = false
        _status.value = "未接続"
    }

    fun refreshStatus() {
        val baseUrl = credentialStore.pcBaseUrl ?: run {
            _status.value = "未ペアリングです"
            return
        }
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val response = RelayApi(baseUrl).getStatus()
                _status.value = response.toString()
            } catch (e: Exception) {
                _status.value = "エラー: ${e.message}"
            }
        }
    }

    fun sendPrompt(promptText: String) {
        val baseUrl = credentialStore.pcBaseUrl
        val token = credentialStore.deviceToken
        if (baseUrl == null || token == null) {
            _status.value = "未ペアリングです"
            return
        }
        viewModelScope.launch(Dispatchers.IO) {
            try {
                RelayApi(baseUrl).submitPrompt(token, promptText)
                _status.value = "プロンプト送信済み"
            } catch (e: Exception) {
                _status.value = "送信エラー: ${e.message}"
            }
        }
    }
}
