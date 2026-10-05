/**
 * Redaction sidecar manager
 *
 * Runs python/redact_server.py (a wrapper around cleanroom-ai/screenshot-redactor)
 * as a long-lived child process. Starting the process loads the OCR, NER and face
 * models into memory; killing it is the only reliable way to release them, as the
 * redactor has no unload API.
 */

import { spawn, ChildProcess } from 'child_process';
import { createInterface } from 'readline';
import { existsSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SCRIPT_PATH = resolve(PACKAGE_ROOT, 'python', 'redact_server.py');

export const REDACTION_STYLES = ['black box', 'pixelate', 'blur'] as const;
export type RedactionStyle = (typeof REDACTION_STYLES)[number];

export interface RedactorConfig {
  pythonPath?: string;
  categories?: string[];
  style: RedactionStyle;
  useNer: boolean;
  loadTimeoutMs: number;
  redactTimeoutMs: number;
}

export interface LoadResult {
  alreadyLoaded: boolean;
  loadMs: number;
  nerLoaded: boolean;
  categories: string[];
}

export interface RedactResult {
  buffer: Buffer;
  width: number;
  height: number;
  counts: Record<string, number>;
  redactMs: number;
}

export interface RedactTextResult {
  text: string;
  counts: Record<string, number>;
  redactMs: number;
}

interface Pending {
  resolve: (value: Record<string, unknown>) => void;
  reject: (error: Error) => void;
  timer: NodeJS.Timeout;
}

function defaultPythonPath(): string {
  return process.platform === 'win32'
    ? resolve(PACKAGE_ROOT, '.venv-redactor', 'Scripts', 'python.exe')
    : resolve(PACKAGE_ROOT, '.venv-redactor', 'bin', 'python');
}

export class RedactorSidecar {
  private child: ChildProcess | null = null;
  private loaded = false;
  private loading: Promise<LoadResult> | null = null;
  private lastLoad: LoadResult | null = null;
  private pending = new Map<number, Pending>();
  private nextId = 1;

  constructor(private readonly config: RedactorConfig) {}

  isLoaded(): boolean {
    return this.loaded;
  }

  /**
   * Start the sidecar and load all models. Idempotent; concurrent callers share one load.
   */
  async load(): Promise<LoadResult> {
    if (this.loaded && this.lastLoad) {
      return { ...this.lastLoad, alreadyLoaded: true };
    }
    if (!this.loading) {
      this.loading = this.start().finally(() => {
        this.loading = null;
      });
    }
    return this.loading;
  }

  /**
   * Stop the sidecar, releasing model memory. Returns false if nothing was running.
   */
  async release(): Promise<boolean> {
    const child = this.child;
    if (!child) return false;
    this.markStopped(new Error('Redaction model was released'));

    await new Promise<void>((done) => {
      const killTimer = setTimeout(() => {
        child.kill('SIGKILL');
        done();
      }, 3000);
      child.once('exit', () => {
        clearTimeout(killTimer);
        done();
      });
      // Closing stdin makes the sidecar's read loop end and the process exit cleanly
      child.stdin?.end();
    });
    return true;
  }

  /**
   * Synchronous best-effort kill, for process exit handlers.
   */
  killSync(): void {
    this.child?.kill('SIGKILL');
  }

  async redact(image: Buffer, style?: RedactionStyle): Promise<RedactResult> {
    if (!this.loaded) {
      throw new Error('Redaction model is not loaded');
    }
    const resp = await this.send(
      {
        op: 'redact',
        image_b64: image.toString('base64'),
        categories: this.config.categories,
        style: style ?? this.config.style,
        use_ner: this.config.useNer,
      },
      this.config.redactTimeoutMs,
    );
    if (typeof resp.image_b64 !== 'string' || !resp.image_b64) {
      throw new Error('Redactor returned no image');
    }
    return {
      buffer: Buffer.from(resp.image_b64, 'base64'),
      width: Number(resp.width),
      height: Number(resp.height),
      counts: (resp.counts as Record<string, number>) ?? {},
      redactMs: Number(resp.redact_ms),
    };
  }

  async redactText(text: string): Promise<RedactTextResult> {
    if (!this.loaded) {
      throw new Error('Redaction model is not loaded');
    }
    const resp = await this.send(
      {
        op: 'redact_text',
        text,
        categories: this.config.categories,
        use_ner: this.config.useNer,
      },
      this.config.redactTimeoutMs,
    );
    if (typeof resp.text !== 'string') {
      throw new Error('Redactor returned no text');
    }
    return {
      text: resp.text,
      counts: (resp.counts as Record<string, number>) ?? {},
      redactMs: Number(resp.redact_ms),
    };
  }

  private async start(): Promise<LoadResult> {
    const pythonPath = this.config.pythonPath || defaultPythonPath();
    if (!existsSync(pythonPath)) {
      throw new Error(
        `Redactor Python not found at ${pythonPath}. Run "npm run setup:redactor" or set PIKVM_REDACTOR_PYTHON.`,
      );
    }

    const child = spawn(pythonPath, [SCRIPT_PATH], {
      cwd: PACKAGE_ROOT,
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    });
    this.child = child;

    // stdout of this process is the MCP channel, so sidecar logs go to stderr only
    createInterface({ input: child.stderr! }).on('line', (line) => console.error(line));
    createInterface({ input: child.stdout! }).on('line', (line) => this.onLine(line));

    child.on('error', (err) => {
      if (this.child === child) this.markStopped(new Error(`Redactor process error: ${err.message}`));
    });
    child.on('exit', (code, signal) => {
      if (this.child === child) {
        this.markStopped(new Error(`Redactor process exited unexpectedly (code ${code}, signal ${signal})`));
      }
    });

    try {
      const resp = await this.send(
        { op: 'warmup', categories: this.config.categories, use_ner: this.config.useNer },
        this.config.loadTimeoutMs,
      );
      this.loaded = true;
      this.lastLoad = {
        alreadyLoaded: false,
        loadMs: Number(resp.load_ms),
        nerLoaded: Boolean(resp.ner_loaded),
        categories: (resp.categories as string[]) ?? [],
      };
      return this.lastLoad;
    } catch (error) {
      await this.release();
      throw error;
    }
  }

  private send(request: Record<string, unknown>, timeoutMs: number): Promise<Record<string, unknown>> {
    const child = this.child;
    if (!child?.stdin?.writable) {
      return Promise.reject(new Error('Redactor process is not running'));
    }
    const id = this.nextId++;
    return new Promise((resolvePromise, rejectPromise) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        rejectPromise(new Error(`Redactor timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      this.pending.set(id, { resolve: resolvePromise, reject: rejectPromise, timer });
      child.stdin!.write(JSON.stringify({ id, ...request }) + '\n');
    });
  }

  private onLine(line: string): void {
    let resp: Record<string, unknown>;
    try {
      resp = JSON.parse(line);
    } catch {
      console.error('[redactor] ignoring non-JSON output');
      return;
    }
    const entry = this.pending.get(resp.id as number);
    if (!entry) return;
    this.pending.delete(resp.id as number);
    clearTimeout(entry.timer);
    if (resp.ok === true) {
      entry.resolve(resp);
    } else {
      entry.reject(new Error(`Redaction failed: ${String(resp.error ?? 'unknown error')}`));
    }
  }

  private markStopped(reason: Error): void {
    this.child = null;
    this.loaded = false;
    this.lastLoad = null;
    for (const entry of this.pending.values()) {
      clearTimeout(entry.timer);
      entry.reject(reason);
    }
    this.pending.clear();
  }
}
