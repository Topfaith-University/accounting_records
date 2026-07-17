import fs from 'fs';
import http, { Server } from 'http';
import os from 'os';
import path from 'path';
import { app, BrowserWindow, dialog } from 'electron';
import { resolveDataDir, resolveDbPath } from './dataPath';
import { initDb } from '../server/db/connection';
import { seedGroups } from '../server/bootstrap';
import { configureJwtSecret } from '../server/lib/jwt';
import { getOrCreateJwtSecret } from '../server/lib/secret';
import { createApp } from '../server/app';

// Overridable only for local testing (e.g. avoiding a clash with a Django dev
// server also using 8002 on the same machine) — production installs always
// default to 8002, matching api-base.ts's hardcoded port.
const PORT = Number(process.env.PAGE_DESKTOP_PORT) || 8002;

// This is a fully local, single-origin app — there's no real network to cache
// against, and a disk-cached error response from a stale/misconfigured prior
// run on the same port would otherwise silently keep being served forever.
app.commandLine.appendSwitch('disable-http-cache');
let httpServers: Server[] = [];
let mainWindow: BrowserWindow | null = null;

function listenOn(requestListener: http.RequestListener, host: string): Promise<Server | null> {
  return new Promise((resolve, reject) => {
    const server = http.createServer(requestListener);
    server.once('listening', () => resolve(server));
    server.once('error', (err: NodeJS.ErrnoException) => {
      // EADDRNOTAVAIL here just means this machine has no IPv6 loopback
      // configured — the IPv4 bind below is what actually matters.
      if (err.code === 'EADDRNOTAVAIL') resolve(null);
      else reject(err);
    });
    server.listen(PORT, host);
  });
}

async function startServer(): Promise<{ portable: boolean }> {
  const { dir: dataDir } = resolveDataDir();
  const { dbPath, portable } = resolveDbPath();

  const db = initDb(dbPath);
  await seedGroups(db);
  configureJwtSecret(getOrCreateJwtSecret(dataDir));

  // app.getAppPath() resolves correctly whether running unpacked (dev) or
  // packaged inside app.asar — Electron's patched fs/require read through
  // the asar archive transparently, so no isPackaged branching is needed.
  const staticDir = path.join(app.getAppPath(), 'frontend-dist');

  const expressApp = createApp(db, staticDir);

  // Bind both IPv4 and IPv6 loopback explicitly. A single bind to '127.0.0.1'
  // isn't enough: Chromium resolves `localhost` to `::1` (IPv6) first on most
  // systems, so BrowserWindow.loadURL('http://localhost:PORT/') would connect
  // over IPv6 while this server only listens on IPv4 — the connection then
  // silently falls through to whatever else happens to be bound to the IPv6
  // wildcard on that port (observed: a Docker Desktop proxy for an unrelated
  // container), serving a network response the user never launched.
  try {
    const v4 = await listenOn(expressApp, '127.0.0.1');
    if (v4) httpServers.push(v4);
  } catch (err) {
    const errno = err as NodeJS.ErrnoException;
    if (errno.code === 'EADDRINUSE') {
      throw new Error(`Port ${PORT} is already in use by another application. Close it and relaunch Page Desktop.`);
    }
    throw err;
  }
  try {
    const v6 = await listenOn(expressApp, '::1');
    if (v6) httpServers.push(v6);
  } catch (err) {
    const errno = err as NodeJS.ErrnoException;
    if (errno.code !== 'EADDRINUSE') throw err;
    // IPv4 bind above already succeeded; a taken IPv6 loopback port just means
    // something else's IPv6 listener will keep shadowing `localhost` there —
    // not fatal, but surfaced so it's not a silent trap during development.
    // eslint-disable-next-line no-console
    console.warn(`[Page Desktop] Port ${PORT} on ::1 is already in use by another application — only IPv4 localhost will reach this app.`);
  }

  return { portable };
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    title: 'Page Desktop',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
  });
  mainWindow.loadURL(`http://localhost:${PORT}/`);
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

/** Startup failures happen before any window exists to show them in, and this
 * process's stdio isn't always attached to a visible console (double-clicked
 * .app launches never have one) — write fatal errors to a fixed crash-log
 * file and show a dialog so a launch failure is never silent. */
function logFatal(error: unknown) {
  const logPath = path.join(os.tmpdir(), 'page-desktop-crash.log');
  const message = error instanceof Error ? `${error.message}\n${error.stack}` : String(error);
  try {
    fs.appendFileSync(logPath, `[${new Date().toISOString()}] ${message}\n\n`);
  } catch {
    // best effort only
  }
  dialog.showErrorBox('Page Desktop failed to start', `${message}\n\nDetails written to: ${logPath}`);
}

app.whenReady().then(async () => {
  try {
    const { portable } = await startServer();
    // eslint-disable-next-line no-console
    console.log(`[Page Desktop] data storage: ${portable ? 'portable (next to app)' : 'per-user OS folder (fallback)'}`);
    createWindow();
  } catch (error) {
    logFatal(error);
    app.quit();
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

process.on('uncaughtException', (error) => {
  logFatal(error);
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  httpServers.forEach((s) => s.close());
});
