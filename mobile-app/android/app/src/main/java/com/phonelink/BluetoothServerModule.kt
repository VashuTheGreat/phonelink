package com.phonelink

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothServerSocket
import android.bluetooth.BluetoothSocket
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.modules.core.DeviceEventManagerModule
import org.json.JSONObject
import java.io.InputStream
import java.io.OutputStream
import java.util.UUID
import kotlin.concurrent.thread

class BluetoothServerModule(reactContext: ReactApplicationContext) : ReactContextBaseJavaModule(reactContext) {

    companion object {
        // Singleton instance — PhoneCallModule yahan se pause/resume karega
        private var instance: BluetoothServerModule? = null

        // Call ke dauraan RFCOMM client socket temporarily close karo
        // taaki HFP audio routing confuse na ho
        fun pauseForCall() {
            instance?.let {
                try {
                    it.clientSocket?.close()
                    it.clientSocket = null
                    it.sendEvent("onBTLog", "RFCOMM paused for call audio routing")
                    it.sendEvent("onBTStatusChanged", "call_active")
                } catch (e: Exception) { /* ignore */ }
            }
        }

        // Call khatam hone ke baad server phir se listen kare
        fun resumeAfterCall() {
            instance?.let {
                it.sendEvent("onBTLog", "Call ended — RFCOMM server resuming")
                it.sendEvent("onBTStatusChanged", "listening")
            }
        }
    }

    private val bluetoothAdapter: BluetoothAdapter? = BluetoothAdapter.getDefaultAdapter()
    private var serverSocket: BluetoothServerSocket? = null
    private var clientSocket: BluetoothSocket? = null
    private var isRunning = false
    
    // UUID for Serial Port Profile (SPP)
    private val SPP_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")

    init {
        instance = this
    }

    override fun getName(): String {
        return "BluetoothServerModule"
    }

    @ReactMethod
    fun addListener(eventName: String) {}

    @ReactMethod
    fun removeListeners(count: Int) {}

    @SuppressLint("MissingPermission")
    @ReactMethod
    fun startServer() {
        if (isRunning) return
        
        if (bluetoothAdapter == null || !bluetoothAdapter.isEnabled) {
            sendEvent("onBTLog", "Bluetooth is not supported or not enabled.")
            return
        }

        isRunning = true
        thread {
            try {
                // Try fixing port to 13 via reflection
                var successFixedPort = false
                try {
                    val method = bluetoothAdapter.javaClass.getMethod("listenUsingInsecureRfcommOn", Int::class.javaPrimitiveType)
                    serverSocket = method.invoke(bluetoothAdapter, 13) as BluetoothServerSocket?
                    successFixedPort = true
                    sendEvent("onBTLog", "Fixed Port 13 bound via reflection.")
                } catch (e: Exception) {
                    sendEvent("onBTLog", "Reflection failed, falling back to dynamic port.")
                }

                if (!successFixedPort) {
                    serverSocket = bluetoothAdapter.listenUsingRfcommWithServiceRecord("PhoneLinkBT", SPP_UUID)
                }
                
                sendEvent("onBTLog", "Bluetooth Server started, waiting for connection...")
                sendEvent("onBTStatusChanged", "listening")
                
                while (isRunning) {
                    val socket = serverSocket?.accept() ?: break
                    clientSocket = socket
                    
                    // Send handshake
                    try {
                        socket.outputStream.write("PHONELINK_READY\n".toByteArray())
                        socket.outputStream.flush()
                    } catch (e: Exception) {
                        e.printStackTrace()
                    }
                    
                    sendEvent("onBTLog", "Client connected: ${socket.remoteDevice.address}")
                    sendEvent("onBTStatusChanged", "connected")
                    handleClient(socket)
                }
            } catch (e: Exception) {
                sendEvent("onBTLog", "Server Error: ${e.message}")
            } finally {
                isRunning = false
                sendEvent("onBTStatusChanged", "disconnected")
            }
        }
    }

    @ReactMethod
    fun stopServer() {
        isRunning = false
        try {
            clientSocket?.close()
            serverSocket?.close()
        } catch (e: Exception) {
            // Ignore
        }
        clientSocket = null
        serverSocket = null
        sendEvent("onBTStatusChanged", "disconnected")
        sendEvent("onBTLog", "Bluetooth Server stopped.")
    }

    private fun handleClient(socket: BluetoothSocket) {
        var inputStream: InputStream? = null
        var outputStream: OutputStream? = null
        try {
            inputStream = socket.inputStream
            outputStream = socket.outputStream
            val buffer = ByteArray(1024)
            var bytes: Int

            while (isRunning) {
                bytes = inputStream.read(buffer)
                if (bytes == -1) break
                val incomingMessage = String(buffer, 0, bytes)
                
                try {
                    val json = JSONObject(incomingMessage)
                    val action = json.optString("action")
                    if (action.isNotEmpty()) {
                        val params = Arguments.createMap()
                        params.putString("action", action)
                        params.putString("number", json.optString("number"))
                        
                        reactApplicationContext
                            .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
                            .emit("onBTCommandReceived", params)
                    }
                } catch (e: Exception) {
                    sendEvent("onBTLog", "Invalid JSON from BT: $incomingMessage")
                }
            }
        } catch (e: Exception) {
            sendEvent("onBTLog", "Client disconnected: ${e.message}")
        } finally {
            clientSocket = null
            sendEvent("onBTStatusChanged", "listening")
        }
    }

    @ReactMethod
    fun sendData(data: String) {
        thread {
            try {
                clientSocket?.outputStream?.write(data.toByteArray())
            } catch (e: Exception) {
                sendEvent("onBTLog", "Failed to send data: ${e.message}")
            }
        }
    }

    private fun sendEvent(eventName: String, data: String) {
        val params = Arguments.createMap()
        params.putString("data", data)
        reactApplicationContext
            .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
            .emit(eventName, params)
    }
}
