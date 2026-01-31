export async function copyToClipboard(text: string, fallbackEl?: HTMLElement): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    if (fallbackEl) {
      const range = document.createRange();
      range.selectNodeContents(fallbackEl);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    }
    return false;
  }
}
