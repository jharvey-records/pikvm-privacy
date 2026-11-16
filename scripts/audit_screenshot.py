"""Audit redaction: capture a PiKVM screenshot, redact it, and open it locally.

Shows a human exactly what pikvm_redacted_screenshot would send to the model
(at full resolution). This is an operator tool, not an MCP tool; no model is
involved.

It calls the same functions as the MCP server's redaction sidecar
(python/redact_server.py), using the same PIKVM_* settings from .env or the
environment. The raw capture stays in memory only; just the redacted JPEG is
written to disk, and nothing is written if redaction fails.

Run with the redactor venv:
    npm run audit:screenshot -- [--style pixelate] [--out path.jpg] [--no-open]
    .venv-redactor/Scripts/python.exe scripts/audit_screenshot.py   (Windows)
    .venv-redactor/bin/python scripts/audit_screenshot.py           (macOS/Linux)
"""

from __future__ import annotations

import argparse
import base64
import os
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STYLES = ("black box", "pixelate", "blur")
SNAPSHOT_RETRY_DELAYS_S = (0.25, 0.5, 1.0, 2.0)  # matches requestSnapshot in src/pikvm/client.ts


def load_dotenv(path: Path) -> None:
    """Minimal .env loader. Like src/config.ts, .env values override the environment."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        os.environ[key] = value


def fetch_snapshot(host: str, username: str, password: str, verify_ssl: bool) -> bytes:
    url = host.rstrip("/") + "/api/streamer/snapshot"
    req = urllib.request.Request(url, headers={"X-KVMD-User": username, "X-KVMD-Passwd": password})
    ctx = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
    for attempt in range(len(SNAPSHOT_RETRY_DELAYS_S) + 1):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            # The streamer returns 503 while busy; retry with backoff like the server does.
            if err.code == 503 and attempt < len(SNAPSHOT_RETRY_DELAYS_S):
                time.sleep(SNAPSHOT_RETRY_DELAYS_S[attempt])
                continue
            hint = " (check PIKVM_USERNAME / PIKVM_PASSWORD)" if err.code in (401, 403) else ""
            raise RuntimeError(f"PiKVM snapshot failed: HTTP {err.code} {err.reason}{hint}") from None
        except urllib.error.URLError as err:
            raise RuntimeError(f"Could not reach PiKVM at {host}: {err.reason}") from None
    raise RuntimeError("PiKVM snapshot failed: streamer stayed busy")


def open_file(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - opening a local file we just wrote
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def main() -> int:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Capture, redact and open a PiKVM screenshot for auditing.")
    parser.add_argument("--style", choices=STYLES, default=os.environ.get("PIKVM_REDACTOR_STYLE") or "black box",
                        help="Redaction style (default: PIKVM_REDACTOR_STYLE or 'black box')")
    parser.add_argument("--out", type=Path,
                        help="Output JPEG path (default: timestamped file in the system temp directory)")
    parser.add_argument("--no-open", action="store_true", help="Save the image without opening it")
    args = parser.parse_args()

    host = os.environ.get("PIKVM_HOST")
    password = os.environ.get("PIKVM_PASSWORD")
    if not host or not password:
        print("PIKVM_HOST and PIKVM_PASSWORD must be set (in .env or the environment).", file=sys.stderr)
        return 2
    username = os.environ.get("PIKVM_USERNAME") or "admin"
    verify_ssl = os.environ.get("PIKVM_VERIFY_SSL") == "true"
    use_ner = os.environ.get("PIKVM_REDACTOR_USE_NER") != "false"
    categories = [c.strip() for c in (os.environ.get("PIKVM_REDACTOR_CATEGORIES") or "").split(",") if c.strip()]
    categories = categories or None  # None = all categories, as in the server

    out = args.out or Path(tempfile.gettempdir()) / f"pikvm-audit-{datetime.now():%Y%m%d-%H%M%S}.jpg"

    # Import the sidecar module itself so the audit uses the exact same redaction code.
    sys.path.insert(0, str(ROOT / "python"))
    try:
        import redact_server
    except ImportError as err:
        print(f"Could not import the redactor ({err}). Run this with the .venv-redactor Python "
              "(npm run setup:redactor creates it).", file=sys.stderr)
        return 2

    try:
        print("Loading redaction models...", file=sys.stderr)
        warm = redact_server.warmup({"categories": categories, "use_ner": use_ner})
        print(f"Models loaded in {warm['load_ms']} ms (NER: {'on' if warm['ner_loaded'] else 'off'})",
              file=sys.stderr)

        print("Capturing screenshot...", file=sys.stderr)
        raw = fetch_snapshot(host, username, password, verify_ssl)

        print("Redacting...", file=sys.stderr)
        result = redact_server.redact_image({
            "image_b64": base64.b64encode(raw).decode("ascii"),
            "categories": categories,
            "style": args.style,
            "use_ner": use_ner,
        })
        del raw
    except Exception as err:  # fail closed: nothing is written
        print(f"Audit failed, no image saved: {err}", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(result["image_b64"]))

    counts = result["counts"]
    summary = ", ".join(f"{cat}: {n}" for cat, n in counts.items()) if counts else "nothing detected"
    print(f"Redacted screenshot ({result['width']}x{result['height']}, style '{args.style}', "
          f"{result['redact_ms']} ms): {out}")
    print(f"Redactions: {summary}")

    if not args.no_open:
        open_file(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
