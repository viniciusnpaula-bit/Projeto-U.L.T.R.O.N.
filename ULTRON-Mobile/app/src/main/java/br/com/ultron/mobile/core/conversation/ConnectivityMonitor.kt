package br.com.ultron.mobile.core.conversation

/** Reports whether an internet request can reasonably be attempted. */
fun interface ConnectivityMonitor {
    fun status(): ConnectivityStatus
}
