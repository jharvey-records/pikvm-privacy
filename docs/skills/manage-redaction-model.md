# manage-redaction-model

> MCP Prompt: `manage-redaction-model`

Guide for loading and releasing the screenshot redaction model with `pikvm_load_model` and `pikvm_release_model`.

## Purpose

`pikvm_redacted_screenshot` relies on OCR, PII entity recognition and face detection models that run in a separate Python process on the MCP server host. These tools control when that process — and the memory it uses (around 2 GB) — exists.

## Arguments

None.

## pikvm_load_model

Starts the redaction process and loads every model. Takes roughly 10-60 seconds (longer the very first time, when the model weights are downloaded). Safe to call repeatedly — if the model is already loaded it returns immediately.

The response reports the load time, the categories that will be redacted, and whether the name/address model is active.

## pikvm_release_model

Stops the redaction process and frees its memory. After this, `pikvm_redacted_screenshot` returns an error until `pikvm_load_model` is called again.

## Example Calls

```json
{ "name": "pikvm_load_model", "arguments": {} }
```

```json
{ "name": "pikvm_release_model", "arguments": {} }
```

## Tips

- Load the model at the start of a session (see [setup-session-workflow.md](setup-session-workflow.md)) rather than waiting for the first screenshot to fail.
- Release the model when you are finished with the remote machine, or when you will not need screenshots for a long time.
- If the redaction process crashes, the model is marked as unloaded and screenshots fail safely; call `pikvm_load_model` again to recover.
- Loading fails (rather than silently degrading) if a required model cannot be loaded.
