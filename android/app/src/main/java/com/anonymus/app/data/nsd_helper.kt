package com.anonymus.app.data

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Handler
import android.os.Looper
import android.util.Log
import kotlinx.coroutines.*
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.net.Socket
import java.util.Collections

class NsdHelper(context: Context, private val onServiceFound: (String) -> Unit) {

    private val nsdManager: NsdManager = context.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val serviceType = "_anonymus._tcp."
    private val mainHandler = Handler(Looper.getMainLooper())
    private var scanJob: Job? = null
    private var serviceResolved = false

    private val fallbackRunnable = Runnable {
        if (!serviceResolved) {
            Log.i("NsdHelper", "NSD timed out. Falling back to subnet port scan...")
            scanSubnet(5000)
        }
    }

    private val discoveryListener = object : NsdManager.DiscoveryListener {
        override fun onDiscoveryStarted(regType: String) {
            Log.d("NsdHelper", "Service discovery started")
        }

        override fun onServiceFound(service: NsdServiceInfo) {
            Log.d("NsdHelper", "Service discovery success: $service")
            // Custom type is unique, resolve directly
            nsdManager.resolveService(service, resolveListener)
        }

        override fun onServiceLost(service: NsdServiceInfo) {
            Log.e("NsdHelper", "service lost: $service")
        }

        override fun onDiscoveryStopped(serviceType: String) {
            Log.i("NsdHelper", "Discovery stopped: $serviceType")
        }

        override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
            Log.e("NsdHelper", "Discovery failed: Error code:$errorCode")
            try {
                nsdManager.stopServiceDiscovery(this)
            } catch (e: Exception) {}
        }

        override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {
            Log.e("NsdHelper", "Discovery failed: Error code:$errorCode")
            try {
                nsdManager.stopServiceDiscovery(this)
            } catch (e: Exception) {}
        }
    }

    private val resolveListener = object : NsdManager.ResolveListener {
        override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
            Log.e("NsdHelper", "Resolve failed: $errorCode")
        }

        override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
            Log.d("NsdHelper", "Resolve Succeeded. $serviceInfo")
            val hostAddress = serviceInfo.host.hostAddress
            if (hostAddress != null) {
                serviceResolved = true
                mainHandler.removeCallbacks(fallbackRunnable)
                onServiceFound(hostAddress)
                stopDiscovery()
            }
        }
    }

    fun discoverServices() {
        serviceResolved = false
        mainHandler.removeCallbacks(fallbackRunnable)
        try {
            nsdManager.discoverServices(serviceType, NsdManager.PROTOCOL_DNS_SD, discoveryListener)
        } catch (e: Exception) {
            Log.e("NsdHelper", "Failed to start discovery", e)
        }
        // Start 5 second fallback timer
        mainHandler.postDelayed(fallbackRunnable, 5000)
    }

    fun stopDiscovery() {
        mainHandler.removeCallbacks(fallbackRunnable)
        try {
            nsdManager.stopServiceDiscovery(discoveryListener)
        } catch (e: Exception) {
            // Might already be stopped
        }
        scanJob?.cancel()
    }

    private fun getLocalIpAddress(): String? {
        try {
            val interfaces = Collections.list(NetworkInterface.getNetworkInterfaces())
            for (intf in interfaces) {
                val addrs = Collections.list(intf.inetAddresses)
                for (addr in addrs) {
                    if (!addr.isLoopbackAddress) {
                        val sAddr = addr.hostAddress
                        if (sAddr != null) {
                            val isIPv4 = sAddr.indexOf(':') < 0
                            if (isIPv4) return sAddr
                        }
                    }
                }
            }
        } catch (ex: Exception) {
            Log.e("NsdHelper", "Error getting local IP address", ex)
        }
        return null
    }

    fun scanSubnet(port: Int) {
        val localIp = getLocalIpAddress() ?: return
        if (!localIp.contains(".")) return
        val subnet = localIp.substringBeforeLast('.') + "."

        scanJob = CoroutineScope(Dispatchers.IO).launch {
            val deferreds = (1..254).map { host ->
                async {
                    try {
                        val socket = Socket()
                        socket.connect(InetSocketAddress("$subnet$host", port), 200)
                        socket.close()
                        Log.d("NsdHelper", "Found server at $subnet$host via subnet scan")
                        if (!serviceResolved) {
                            serviceResolved = true
                            withContext(Dispatchers.Main) {
                                onServiceFound("$subnet$host")
                                stopDiscovery()
                            }
                        }
                    } catch (e: Exception) {
                        // ignore timeouts/refusals
                    }
                }
            }
            deferreds.awaitAll()
        }
    }
}
