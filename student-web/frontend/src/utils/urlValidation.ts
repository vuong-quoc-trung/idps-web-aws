/** Optional absolute HTTP(S) URL; reject credentials and browser URL repair. */
export function validHttpUrl(value?: string | null): boolean {
  if (value == null) return true;
  if (/[\x00-\x1f\x7f]/.test(value)) return false;
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
