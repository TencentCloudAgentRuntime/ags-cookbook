import { spawn } from 'node:child_process';

const children = [
  spawn(process.execPath, ['src/server.mjs'], { stdio: 'inherit', env: process.env }),
  spawn(process.execPath, ['src/mcp-server.mjs'], { stdio: 'inherit', env: process.env }),
];

let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill('SIGTERM');
  setTimeout(() => process.exit(code), 250).unref();
}

for (const child of children) {
  child.on('exit', (code, signal) => {
    if (!stopping) {
      console.error(`A demo process exited (${signal || code}); stopping the other process.`);
      stop(code ?? 1);
    }
  });
}

process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
