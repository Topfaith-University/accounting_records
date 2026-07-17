import fs from 'fs';
import path from 'path';
import { app } from 'electron';

const DATA_DIR_NAME = 'PageDesktopData';
const DB_FILE_NAME = 'page-desktop.sqlite3';

/** Folder containing the running app itself — where portable-mode data should live
 * so that copying the app's folder to another device carries the data with it.
 *
 * Windows portable builds: electron-builder sets PORTABLE_EXECUTABLE_DIR to the
 * folder holding the double-clicked .exe.
 * macOS: the executable lives at `AppName.app/Contents/MacOS/AppName`, so the
 * folder *containing* the .app bundle is three levels up from the executable.
 * Unpackaged dev runs: the project directory itself.
 */
function portableRootDir(): string {
  if (process.env.PORTABLE_EXECUTABLE_DIR) {
    return process.env.PORTABLE_EXECUTABLE_DIR;
  }
  if (!app.isPackaged) {
    return path.resolve(__dirname, '..', '..');
  }
  if (process.platform === 'darwin') {
    return path.resolve(path.dirname(app.getPath('exe')), '..', '..', '..');
  }
  return path.dirname(app.getPath('exe'));
}

function canWriteTo(dir: string): boolean {
  try {
    fs.mkdirSync(dir, { recursive: true });
    const probe = path.join(dir, '.write-test');
    fs.writeFileSync(probe, 'ok');
    fs.unlinkSync(probe);
    return true;
  } catch {
    return false;
  }
}

/** Resolves the folder the SQLite file should live in, preferring a directory
 * next to the app binary (portable data) and falling back to the OS per-user
 * data folder if that location isn't writable — e.g. a macOS app launched from
 * a Gatekeeper-translocated, read-only path before being moved out of the zip. */
export function resolveDataDir(): { dir: string; portable: boolean } {
  const candidate = path.join(portableRootDir(), DATA_DIR_NAME);
  if (canWriteTo(candidate)) {
    return { dir: candidate, portable: true };
  }
  const fallback = app.getPath('userData');
  fs.mkdirSync(fallback, { recursive: true });
  return { dir: fallback, portable: false };
}

export function resolveDbPath(): { dbPath: string; portable: boolean } {
  const { dir, portable } = resolveDataDir();
  return { dbPath: path.join(dir, DB_FILE_NAME), portable };
}
