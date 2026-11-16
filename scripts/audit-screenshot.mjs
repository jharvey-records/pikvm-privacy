#!/usr/bin/env node
/**
 * Launcher for scripts/audit_screenshot.py using the .venv-redactor Python
 * (or PIKVM_REDACTOR_PYTHON). Arguments are passed through:
 *
 *   npm run audit:screenshot -- --style pixelate --no-open
 */

import { spawnSync } from 'child_process';
import { existsSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const python = process.env.PIKVM_REDACTOR_PYTHON || (process.platform === 'win32'
  ? resolve(ROOT, '.venv-redactor', 'Scripts', 'python.exe')
  : resolve(ROOT, '.venv-redactor', 'bin', 'python'));

if (!existsSync(python)) {
  console.error(`Redactor Python not found at ${python}. Run "npm run setup:redactor" or set PIKVM_REDACTOR_PYTHON.`);
  process.exit(2);
}

const result = spawnSync(python, [resolve(ROOT, 'scripts', 'audit_screenshot.py'), ...process.argv.slice(2)], {
  cwd: ROOT,
  stdio: 'inherit',
});
process.exit(result.status ?? 1);
