// Builds the Angular frontend and copies its output into frontend-dist/.
// Plain Node (fs.rmSync/cpSync, cross-spawn-free child_process.spawnSync)
// instead of shell commands (`rm -rf`, `cp -R`, `cd &&`) so this script runs
// identically under Windows' cmd.exe and macOS/Linux's sh — the previous
// inline shell version only ever worked on Unix.
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const frontendDir = path.join(__dirname, '..', '..', 'frontend', 'sage-frontend');
const frontendDistOut = path.join(__dirname, 'frontend-dist');
const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';

function run(cmd, args, cwd) {
  const result = spawnSync(cmd, args, { cwd, stdio: 'inherit', shell: false });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

run(npmCmd, ['install'], frontendDir);
run(npmCmd, ['run', 'build', '--', '--configuration', 'production'], frontendDir);

fs.rmSync(frontendDistOut, { recursive: true, force: true });
fs.cpSync(path.join(frontendDir, 'dist', 'sage-frontend', 'browser'), frontendDistOut, { recursive: true });

console.log(`Frontend built and copied to ${frontendDistOut}`);
