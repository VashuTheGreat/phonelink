package com.phonelink

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.telecom.TelecomManager
import androidx.annotation.RequiresApi
import androidx.core.content.ContextCompat
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod

class PhoneCallModule(reactContext: ReactApplicationContext) : ReactContextBaseJavaModule(reactContext) {

    override fun getName(): String = "PhoneCallModule"

    @SuppressLint("MissingPermission")
    @ReactMethod
    fun makeCall(number: String) {
        val context = reactApplicationContext

        val callPermission = ContextCompat.checkSelfPermission(context, Manifest.permission.CALL_PHONE)

        if (callPermission == PackageManager.PERMISSION_GRANTED) {
            val intent = Intent(Intent.ACTION_CALL).apply {
                data = Uri.parse("tel:$number")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
        } else {
            val intent = Intent(Intent.ACTION_DIAL).apply {
                data = Uri.parse("tel:$number")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
        }
    }

    @SuppressLint("MissingPermission")
    @ReactMethod
    fun answerCall() {
        val telecomManager = reactApplicationContext.getSystemService(Context.TELECOM_SERVICE) as? TelecomManager
        val hasPermission = ContextCompat.checkSelfPermission(
            reactApplicationContext, Manifest.permission.ANSWER_PHONE_CALLS
        ) == PackageManager.PERMISSION_GRANTED

        if (telecomManager != null && hasPermission) {
            try {
                telecomManager.acceptRingingCall()
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    @SuppressLint("MissingPermission")
    @ReactMethod
    fun hangupCall() {
        val telecomManager = reactApplicationContext.getSystemService(Context.TELECOM_SERVICE) as? TelecomManager
        val hasPermission = ContextCompat.checkSelfPermission(
            reactApplicationContext, Manifest.permission.ANSWER_PHONE_CALLS
        ) == PackageManager.PERMISSION_GRANTED

        if (telecomManager != null && hasPermission) {
            try {
                telecomManager.endCall()
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }
}
