package br.com.ultron.mobile.core.conversation

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities

/** Uses Android's current network capabilities; it never depends on the Windows Core. */
class AndroidConnectivityMonitor(context: Context) : ConnectivityMonitor {
    private val manager = context.applicationContext
        .getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

    override fun status(): ConnectivityStatus {
        val network = manager.activeNetwork ?: return ConnectivityStatus.OFFLINE
        val capabilities = manager.getNetworkCapabilities(network)
            ?: return ConnectivityStatus.OFFLINE
        val hasInternet = capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
        val validated = capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
        return if (hasInternet && validated) ConnectivityStatus.ONLINE else ConnectivityStatus.OFFLINE
    }
}
