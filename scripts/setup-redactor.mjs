#!/usr/bin/env node
/**
 * Set up the Python environment for screenshot redaction.
 *
 *   1. Fetches the vendor/screenshot-redactor submodule
 *   2. Creates .venv-redactor with a Python >= 3.11 interpreter
 *   3. Installs python/requirements.txt into it
 *   4. Pre-downloads the GLiNER model weights so the first pikvm_load_model is fast
 *
 * Set PIKVM_REDACTOR_BASE_PYTHON to choose the interpreter used to create the venv.
 */

import { spawnSync } from 'child_process';
import { existsSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const VENV = resolve(ROOT, '.venv-redactor');
const VENV_PYTHON = process.platform === 'win32'
  ? resolve(VENV, 'Scripts', 'python.exe')
  : resolve(VENV, 'bin', 'python');
const MIN_PYTHON = [3, 11];

function run(cmd, args, opts = {}) {
  console.log(`> ${cmd} ${args.join(' ')}`);
  const result = spawnSync(cmd, args, { cwd: ROOT, stdio: 'inherit', ...opts });
  if (result.status !== 0) {
    console.error(`Command failed: ${cmd} ${args.join(' ')}`);
    process.exit(result.status ?? 1);
  }
}

function pythonVersion(cmd, args) {
  const result = spawnSync(cmd, [...args, '-c', 'import sys; print(sys.version_info[0], sys.version_info[1])'], {
    encoding: 'utf8',
  });
  if (result.status !== 0 || !result.stdout) return null;
  return result.stdout.trim().split(' ').map(Number);
}

function isSupported(version) {
  return version && (version[0] > MIN_PYTHON[0] || (version[0] === MIN_PYTHON[0] && version[1] >= MIN_PYTHON[1]));
}

function findBasePython() {
  const candidates = [];
  if (process.env.PIKVM_REDACTOR_BASE_PYTHON) {
    candidates.push([process.env.PIKVM_REDACTOR_BASE_PYTHON, []]);
  }
  if (process.platform === 'win32') {
    for (const v of ['3.12', '3.13', '3.11', '3']) candidates.push(['py', [`-${v}`]]);
  }
  candidates.push(['python3', []], ['python', []]);

  for (const [cmd, args] of candidates) {
    const version = pythonVersion(cmd, args);
    if (isSupported(version)) return [cmd, args, version];
  }
  console.error(`No Python >= ${MIN_PYTHON.join('.')} found. Install one or set PIKVM_REDACTOR_BASE_PYTHON.`);
  process.exit(1);
}

// 1. Submodule
if (!existsSync(resolve(ROOT, 'vendor', 'screenshot-redactor', 'python', 'redactor'))) {
  run('git', ['submodule', 'update', '--init', '--recursive']);
}

// 2. Virtual environment
if (existsSync(VENV_PYTHON) && isSupported(pythonVersion(VENV_PYTHON, []))) {
  console.log(`Using existing virtual environment at ${VENV}`);
} else {
  const [cmd, args, version] = findBasePython();
  console.log(`Creating virtual environment with Python ${version.join('.')}`);
  run(cmd, [...args, '-m', 'venv', '--clear', VENV]);
}

// 3. Dependencies
run(VENV_PYTHON, ['-m', 'pip', 'install', '--upgrade', 'pip']);
run(VENV_PYTHON, ['-m', 'pip', 'install', '-r', resolve(ROOT, 'python', 'requirements.txt')]);

// 4. Model weights
run(VENV_PYTHON, [
  '-c',
  'import os, sys; sys.path.insert(0, os.path.join("vendor", "screenshot-redactor", "python")); ' +
    'from redactor import ner, ocr; ocr._get_engine(); ' +
    'sys.exit(0 if ner.available() else "GLiNER model failed to load")',
]);

console.log('\nRedactor ready. Use pikvm_load_model to load it at runtime.');
