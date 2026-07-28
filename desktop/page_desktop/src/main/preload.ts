// No privileged APIs are exposed to the renderer — the Angular app talks to the
// local Express server over plain HTTP (same origin), exactly as it talks to
// Django today. This file exists only so Electron's contextIsolation has a
// preload script to load.
