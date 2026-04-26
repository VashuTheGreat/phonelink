package com.phonelink

import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.modules.core.DeviceEventManagerModule
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.PrintWriter
import java.net.ServerSocket
import java.net.Socket
import kotlin.concurrent.thread

class HttpServerModule(reactContext: ReactApplicationContext) : ReactContextBaseJavaModule(reactContext) {

    private var serverSocket: ServerSocket? = null
    private var isRunning = false

    override fun getName(): String {
        return "HttpServerModule"
    }

    // Required stubs for NativeEventEmitter on the JS side
    @ReactMethod
    fun addListener(eventName: String) {}

    @ReactMethod
    fun removeListeners(count: Int) {}

    @ReactMethod
    fun startServer(port: Int) {
        if (isRunning) return

        isRunning = true
        thread {
            try {
                serverSocket = ServerSocket(port)
                while (isRunning) {
                    val clientSocket = serverSocket?.accept() ?: break
                    handleClient(clientSocket)
                }
            } catch (e: Exception) {
                e.printStackTrace()
            } finally {
                isRunning = false
            }
        }
    }

    @ReactMethod
    fun stopServer() {
        isRunning = false
        try {
            serverSocket?.close()
        } catch (e: Exception) {
            e.printStackTrace()
        }
        serverSocket = null
    }

    private fun handleClient(socket: Socket) {
        thread {
            try {
                val reader = BufferedReader(InputStreamReader(socket.inputStream))
                val writer = PrintWriter(socket.outputStream)

                val line = reader.readLine()
                var requestedNumber = ""
                if (line != null && line.startsWith("GET /")) {
                    val parts = line.split(" ")
                    if (parts.size > 1) {
                        requestedNumber = parts[1].substring(1).trimEnd('/')
                        if (requestedNumber.isNotEmpty() && requestedNumber != "favicon.ico") {
                            sendEvent("onCallRequested", requestedNumber)
                        }
                    }
                }

                // Proper HTTP response
                writer.print("HTTP/1.1 200 OK\r\n")
                writer.print("Content-Type: text/plain\r\n")
                writer.print("Connection: close\r\n")
                writer.print("\r\n")
                writer.print("PhoneLink: call request received for $requestedNumber\r\n")
                writer.flush()

                socket.close()
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    private fun sendEvent(eventName: String, data: String) {
        val params = Arguments.createMap()
        params.putString("number", data)
        reactApplicationContext
            .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
            .emit(eventName, params)
    }
}
