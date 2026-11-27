"""Redaction sidecar for pikvm-privacy.

Runs the cleanroom-ai screenshot redactor in a long-lived process so its models
(RapidOCR, GLiNER, YuNet) stay in memory between screenshots. The MCP server
starts this process to load the models and kills it to release them.

Protocol: one JSON object per line on stdin, one JSON response per line on
stdout. stdout is reserved for responses; all logging goes to stderr.

Requests:
  {"id": 1, "op": "warmup", "use_ner": true, "categories": [...]}
  {"id": 2, "op": "redact", "image_b64": "...", "categories": [...],
   "style": "black box", "use_ner": true, "custom_terms": []}
  {"id": 3, "op": "redact_text", "text": "...", "categories": [...],
   "use_ner": true, "custom_terms": []}

Responses never contain any detected values - only redacted output and
per-category counts.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

REDACTOR_DIR = Path(__file__).resolve().parent.parent / "vendor" / "screenshot-redactor" / "python"
sys.path.insert(0, str(REDACTOR_DIR))

logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="[redactor] %(levelname)s %(message)s")

import numpy as np  # noqa: E402
import regex  # noqa: E402
from PIL import Image  # noqa: E402

from redactor import DEFAULT_CATEGORIES  # noqa: E402
from redactor import ner, ocr, pipeline, rules, visual  # noqa: E402
from redactor.layout import OCRLine  # noqa: E402
from redactor.pipeline import NER_CATEGORIES, TEXT_CATEGORIES, redact, scan, to_rgb_array  # noqa: E402
from redactor.types import TextSpan  # noqa: E402
from redactor.redact import STYLES  # noqa: E402

MAX_SIDE = 4096
JPEG_QUALITY = 85


# --- Overrides of vendored behaviour -------------------------------------------------------
# vendor/screenshot-redactor is not edited; these replace two module-level functions that
# pipeline.scan() looks up at call time, so both the image and text paths pick them up.

def _union_line_spans(rule_spans: list[TextSpan], ner_spans: list[TextSpan]) -> list[TextSpan]:
    """Keep NER spans that overlap a rule span instead of dropping them.

    Upstream discards any NER span touching a rule span. In
    `.../slayers/Summers, Buffy/1999/Performance Review.xlsx` the random-token rule matches
    `Buffy/1999/Performance`, so the NER hit `Summers, Buffy` was dropped and `Summers,` stayed
    visible. Redacting is a union of regions, so overlap is harmless; only spans already fully
    covered are skipped (to avoid double counting).
    """
    kept = list(rule_spans)
    for s in ner_spans:
        if not any(k.start <= s.start and s.end <= k.end for k in kept):
            kept.append(s)
    return sorted(kept, key=lambda s: (s.start, s.end))


_NAME_CHARS = r"[\p{L}\p{M}'’\-]"
# The first name may start lowercase: OCR misreads case (e.g. "willow"), and NER then trims a
# lowercase word off the edge of a name, leaving it visible.
_SURNAME_FIRST = rf"\p{{Lu}}{_NAME_CHARS}+\s*,\s*\p{{L}}{_NAME_CHARS}+(?:\s+\p{{Lu}}{_NAME_CHARS}*\.?)?"
_SEP = r"[/\\>›»|]"
#: A whole path / breadcrumb segment of the form "Surname, Firstname [Middle]". Needs a separator
#: on at least one side so ordinary "Edit, View" text isn't matched.
PATH_SURNAME_FIRST = regex.compile(
    rf"(?:(?<={_SEP})\s*({_SURNAME_FIRST})(?=\s*(?:{_SEP}|$))"
    rf"|^\s*({_SURNAME_FIRST})(?=\s*{_SEP}))"
)


def path_person_spans(text: str) -> list[TextSpan]:
    """Deterministic backstop for folder names like `/Summers, Buffy/` (NER confidence varies)."""
    out = []
    for m in PATH_SURNAME_FIRST.finditer(text):
        g = 1 if m.group(1) else 2
        out.append(TextSpan(m.start(g), m.end(g), "PERSON", "person", 0.9, "rule"))
    return out


_vendor_find_spans = rules.find_spans


def _find_spans(text: str, categories=None, custom_terms=()) -> list[TextSpan]:
    spans = _vendor_find_spans(text, categories, custom_terms)
    if categories is None or "person" in categories:
        # Added after upstream overlap resolution so a token rule can't swallow the name.
        spans = _union_line_spans(spans, path_person_spans(text))
    return spans


pipeline._merge_line_spans = _union_line_spans
rules.find_spans = _find_spans
_merge_line_spans = _union_line_spans


def _categories(req: dict) -> list[str]:
    cats = req.get("categories") or DEFAULT_CATEGORIES
    return [c for c in cats if c in DEFAULT_CATEGORIES]


def warmup(req: dict) -> dict:
    """Load every model up front and fail if one the config relies on is unavailable."""
    t = time.perf_counter()
    cats = set(_categories(req))
    use_ner = bool(req.get("use_ner", True))

    ocr._get_engine()
    ner_loaded = False
    if use_ner and cats & NER_CATEGORIES:
        ner_loaded = ner.available()
        if not ner_loaded:
            raise RuntimeError(
                f"GLiNER model '{ner.MODEL_ID}' could not be loaded; refusing to run with "
                "rules-only name/address detection. Set PIKVM_REDACTOR_USE_NER=false to allow it."
            )
    if "faces" in cats and visual._yunet_model() is None:
        raise RuntimeError(f"YuNet face model missing at {visual.YUNET_PATH}")

    # Exercise the whole pipeline once so any lazy imports happen now.
    scan(np.full((64, 64, 3), 255, dtype=np.uint8), cats, use_ner=use_ner)

    return {"load_ms": round((time.perf_counter() - t) * 1000), "ner_loaded": ner_loaded,
            "categories": sorted(cats)}


def redact_image(req: dict) -> dict:
    style = req.get("style") or "black box"
    if style not in STYLES:
        raise ValueError(f"style must be one of {STYLES}")
    cats = _categories(req)
    terms = [t for t in req.get("custom_terms") or [] if isinstance(t, str) and t.strip()]

    t = time.perf_counter()
    img = Image.open(io.BytesIO(base64.b64decode(req["image_b64"])))
    arr = to_rgb_array(img)
    h, w = arr.shape[:2]
    if max(h, w) > MAX_SIDE:
        s = MAX_SIDE / max(h, w)
        arr = np.asarray(Image.fromarray(arr).resize((int(w * s), int(h * s)), Image.LANCZOS))

    result = scan(arr, cats, terms, use_ner=bool(req.get("use_ner", True)))
    out = redact(arr, result.detections, style=style)

    # Re-encoding from raw pixels drops any metadata from the source image.
    buf = io.BytesIO()
    Image.fromarray(out).save(buf, format="JPEG", quality=JPEG_QUALITY)
    return {
        "image_b64": base64.b64encode(buf.getvalue()).decode("ascii"),
        "width": out.shape[1],
        "height": out.shape[0],
        "counts": result.summary(),
        "redact_ms": round((time.perf_counter() - t) * 1000),
    }


# NER only reads OCRLine.text, so plain-text lines get a placeholder box.
_NO_POLYGON = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


def _label_value_spans(lines: list[str], spans: dict[int, list[TextSpan]]) -> None:
    """Plain-text version of the image pipeline's labelled_values(): a line that is only a
    secret label ("Password:") has its value on the next non-empty line."""
    for i, line in enumerate(lines):
        if not rules.SECRET_LABEL_ONLY.search(line):
            continue
        nxt = next((j for j in range(i + 1, len(lines)) if lines[j].strip()), None)
        if nxt is None or spans.get(nxt):
            continue
        value = lines[nxt]
        start = len(value) - len(value.lstrip())
        end = len(value.rstrip())
        if end - start >= 3:
            spans[nxt] = [TextSpan(start, end, "PASSWORD_OR_SECRET", "secrets", 0.9, "rule")]


def _replace_spans(line: str, spans: list[TextSpan]) -> str:
    """Replace spans with `[REDACTED <category>]`; overlapping spans become one placeholder."""
    groups: list[list] = []  # [start, end, categories]
    for s in sorted(spans, key=lambda s: s.start):
        if groups and s.start < groups[-1][1]:
            groups[-1][1] = max(groups[-1][1], s.end)
            if s.category not in groups[-1][2]:
                groups[-1][2].append(s.category)
        else:
            groups.append([s.start, s.end, [s.category]])
    for start, end, cats in reversed(groups):
        line = f"{line[:start]}[REDACTED {'/'.join(cats)}]{line[end:]}"
    return line


def redact_text(req: dict) -> dict:
    cats = set(_categories(req)) & TEXT_CATEGORIES
    terms = [t for t in req.get("custom_terms") or [] if isinstance(t, str) and t.strip()]
    if terms:
        cats.add("custom")

    t = time.perf_counter()
    lines = str(req.get("text") or "").replace("\r\n", "\n").split("\n")
    filled = [i for i, line in enumerate(lines) if line.strip()]

    ner_spans: dict[int, list[TextSpan]] = {}
    if bool(req.get("use_ner", True)) and cats & NER_CATEGORIES:
        found = ner.find_entities([OCRLine(lines[i], _NO_POLYGON) for i in filled], cats & NER_CATEGORIES)
        ner_spans = {filled[k]: v for k, v in found.items()}

    spans = {i: _merge_line_spans(rules.find_spans(lines[i], cats, terms), ner_spans.get(i, []))
             for i in filled}
    if "secrets" in cats:
        _label_value_spans(lines, spans)

    counts: dict[str, int] = {}
    for i, line_spans in spans.items():
        for s in line_spans:
            counts[s.category] = counts.get(s.category, 0) + 1
        lines[i] = _replace_spans(lines[i], line_spans)

    return {
        "text": "\n".join(lines),
        "counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "redact_ms": round((time.perf_counter() - t) * 1000),
    }


OPS = {"warmup": warmup, "redact": redact_image, "redact_text": redact_text}


def main() -> None:
    # The server writes UTF-8; Windows would otherwise decode stdin as the ANSI code page
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req_id = None
        try:
            req = json.loads(line)
            req_id = req.get("id")
            op = OPS.get(req.get("op"))
            if op is None:
                raise ValueError(f"unknown op: {req.get('op')!r}")
            resp = {"id": req_id, "ok": True, **op(req)}
        except Exception as exc:  # report every failure to the caller rather than dying
            logging.exception("request failed")
            resp = {"id": req_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
