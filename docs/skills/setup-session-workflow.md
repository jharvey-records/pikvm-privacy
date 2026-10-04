# setup-session-workflow

> MCP Prompt: `setup-session-workflow`

Step-by-step procedure for initializing a PiKVM session.

## Arguments

None.

## Workflow Steps

### Step 1 — Check Resolution

Call `pikvm_get_resolution` to determine the screen size and confirm the connection is working.

### Step 2 — Load the Redaction Model

Call `pikvm_load_model`. Screenshots are redacted before you see them, and this loads the models that do it. It can take up to a minute. If it fails, report the error — screenshots will not be available.

### Step 3 — Take Initial Screenshot

Call `pikvm_redacted_screenshot` to see the current state of the remote machine. This confirms video capture and redaction are working and shows you what's on screen. Black boxes mark redacted sensitive content.

### Step 4 — Calibrate Mouse

Run auto-calibration to ensure accurate mouse positioning.

1. Call `pikvm_auto_calibrate` — it automatically detects the cursor and computes calibration factors.
2. If it succeeds, calibration is applied automatically. Proceed to Step 5.
3. If it fails, fall back to manual calibration:
   1. Call `pikvm_calibrate` — this moves the cursor to the screen center.
   2. Call `pikvm_redacted_screenshot` — visually locate the actual cursor position.
   3. If the cursor is **not** at the center, calculate correction factors:
      - factorX = expected_x / actual_x
      - factorY = expected_y / actual_y
   4. Call `pikvm_set_calibration` with the calculated factors.
   5. Call `pikvm_redacted_screenshot` again to verify the calibration looks correct.

### Step 5 — Verify Keyboard (optional)

If you will be typing:

1. Identify a safe text input area on screen (e.g., a terminal, text editor, address bar).
2. Click on it with `pikvm_mouse_click`.
3. Type a short test string with `pikvm_type`.
4. Take a screenshot to verify the text appeared correctly.

### Step 6 — Report Ready

Summarize:

- Screen resolution
- What OS/application is visible
- Redaction model status
- Calibration status
- Any issues detected

The session is now ready for use. When the session is finished, call `pikvm_release_model` to free the redaction model's memory.
