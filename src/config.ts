/**
 * Configuration management for PiKVM MCP Server
 *
 * Reads configuration from environment variables.
 * Supports .env file via dotenv.
 */

import { config as loadEnv } from 'dotenv';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { REDACTION_STYLES, RedactionStyle, RedactorConfig } from './redactor/sidecar.js';

// Load .env file from project root
// - quiet: true prevents stdout output that would corrupt MCP protocol
// - override: true ensures .env values take precedence over any existing env vars
const __dirname = dirname(fileURLToPath(import.meta.url));
const envPath = resolve(__dirname, '..', '.env');
loadEnv({ path: envPath, quiet: true, override: true });

export interface Config {
  pikvm: {
    host: string;
    username: string;
    password: string;
    verifySsl: boolean;
    defaultKeymap: string;
  };
  calibration: {
    rounds: number;
    verifyRounds: number;
    moveDelayMs: number;
  };
  redactor: RedactorConfig;
}

export function loadConfig(): Config {
  const host = process.env.PIKVM_HOST;
  if (!host) {
    throw new Error('PIKVM_HOST environment variable is required');
  }

  const password = process.env.PIKVM_PASSWORD;
  if (!password) {
    throw new Error('PIKVM_PASSWORD environment variable is required');
  }

  return {
    pikvm: {
      host,
      username: process.env.PIKVM_USERNAME || 'admin',
      password,
      verifySsl: process.env.PIKVM_VERIFY_SSL === 'true',
      defaultKeymap: process.env.PIKVM_DEFAULT_KEYMAP || 'en-us',
    },
    calibration: {
      rounds: parseInt(process.env.PIKVM_CALIBRATION_ROUNDS || '5', 10),
      verifyRounds: parseInt(process.env.PIKVM_CALIBRATION_VERIFY_ROUNDS || '5', 10),
      moveDelayMs: parseInt(process.env.PIKVM_CALIBRATION_MOVE_DELAY || '300', 10),
    },
    redactor: loadRedactorConfig(),
  };
}

function loadRedactorConfig(): RedactorConfig {
  const style = (process.env.PIKVM_REDACTOR_STYLE || 'black box') as RedactionStyle;
  if (!REDACTION_STYLES.includes(style)) {
    throw new Error(`PIKVM_REDACTOR_STYLE must be one of: ${REDACTION_STYLES.join(', ')}`);
  }
  const categories = process.env.PIKVM_REDACTOR_CATEGORIES
    ?.split(',')
    .map((c) => c.trim())
    .filter(Boolean);

  return {
    pythonPath: process.env.PIKVM_REDACTOR_PYTHON || undefined,
    categories: categories?.length ? categories : undefined,
    style,
    useNer: process.env.PIKVM_REDACTOR_USE_NER !== 'false',
    loadTimeoutMs: parseInt(process.env.PIKVM_REDACTOR_LOAD_TIMEOUT_MS || '180000', 10),
    redactTimeoutMs: parseInt(process.env.PIKVM_REDACTOR_TIMEOUT_MS || '60000', 10),
  };
}
