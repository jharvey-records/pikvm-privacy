# pikvm-privacy

A privacy-oriented fork of [PiKVM MCP Server](https://github.com/KultivatorConsulting/pikvm_mcp_server) by Kultivator Consulting. Every screenshot the AI sees is first passed through [cleanroom-ai/screenshot-redactor](https://github.com/cleanroom-ai/screenshot-redactor), which blacks out secrets, personal data and faces before the image leaves the server. See [Privacy](#privacy) below.

Give AI agents hands. This MCP server connects Claude Code (or any MCP client) directly to a [PiKVM](https://pikvm.org/) device, giving AI full keyboard, mouse, and screen access to a physical machine -- no browser automation, no virtual desktops, no emulators.

Point it at real hardware. Let the AI see the screen, type commands, click buttons, and navigate GUIs on a machine it could never otherwise touch.

<p align="center">
  <img src="assets/simple_setup.jpg" alt="Raspberry Pi 5 connected to a PiKVM V4 Plus" width="600">
  <br>
  <em>A Raspberry Pi 5 controlled via PiKVM V4 Plus -- the AI's physical interface to the real world.</em>
</p>

### Automatic Mouse Calibration

IP-KVM devices translate mouse coordinates through multiple layers — USB HID emulation, host-side input drivers, display scaling — each introducing positional error. Existing KVM products either ignore this (requiring manual correction) or offer limited auto-sync that only detects cursor acceleration in a fixed corner region.

This MCP server takes a different approach. The `pikvm_auto_calibrate` tool uses a vision-based algorithm that:

1. **Moves the cursor** a known distance across multiple randomized screen positions
2. **Diffs screenshot pairs** to isolate the cursor via connected-component analysis
3. **Computes correction factors** from detected vs commanded movement using median aggregation
4. **Self-verifies** by moving to target positions and confirming the cursor lands within 20px

The entire process runs in ~30-60 seconds with no human intervention. Noisy screens (tooltips, animations, dynamic content) are handled through multi-round sampling, ratio divergence filtering, and outlier-resistant statistics — the algorithm discards bad data and still converges on accurate factors.

This is the first IP-KVM tooling — commercial or open source — to implement fully automated mouse coordinate calibration via computer vision. It is what makes precise AI-driven mouse control over a network KVM practical.

### See it in action

> The demo videos below were recorded with the upstream PiKVM MCP Server, before screenshot redaction was added.

The video below shows Claude Code using this MCP server to autonomously interact with a Raspberry Pi desktop: taking a screenshot to identify the OS, opening a text editor from the menu, typing text, and closing the application -- all through the PiKVM hardware interface.

[![Demo Video](https://img.youtube.com/vi/VYE8O1gAs7s/0.jpg)](https://youtu.be/VYE8O1gAs7s)

This next demonstration shows Claude, connected via the PiKVM MCP server, responding to a natural language prompt to auto-calibrate its mouse coordinate scaling before performing a series of precision mouse tasks on a remote machine. The session concludes with Claude autonomously drawing a house in MS Paint — a simple but effective showcase of accurate, AI-driven input control over an isolated system.

[![Demo Video](https://img.youtube.com/vi/kNj8TJD6odo/0.jpg)](https://youtu.be/kNj8TJD6odo)

## Features

- **Automatic mouse calibration** — Vision-based cursor detection computes coordinate correction factors with no manual measurement. The first fully automated calibration for IP-KVM.
- **Redacted screenshot capture** — Get current screen as JPEG image, with secrets, PII and faces blacked out before it is returned
- **Redacted screen text** — For models without vision (e.g. many self-hosted open-source models): read the screen via PiKVM's OCR, with secrets and PII replaced by placeholders before it is returned
- **Text typing** — Type text with proper special character handling via keymaps
- **Keyboard control** — Send individual keys or key combinations (e.g., Ctrl+Alt+Delete)
- **Mouse control** — Move, click, and scroll with calibrated coordinate correction

## Privacy

The original server returned raw screenshots to the MCP client, which means anything on the remote screen (passwords, API keys, customer data, faces) ends up in the AI model's context. This fork removes that path:

- **There is no unredacted screenshot tool.** `pikvm_screenshot` has been replaced by `pikvm_redacted_screenshot`.
- **Screen text is redacted too.** `pikvm_get_redacted_text` takes the text from PiKVM's OCR endpoint and runs it through the same secret/PII rules and GLiNER model in the sidecar, replacing each sensitive value with `[REDACTED <category>]`. It shares the loaded model with screenshots and fails closed in the same way.
- **Redaction runs locally.** A Python sidecar process on the MCP server host runs the [screenshot-redactor](https://github.com/cleanroom-ai/screenshot-redactor) pipeline: RapidOCR text recognition, secret/PII rules and checksums, the GLiNER PII model ([`urchade/gliner_multi_pii-v1`](https://huggingface.co/urchade/gliner_multi_pii-v1)) for names and addresses, YuNet face detection, and QR/barcode detection. Images are not sent to any third-party service for redaction.
- **Redaction happens at full resolution**, before any downscaling requested via `maxWidth`/`maxHeight`.
- **Fails closed.** If the model isn't loaded, or the sidecar crashes, times out or returns an error, the tool returns an error — never the unredacted image. `pikvm_load_model` also refuses to start if the GLiNER model can't load, rather than silently falling back to rules-only name/address detection (set `PIKVM_REDACTOR_USE_NER=false` to allow that explicitly).
- **No detected values are returned.** Tool responses report only per-category counts and the redacted output, never the redacted values.
- **Auto-calibration** still diffs raw screenshots internally to find the cursor, but those images never leave the server.

### Limits

Redaction is best-effort. Detection depends on OCR reading the text correctly and on the rules or NER model recognising it as sensitive, so things can be missed — small, low-contrast, stylised or partially obscured text is the most likely to slip through. For example, in testing a private IP address (`192.168.10.45`) was not redacted. It can also over-redact harmless text that looks like a name or token. Treat it as a strong safety net, not a guarantee, and avoid pointing the AI at screens containing material that must never be disclosed. Prefer the default `black box` style — blur and pixelation are not considered safe for text. The same applies to `pikvm_get_redacted_text`, whose input comes from PiKVM's own OCR (Tesseract) rather than RapidOCR: misread characters can stop a value from being recognised.

## Installation

Requires **Node.js 18+** and **Python 3.11+** (the redactor's `onnxruntime` dependency has no Python 3.10 wheels).

```bash
git clone --recursive https://github.com/jharvey-records/pikvm-privacy.git
cd pikvm-privacy
npm install
npm run build
npm run setup:redactor
```

`npm run setup:redactor` (see [`scripts/setup-redactor.mjs`](scripts/setup-redactor.mjs)):

1. Initialises the `vendor/screenshot-redactor` git submodule if you cloned without `--recursive`
2. Creates a `.venv-redactor` virtual environment using a Python >= 3.11 interpreter (set `PIKVM_REDACTOR_BASE_PYTHON` to choose one explicitly)
3. Installs [`python/requirements.txt`](python/requirements.txt) (RapidOCR, ONNX Runtime, OpenCV, GLiNER, CPU-only PyTorch)
4. Pre-downloads the GLiNER model weights so the first `pikvm_load_model` is fast

The server uses `.venv-redactor` automatically; set `PIKVM_REDACTOR_PYTHON` to use a different interpreter.

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env`:
```
PIKVM_HOST=https://<your-pikvm-ip>
PIKVM_USERNAME=admin
PIKVM_PASSWORD=your_password
PIKVM_VERIFY_SSL=false
PIKVM_DEFAULT_KEYMAP=en-us
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PIKVM_HOST` | *(required)* | PiKVM URL, e.g. `https://<your-pikvm-ip>` |
| `PIKVM_PASSWORD` | *(required)* | PiKVM password |
| `PIKVM_USERNAME` | `admin` | PiKVM username |
| `PIKVM_VERIFY_SSL` | `false` | Verify SSL certificates (PiKVM usually uses a self-signed cert) |
| `PIKVM_DEFAULT_KEYMAP` | `en-us` | Default keyboard layout for `pikvm_type` |
| `PIKVM_CALIBRATION_ROUNDS` | `5` | Auto-calibration sampling rounds |
| `PIKVM_CALIBRATION_VERIFY_ROUNDS` | `5` | Auto-calibration verification rounds |
| `PIKVM_CALIBRATION_MOVE_DELAY` | `300` | Delay (ms) after each mouse move during auto-calibration |
| `PIKVM_REDACTOR_PYTHON` | `.venv-redactor` Python in the package root | Python interpreter used to run the redaction sidecar |
| `PIKVM_REDACTOR_CATEGORIES` | all | Comma-separated categories to redact: `secrets`, `contact`, `financial`, `government_id`, `network`, `person`, `location`, `dates`, `faces`, `codes` |
| `PIKVM_REDACTOR_STYLE` | `black box` | Default redaction style: `black box`, `pixelate` or `blur` |
| `PIKVM_REDACTOR_USE_NER` | `true` | Use the GLiNER model for names/addresses. When `true`, `pikvm_load_model` fails if GLiNER can't load; `false` allows rules-only detection |
| `PIKVM_REDACTOR_LOAD_TIMEOUT_MS` | `180000` | Timeout (ms) for `pikvm_load_model` |
| `PIKVM_REDACTOR_TIMEOUT_MS` | `60000` | Timeout (ms) for redacting a single screenshot |
| `REDACTOR_NER_MODEL` | `urchade/gliner_multi_pii-v1` | Read by the upstream redactor to override the GLiNER model |

## Usage with Claude Code

> **Requires Node.js 18+.** This server uses ES modules. If `node --version` shows an older version, replace `"command": "node"` with the full path to a compatible binary (e.g. `"/usr/local/bin/node"` or your nvm path like `"~/.nvm/versions/node/v22.x.x/bin/node"`). This is common when nvm's default alias points to an older version.

Add to your Claude Code MCP settings (`~/.config/claude-code/settings.json` or via the settings UI):

```json
{
  "mcpServers": {
    "pikvm-privacy": {
      "command": "node",
      "args": ["/path/to/pikvm-privacy/dist/index.js"],
      "env": {
        "PIKVM_HOST": "https://<your-pikvm-ip>",
        "PIKVM_USERNAME": "admin",
        "PIKVM_PASSWORD": "your_password"
      }
    }
  }
}
```

Or if using the .env file:

```json
{
  "mcpServers": {
    "pikvm-privacy": {
      "command": "node",
      "args": ["/path/to/pikvm-privacy/dist/index.js"]
    }
  }
}
```

The package also exposes a `pikvm-privacy` bin (e.g. after `npm link`), which can be used as the `command` instead of `node /path/to/pikvm-privacy/dist/index.js`.

## Available Tools

### Display
- **`pikvm_redacted_screenshot`** - Capture current screen as JPEG with sensitive content redacted (optional: maxWidth, maxHeight, quality, style). Requires the redaction model to be loaded
- **`pikvm_get_redacted_text`** - Read the screen as text via PiKVM's OCR, with sensitive content replaced by `[REDACTED <category>]`. For models without vision (optional: langs, left/top/right/bottom region). Requires the redaction model to be loaded
- **`pikvm_get_resolution`** - Get screen resolution and valid coordinate ranges

### Redaction Model
- **`pikvm_load_model`** - Start the redaction sidecar and load the OCR, PII (GLiNER) and face detection models (~12s once weights are cached, longer on first run while they download; uses around 2 GB of RAM; safe to call when already loaded)
- **`pikvm_release_model`** - Stop the redaction sidecar and free its memory

### Keyboard
- **`pikvm_type`** - Type text with keymap-aware special character handling (required: text; optional: keymap, slow, delay)
- **`pikvm_key`** - Send a key or key combo, e.g. Ctrl+Alt+Del (required: key; optional: modifiers, state)
- **`pikvm_shortcut`** - Send multiple keys pressed simultaneously (required: keys array)

### Mouse
- **`pikvm_mouse_move`** - Move cursor to absolute pixel position or relative delta (required: x, y; optional: relative)
- **`pikvm_mouse_click`** - Click a mouse button, optionally at a position (optional: button, x, y, state)
- **`pikvm_mouse_scroll`** - Scroll the mouse wheel (required: deltaY; optional: deltaX)

### Calibration
- **`pikvm_auto_calibrate`** - Automatically detect cursor and compute calibration factors *(preferred)*
- **`pikvm_calibrate`** - Start manual calibration by moving cursor to screen center for visual verification
- **`pikvm_set_calibration`** - Apply correction factors calculated from calibration (required: factorX, factorY)
- **`pikvm_get_calibration`** - Get current calibration state
- **`pikvm_clear_calibration`** - Reset to uncalibrated mode

## Skills (Prompts & Skill Tools)

The server exposes 17 skills that provide structured guidance for agents. Each skill is available via **two discovery paths**:

- **MCP Prompts** — `prompts/list` / `prompts/get` for clients that support the Prompts capability.
- **Skill Tools** — `tools/list` / `tools/call` as `skill_*` read-only tools, ensuring visibility in marketplaces (e.g. LobeHub) that index tools only.

### Tool Guides

| Prompt Name | Skill Tool | Description |
|---|---|---|
| `take-redacted-screenshot` | `skill_take_redacted_screenshot` | Capturing privacy-redacted screenshots with pikvm_redacted_screenshot |
| `get-redacted-text` | `skill_get_redacted_text` | Reading privacy-redacted screen text with pikvm_get_redacted_text (for models without vision) |
| `manage-redaction-model` | `skill_manage_redaction_model` | Loading and releasing the redaction model with pikvm_load_model / pikvm_release_model |
| `check-resolution` | `skill_check_resolution` | Checking screen resolution with pikvm_get_resolution |
| `type-text` | `skill_type_text` | Typing text with pikvm_type |
| `send-key` | `skill_send_key` | Sending keys with pikvm_key |
| `send-shortcut` | `skill_send_shortcut` | Sending keyboard shortcuts with pikvm_shortcut |
| `move-mouse` | `skill_move_mouse` | Moving the mouse with pikvm_mouse_move |
| `click-element` | `skill_click_element` | Clicking with pikvm_mouse_click |
| `scroll-page` | `skill_scroll_page` | Scrolling with pikvm_mouse_scroll |
| `auto-calibrate` | `skill_auto_calibrate` | Automatic mouse calibration with pikvm_auto_calibrate |

### Workflow Recipes

| Prompt Name | Skill Tool | Arguments | Description |
|---|---|---|---|
| `setup-session-workflow` | `skill_setup_session_workflow` | — | Initialize a PiKVM session (resolution, redaction model, screenshot, calibration) |
| `calibrate-mouse-workflow` | `skill_calibrate_mouse_workflow` | — | Calibrate mouse coordinates |
| `click-ui-element-workflow` | `skill_click_ui_element_workflow` | `element_description` (required) | Find and click a UI element |
| `fill-form-workflow` | `skill_fill_form_workflow` | `form_description` (optional) | Fill in a form on screen |
| `navigate-desktop-workflow` | `skill_navigate_desktop_workflow` | `goal` (required) | Navigate a desktop environment |
| `auto-calibrate-mouse-workflow` | `skill_auto_calibrate_mouse_workflow` | — | Automatic mouse calibration |

See [`docs/skills/`](docs/skills/) for detailed human-readable guides.

## Key Codes Reference

Common key codes for `pikvm_key` and `pikvm_shortcut`:

- Letters: `KeyA`, `KeyB`, ... `KeyZ`
- Numbers: `Digit0`, `Digit1`, ... `Digit9`
- Function keys: `F1`, `F2`, ... `F12`
- Modifiers: `ShiftLeft`, `ShiftRight`, `ControlLeft`, `ControlRight`, `AltLeft`, `AltRight`, `MetaLeft`, `MetaRight`
- Special: `Enter`, `Escape`, `Backspace`, `Tab`, `Space`, `Delete`, `Insert`, `Home`, `End`, `PageUp`, `PageDown`
- Arrows: `ArrowUp`, `ArrowDown`, `ArrowLeft`, `ArrowRight`

## Credits

- [PiKVM MCP Server](https://github.com/KultivatorConsulting/pikvm_mcp_server) by Kultivator Consulting — the upstream project this fork is based on, including the auto-calibration feature.
- [screenshot-redactor](https://github.com/cleanroom-ai/screenshot-redactor) by cleanroom-ai — the redaction pipeline, vendored as a git submodule at `vendor/screenshot-redactor`. Licensed under Apache-2.0.

## License

GPL-3.0 - See [LICENSE](LICENSE) for details. The vendored screenshot-redactor is licensed separately under Apache-2.0 (see `vendor/screenshot-redactor/LICENSE`).
