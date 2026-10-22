# U.L.T.R.O.N. Desktop 1.9.4

The Electron shell restores the supplied 1.1.1 red-and-black interface and connects it to the Python Desktop API. Python owns the core, API, and continuous microphone loop.

The home screen shows status and system metrics returned by the local API, session activity, and quick actions routed through the core. The floating HUD shares the existing renderer status and routes its fixed quick actions through the same command flow; it does not start another microphone or API client.

Run the complete application with `iniciar_desktop.bat` from the package root. The Python launcher starts the API first, then this Electron UI, and stops the core and microphone when the window closes.

For development, install the package dependencies with `npm install`, then run `npm start` only when `ULTRON_API_URL` and `ULTRON_API_TOKEN` have been supplied by a running local Python API. The renderer can call only the named methods exposed by `preload.js`; it cannot choose arbitrary routes or access Node APIs.

`npm run dist` builds the Electron shell only. Para a versão integrada, use `ULTRON-Setup.exe` (raiz) e abra pelo `ULTRON.exe` ou pelo atalho.
