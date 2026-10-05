# get-redacted-text

> MCP Prompt: `get-redacted-text`

Guide for reading privacy-redacted screen text with `pikvm_get_redacted_text` (for models without vision).

## Purpose

Read the text on the remote machine's screen as plain text, using PiKVM's built-in OCR, with sensitive content replaced by placeholders before it is returned. Use this instead of `pikvm_redacted_screenshot` if you cannot view images. It works best for terminals, consoles and other text-heavy screens. There is no tool that returns unredacted text.

Sensitive values are replaced with `[REDACTED <category>]`, e.g. `[REDACTED secrets]`, `[REDACTED person]`, `[REDACTED network]`. Redacted categories (configurable by the server operator): secrets (API keys, tokens, passwords), contact details (emails, phone numbers, usernames), financial data, government IDs, IP/MAC addresses, people's names, street addresses and dates of birth.

## Prerequisite

The redaction model must be loaded. Call `pikvm_load_model` once at the start of a session (see [manage-redaction-model.md](manage-redaction-model.md)). If it is not loaded, this tool returns an error and no text.

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| langs | string[] | *(PiKVM default)* | Tesseract language codes, e.g. `["eng"]` |
| left, top, right, bottom | number | *(whole screen)* | Region to read, in native screen pixels. Give all four or none |

## Example Calls

```json
{ "name": "pikvm_get_redacted_text", "arguments": {} }
```

```json
{
  "name": "pikvm_get_redacted_text",
  "arguments": { "left": 0, "top": 800, "right": 1920, "bottom": 1080 }
}
```

## Example Response

```
Redacted 2 item(s): secrets 1, network 1.

user@host:~$ cat config.env
AWS_ACCESS_KEY_ID=[REDACTED secrets]
SERVER=[REDACTED network]
```

## Tips

- The response starts with a summary of how many items of each category were redacted, followed by a blank line and the screen text.
- Treat `[REDACTED ...]` placeholders as content you are not meant to read — do not try to infer or reconstruct it.
- OCR gives text only: no icons, colours or positions. Drive the machine with the keyboard (`pikvm_type`, `pikvm_key`, `pikvm_shortcut`) rather than the mouse.
- To read just the latest output of a busy terminal, run `clear` before your command, or limit the region to the bottom of the screen (use `pikvm_get_resolution` for the screen size).
- OCR can misread characters (e.g. `l`/`1`, `O`/`0`). Don't copy exact values like hashes from the screen; redirect them to a file or compare them with a command instead.
- Redaction is best-effort and may also replace harmless text that looks like a name or secret.
- Read the screen again **after** each action to verify the result.
