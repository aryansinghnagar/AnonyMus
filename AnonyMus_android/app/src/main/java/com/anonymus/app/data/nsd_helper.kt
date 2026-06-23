package com.anonymus.app.data

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.util.Log

class NsdHelper(context: Context, private val onServiceFound: (String) -> Unit) {

    private val nsdManager: NsdManager = context.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val serviceType = "_http._tcp."
    
    private val discoveryListener = object : NsdManager.DiscoveryListener {
        override fun onDiscoveryStarted(regType: String) {
            Log.d("NsdHelper", "Service discovery started")
        }

        override fun onServiceFound(service: NsdServiceInfo) {
            Log.d("NsdHelper", "Service discovery success: $service")
            if (service.serviceName.contains(com.anonymus.app.BuildConfig.APP_NAME)) {
                nsdManager.resolveService(service, resolveListener)
            }
        }

        override fun onServiceLost(service: NsdServiceInfo) {
            Log.e("NsdHelper", "service lost: $service")
        }

        override fun onDiscoveryStopped(serviceType: String) {
            Log.i("NsdHelper", "Discovery stopped: $serviceType")
        }

        override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
            Log.e("NsdHelper", "Discovery failed: Error code:$errorCode")
            nsdManager.stopServiceDiscovery(this)
        }

        override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {
            Log.e("NsdHelper", "Discovery failed: Error code:$errorCode")
            nsdManager.stopServiceDiscovery(this)
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
                onServiceFound(hostAddress)
                stopDiscovery()
            }
        }
    }

    fun discoverServices() {
        try {
            nsdManager.discoverServices(serviceType, NsdManager.PROTOCOL_DNS_SD, discoveryListener)
        } catch (e: Exception) {
            Log.e("NsdHelper", "Failed to start discovery", e)
        }
    }

    fun stopDiscovery() {
        try {
            nsdManager.stopServiceDiscovery(discoveryListener)
        } catch (e: Exception) {
            // Might already be stopped
        }
    }
}
