# AGENTS.md - pikvm-privacy MCP Server

## Project Overview

This project implements an MCP (Model Context Protocol) server that provides direct API access to PiKVM devices. This allows Claude Code and other MCP clients to control remote machines via PiKVM without going through browser automation.

pikvm-privacy is a privacy-oriented fork of [PiKVM MCP Server](https://github.com/KultivatorConsulting/pikvm_mcp_server). Every screenshot returned to the client is first redacted by [cleanroom-ai/screenshot-redactor](https://github.com/cleanroom-ai/screenshot-redactor) (Apache-2.0, vendored as a git submodule), which runs locally in a Python sidecar process. There is no tool that returns an unredacted screenshot.

## Why This Exists

Browser automation through PiKVM's web interface has keyboard input issues - special characters get mangled because the automation layer sends characters rather than proper key events. This MCP server communicates directly with PiKVM's REST API, which handles character-to-keycode conversion properly.

Screenshots of a remote machine routinely contain secrets and personal data. This fork ensures that content is redacted on the MCP server host before it reaches the AI model.

## Project Structure

```
pikvm-privacy/
├── AGENTS.md           # This file - instructions for AI agents
├── CONTEXT.md          # Background research and design notes
├── API_REFERENCE.md    # PiKVM API documentation
├── src/                # Source code
│   ├── index.ts        # Main MCP server entry point (tool + prompt handlers)
│   ├── config.ts       # Configuration handling
│   ├── pikvm/          # PiKVM API client
│   │   ├── client.ts
│   │   ├── auto-calibrate.ts  # Vision-based auto-calibration
│   │   └── lock.ts
│   ├── redactor/
│   │   └── sidecar.ts  # Starts/stops the Python redaction sidecar, JSON-lines RPC
│   └── prompts/        # MCP prompt definitions
│       ├── types.ts    # PromptDefinition interface
│       ├── tool-guides.ts  # 10 individual tool guide prompts
│       ├── workflows.ts    # 6 multi-step workflow prompts
│       ├── skill-tools.ts  # Auto-generated skill_* tools from prompts
│       └── index.ts    # Barrel export + lookup function
├── python/
│   ├── redact_server.py    # Redaction sidecar (wraps vendor/screenshot-redactor)
│   └── requirements.txt    # Python dependencies for the sidecar
├── scripts/
│   └── setup-redactor.mjs  # `npm run setup:redactor` - submodule, venv, deps, model weights
├── vendor/
│   └── screenshot-redactor/  # Git submodule: cleanroom-ai/screenshot-redactor (do not edit)
├── docs/skills/        # Human-readable skill guides (mirrors prompts)
├── package.json
└── tsconfig.json
```

## Development Commands

```bash
# Install dependencies (clone with --recursive, or setup:redactor will init the submodule)
npm install

# Set up the Python redaction environment (.venv-redactor, requires Python 3.11+)
npm run setup:redactor

# Build
npm run build

# Run in development
npm run dev

# Type checking
npm run typecheck
```

## Configuration

The server is configured via environment variables or a `.env` file:

- `PIKVM_HOST` - PiKVM URL (e.g., `https://<your-pikvm-ip>`)
- `PIKVM_USERNAME` - Auth username (default: `admin`)
- `PIKVM_PASSWORD` - Auth password
- `PIKVM_VERIFY_SSL` - Whether to verify SSL certs (default: `false` for self-signed)
- `PIKVM_DEFAULT_KEYMAP` - Default keyboard layout (default: `en-us`)
- `PIKVM_CALIBRATION_ROUNDS` / `PIKVM_CALIBRATION_VERIFY_ROUNDS` / `PIKVM_CALIBRATION_MOVE_DELAY` - Auto-calibration defaults (5 / 5 / 300ms)
- `PIKVM_REDACTOR_PYTHON` - Python interpreter for the sidecar (default: `.venv-redactor` Python in the package root)
- `PIKVM_REDACTOR_CATEGORIES` - Comma-separated categories to redact (default: all of `secrets`, `contact`, `financial`, `government_id`, `network`, `person`, `location`, `dates`, `faces`, `codes`)
- `PIKVM_REDACTOR_STYLE` - Default redaction style: `black box` (default), `pixelate` or `blur`
- `PIKVM_REDACTOR_USE_NER` - Use GLiNER for names/addresses (default: `true`; when `true`, model load fails if GLiNER can't load)
- `PIKVM_REDACTOR_LOAD_TIMEOUT_MS` - Model load timeout (default: `180000`)
- `PIKVM_REDACTOR_TIMEOUT_MS` - Per-screenshot redaction timeout (default: `60000`)
- `REDACTOR_NER_MODEL` - Read by the upstream redactor to override the GLiNER model (default: `urchade/gliner_multi_pii-v1`)

## MCP Tools Provided

### Display
1. **`pikvm_redacted_screenshot`** - Capture current screen as JPEG with sensitive content redacted (optional: maxWidth, maxHeight, quality, style)
2. **`pikvm_get_resolution`** - Get current screen resolution (useful for mouse coordinates)

### Redaction Model
3. **`pikvm_load_model`** - Start the sidecar and load RapidOCR, GLiNER and YuNet models
4. **`pikvm_release_model`** - Kill the sidecar, freeing its memory

### Keyboard
5. **`pikvm_type`** - Type text (handles special chars correctly via keymap)
6. **`pikvm_key`** - Send key/combo (e.g., Ctrl+Alt+Del)
7. **`pikvm_shortcut`** - Send keyboard shortcut (multiple keys pressed simultaneously)

### Mouse
8. **`pikvm_mouse_move`** - Move mouse cursor (absolute or relative)
9. **`pikvm_mouse_click`** - Click mouse button
10. **`pikvm_mouse_scroll`** - Scroll wheel

### Calibration
11. **`pikvm_calibrate`** - Start mouse coordinate calibration (moves cursor to screen center)
12. **`pikvm_set_calibration`** - Set calibration correction factors after visual verification
13. **`pikvm_get_calibration`** - Get current calibration state
14. **`pikvm_clear_calibration`** - Clear calibration, revert to uncalibrated mode
15. **`pikvm_auto_calibrate`** - Automatically detect the cursor via screenshot diffing and compute calibration factors

## MCP Prompts & Skill Tools

The server exposes 16 skills as both MCP prompts (`prompts/list` / `prompts/get`) and read-only `skill_*` tools (`tools/list` / `tools/call`). The skill tools are auto-generated from prompt definitions for marketplace visibility (e.g. LobeHub indexes tools, not prompts).

**Total tools: 31** (15 `pikvm_*` hardware/redaction tools + 16 `skill_*` guidance tools)

### Tool Guides
| Prompt | Skill Tool | Covers |
|---|---|---|
| `take-redacted-screenshot` | `skill_take_redacted_screenshot` | pikvm_redacted_screenshot |
| `manage-redaction-model` | `skill_manage_redaction_model` | pikvm_load_model, pikvm_release_model |
| `check-resolution` | `skill_check_resolution` | pikvm_get_resolution |
| `type-text` | `skill_type_text` | pikvm_type |
| `send-key` | `skill_send_key` | pikvm_key |
| `send-shortcut` | `skill_send_shortcut` | pikvm_shortcut |
| `move-mouse` | `skill_move_mouse` | pikvm_mouse_move |
| `click-element` | `skill_click_element` | pikvm_mouse_click |
| `auto-calibrate` | `skill_auto_calibrate` | pikvm_auto_calibrate |
| `scroll-page` | `skill_scroll_page` | pikvm_mouse_scroll |

### Workflow Recipes
| Prompt | Skill Tool | Arguments | Description |
|---|---|---|---|
| `setup-session-workflow` | `skill_setup_session_workflow` | — | Initialize session: resolution, load redaction model, screenshot, calibrate; release model at end |
| `calibrate-mouse-workflow` | `skill_calibrate_mouse_workflow` | — | Full mouse calibration procedure |
| `auto-calibrate-mouse-workflow` | `skill_auto_calibrate_mouse_workflow` | — | Automatic mouse calibration procedure |
| `click-ui-element-workflow` | `skill_click_ui_element_workflow` | element_description (required) | Find and click a UI element |
| `fill-form-workflow` | `skill_fill_form_workflow` | form_description (optional) | Fill in form fields |
| `navigate-desktop-workflow` | `skill_navigate_desktop_workflow` | goal (required) | Navigate desktop with Observe-Plan-Act-Verify loop |

Implementation: `src/prompts/` (types.ts, tool-guides.ts, workflows.ts, skill-tools.ts, index.ts). Human-readable guides: `docs/skills/` — keep these in sync with the prompt text.

## Key Implementation Notes

- PiKVM often uses self-signed SSL certificates - disable verification or add CA
- The `/api/hid/print` endpoint is the best way to type text - it handles keymap conversion
- Mouse coordinates are absolute (0-based, screen resolution dependent)
- Some operations may need delays between them for the target system to process
- **Calibration**: Mouse coordinates often need calibration at different resolutions. Prefer `pikvm_auto_calibrate`. The manual workflow is: call `pikvm_calibrate` to move cursor to center, take a redacted screenshot to verify actual position, then call `pikvm_set_calibration` with correction factors. Calibration is automatically invalidated when resolution changes.
- **Redaction sidecar**: `src/redactor/sidecar.ts` spawns `python/redact_server.py` as a long-lived child process and talks to it over JSON lines on stdin/stdout (stdout is reserved for responses; Python logging goes to stderr). `pikvm_load_model` starts it and runs a warmup that loads RapidOCR, GLiNER (`urchade/gliner_multi_pii-v1`) and YuNet (~12s once weights are cached, longer on first run; around 2 GB working set). Killing the process (`pikvm_release_model`) is the only way to free the models — the redactor has no unload API.
- **Fail closed**: `pikvm_redacted_screenshot` captures at full resolution, redacts, then downscales if `maxWidth`/`maxHeight` were given. Any error (model not loaded, sidecar crash, timeout, bad response) results in a tool error, never the raw image. Warmup fails if GLiNER can't load unless `PIKVM_REDACTOR_USE_NER=false`.
- **No detected text in responses**: the sidecar returns only the redacted image and per-category counts; detected values are never sent back to the server or client.
- **Raw screenshots stay internal**: `pikvm_auto_calibrate` still diffs raw captures to locate the cursor, but those images are never returned to the client. Do not add any code path that returns an unredacted capture.
- **Python 3.11+** is required for the sidecar (onnxruntime 1.30 has no 3.10 wheels). `npm run setup:redactor` creates `.venv-redactor`, which the server uses by default.
- Redaction is best-effort OCR-based detection and can miss items (e.g. in testing a private IP `192.168.10.45` was not redacted).

## Testing

Test against a real PiKVM device:
- URL: `https://<your-pikvm-ip>`
- Access via: PiKVM web interface at `/kvm/`

## References

- See `CONTEXT.md` for background research
- See `API_REFERENCE.md` for PiKVM API details
- Upstream project: https://github.com/KultivatorConsulting/pikvm_mcp_server
- Screenshot redactor: https://github.com/cleanroom-ai/screenshot-redactor
- PiKVM GitHub: https://github.com/pikvm/kvmd
- MCP SDK: https://github.com/modelcontextprotocol
