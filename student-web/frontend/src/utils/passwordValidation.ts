export function passwordError(password: string, confirmation: string): string {
  if (!password.trim() || password.length < 12) return 'Mật khẩu mới cần ít nhất 12 ký tự.';
  if (new TextEncoder().encode(password).length > 72) return 'Mật khẩu mới vượt quá 72 byte UTF-8; ký tự có dấu có thể chiếm nhiều byte.';
  if (password !== confirmation) return 'Xác nhận mật khẩu chưa khớp.';
  return '';
}
