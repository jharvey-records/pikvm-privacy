# take-redacted-screenshot

> MCP Prompt: `take-redacted-screenshot`

Guide for capturing privacy-redacted screenshots with `pikvm_redacted_screenshot`.

## Purpose

Capture the current screen of the remote machine as a JPEG image, with sensitive content blacked out before the image is returned. This is your primary way to **see** what is on screen. There is no unredacted screenshot tool.

Redacted categories (configurable by the server operator): secrets (API keys, tokens, passwords), contact details (emails, phone numbers, usernames), financial data, government IDs, IP/MAC addresses, people's names, street addresses, dates of birth, faces, and QR codes/barcodes.

## Prerequisite

The redaction model must be loaded. Call `pikvm_load_model` once at the start of a session (see [manage-redaction-model.md](manage-redaction-model.md)). If it is not loaded, this tool returns an error and no image.

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| maxWidth | number | *(native)* | Maximum width in pixels — image is scaled down after redaction if the screen is wider |
| maxHeight | number | *(native)* | Maximum height in pixels — image is scaled down after redaction if the screen is taller |
| quality | number | 80 | JPEG quality (1-100) used when scaling down |
| style | string | black box | Redaction style: `black box`, `pixelate` or `blur` |

Redaction always runs on the full-resolution capture, so scaling never weakens it. Scaling preserves aspect ratio, and the server tracks the scale factor so that mouse coordinates you derive from the image are automatically mapped back to native resolution.

## Example Call

```json
{
  "name": "pikvm_redacted_screenshot",
  "arguments": { "maxWidth": 1280, "quality": 70 }
}
```

## Tips

- Each call takes a second or more because OCR and entity recognition run on every capture.
- Redacted regions appear as solid black boxes. Treat them as content you are not meant to read — do not try to infer or reconstruct it.
- Redaction can also cover non-sensitive text (e.g. a label that looks like a name). If a UI element you need is hidden, navigate by its surroundings instead.
- Always take a screenshot **after** performing an action to verify the result.
- The response includes a text line describing dimensions, any scaling, and how many items of each category were redacted.
