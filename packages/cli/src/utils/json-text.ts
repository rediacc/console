/**
 * Parsing for JSON files a person can edit. Windows PowerShell 5.1
 * (`Set-Content -Encoding utf8`) and older Notepad write a UTF-8 byte order
 * mark, which `JSON.parse` rejects as "Unexpected token '﻿'". Every
 * reader of a config-dir JSON file goes through here; writes stay BOM-free.
 */

/** `text` without one leading U+FEFF. */
export function stripBom(text: string): string {
  return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
}

/** `JSON.parse` of file text that may start with a byte order mark. */
export function parseJsonText<T = unknown>(text: string): T {
  return JSON.parse(stripBom(text)) as T;
}
