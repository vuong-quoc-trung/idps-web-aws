function hasControlChar(str: string): boolean {
  for (let i = 0; i < str.length; i++) {
    const code = str.charCodeAt(i);
    if (code <= 0x1f || code === 0x7f) return true;
  }
  return false;
}

/** Optional absolute HTTP(S) URL; reject credentials and browser URL repair. */
export function validHttpUrl(value?: string | null): boolean {
  if (value == null) return true;
  if (hasControlChar(value)) return false;
  const text = value.trim();
  if (!text) return true;
  if (!/^https?:\/\//i.test(text) || /[\s\\<>"{}|^`]/.test(text) || /%(?![0-9a-f]{2})/i.test(text)) return false;
  const authority = text.match(/^https?:\/\/([^/?#]+)/i)?.[1];
  if (!authority || authority.includes('@') || authority.includes('%')) return false;
  try {
    const url = new URL(text);
    return !!url.hostname && !url.username && !url.password
      && (!url.port || Number(url.port) >= 1 && Number(url.port) <= 65535);
  } catch {
    return false;
  }
}
