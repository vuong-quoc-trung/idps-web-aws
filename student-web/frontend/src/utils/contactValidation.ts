export const PHONE_ERROR = 'Số điện thoại không hợp lệ. Nhập số Việt Nam (VD: 0912345678) hoặc +mã quốc gia.';
export const EMAIL_ERROR = 'Email không đúng định dạng (VD: ten@gmail.com).';
export function normalizePhone(raw?: string | null): string {
  return (raw ?? '').trim().replace(/[ .()-]/g, '');
}
export function validPhone(raw?: string | null): boolean {
  if (!raw?.trim()) return true;
  if (raw.length > 40 || !/^[+0-9 .()-]+$/.test(raw)) return false;
  const value = normalizePhone(raw);
  return /^(?:0|\+84)(?:[35789][0-9]{8}|2[0-9]{9})$/.test(value)
    || (!value.startsWith('+84') && /^\+[1-9][0-9]{7,14}$/.test(value));
}
export function validEmail(raw?: string | null): boolean {
  if (!raw?.trim()) return true;
  const value = raw.trim(), parts = value.split('@');
  if (value.length > 150 || parts.length !== 2) return false;
  const [local, domain] = parts;
  return local.length <= 64 && !local.startsWith('.') && !local.endsWith('.') && !local.includes('..')
    && /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$/.test(local)
    && /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$/.test(domain);
}
