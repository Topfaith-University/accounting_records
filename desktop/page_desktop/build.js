// Bundles the Electron main process + server into single CJS files via esbuild.
// Sidesteps electron-builder's node_modules pruning entirely (it was silently
// dropping real transitive dependencies like call-bind-apply-helpers even with
// explicit `files` overrides) — only better-sqlite3 (a native addon that can't
// be bundled) remains a real node_modules entry in the packaged app.
const esbuild = require('esbuild');
const fs = require('fs');
const path = require('path');

const shared = {
  bundle: true,
  platform: 'node',
  target: 'node20',
  format: 'cjs',
  external: ['electron', 'better-sqlite3'],
  logLevel: 'info',
};

function copyFile(from, to) {
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.copyFileSync(from, to);
}

/** fontkit, pdfkit, and linebreak (pdfmake's PDF engine and its text-shaping
 * dependencies) load binary/text assets via `readFileSync(__dirname + '/...')`
 * at require-time — esbuild only follows require()/import, so these never get
 * bundled and must be copied next to the output file by hand, matching the
 * `__dirname` each library expects once flattened into dist/main/. Exhaustive
 * list verified via `grep -rn "readFileSync(__dirname" node_modules/@foliojs-fork
 * node_modules/pdfmake/src` across the whole pdfmake dependency tree. */
function copyPdfAssets() {
  const fontkitDir = path.join(__dirname, 'node_modules/@foliojs-fork/fontkit');
  for (const trie of ['data.trie', 'indic.trie', 'use.trie']) {
    copyFile(path.join(fontkitDir, trie), path.join(__dirname, 'dist/main', trie));
  }
  const pdfkitDataDir = path.join(__dirname, 'node_modules/@foliojs-fork/pdfkit/js/data');
  for (const file of fs.readdirSync(pdfkitDataDir)) {
    copyFile(path.join(pdfkitDataDir, file), path.join(__dirname, 'dist/main/data', file));
  }
  copyFile(
    path.join(__dirname, 'node_modules/@foliojs-fork/linebreak/src/classes.trie'),
    path.join(__dirname, 'dist/main/classes.trie'),
  );
}

Promise.all([
  esbuild.build({ ...shared, entryPoints: ['src/main/index.ts'], outfile: 'dist/main/index.js' }),
  esbuild.build({ ...shared, entryPoints: ['src/main/preload.ts'], outfile: 'dist/main/preload.js' }),
])
  .then(copyPdfAssets)
  .catch(() => process.exit(1));
