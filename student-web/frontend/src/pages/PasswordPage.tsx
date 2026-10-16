import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { fetchMe, changePassword, requestPasswordReset, resetPassword } from '../api/authApi';
import { useAuth } from '../contexts/AuthContext';
import { passwordError } from '../utils/passwordValidation';
import './LoginPage.css';
import './PasswordPage.css';

export default function PasswordPage({ mode }: { mode: 'change' | 'forgot' }) {
  const changing = mode === 'change';
  const { clearSession } = useAuth();
  const navigate = useNavigate();
  const [studentCode, setStudentCode] = useState('');
  const [current, setCurrent] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [code, setCode] = useState('');
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [show, setShow] = useState(false);
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const remaining = Math.max(0, Math.ceil((resendAt - now) / 1000));
  async function sendCode() {
    if (busy || remaining > 0) return;
    if (!studentCode.trim()) { setError('Vui lòng nhập mã sinh viên.'); return; }
    setBusy(true); setError(''); setNotice('');
    try {
      await requestPasswordReset(studentCode.trim());
      setSent(true); setCode(''); setResendAt(Date.now() + 60000); setNow(Date.now());
      setNotice('Nếu tài khoản đủ điều kiện, mã sẽ được gửi tới email cá nhân đã lưu trong hồ sơ. Kiểm tra cả thư rác. Mã có hiệu lực 5 phút; mã mới thay thế mã trước.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Không kết nối được máy chủ.'); }
    finally { setBusy(false); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!changing && !sent) { await sendCode(); return; }
    const invalid = passwordError(password, confirm);
    if (invalid) { setError(invalid); return; }
    if (changing && (!current || current === password)) { setError('Nhập mật khẩu hiện tại và chọn mật khẩu mới khác mật khẩu cũ.'); return; }
    if (!changing && !/^[0-9]{6}$/.test(code)) { setError('Mã xác thực phải gồm 6 chữ số.'); return; }
    setBusy(true); setError('');
    try {
      if (changing) await changePassword(current, password);
      else await resetPassword(studentCode.trim(), code, password);
      setCurrent(''); setPassword(''); setConfirm(''); setCode('');
      await fetchMe(); // Let backend invalidate the old authenticated session before the next login.
      clearSession();
      navigate('/login', { replace: true, state: { passwordNotice: 'Mật khẩu đã được cập nhật. Vui lòng đăng nhập bằng mật khẩu mới.' } });
    } catch (e) { setError(e instanceof Error ? e.message : 'Không kết nối được máy chủ.'); }
    finally { setBusy(false); }
  }
  return <main className="auth-page password-page"><div className="auth-container"><section className="auth-card">
    <div className="auth-card-header"><h1>{changing ? 'Đổi mật khẩu' : 'Quên mật khẩu'}</h1>
      <p>{changing ? 'Dành cho tài khoản đang đăng nhập. Sau khi đổi, bạn cần đăng nhập lại.' : 'Sinh viên nhận mã xác thực qua email cá nhân đã lưu trong hồ sơ.'}</p></div>
    {!changing && <p className="auth-hint">Admin/staff quên mật khẩu: liên hệ người quản trị hệ thống. Tài khoản chưa kích hoạt cần dùng luồng kích hoạt.</p>}
    {notice && <div className="password-notice" role="status">{notice}</div>}
    {error && <div className="alert alert-error" role="alert">{error}</div>}
    <form className="auth-form" onSubmit={submit}>
      {!changing && <div className="field-group"><label className="field-label" htmlFor="reset-student">Mã sinh viên</label>
        <input id="reset-student" className="field-input" autoComplete="username" maxLength={50} required value={studentCode}
          placeholder="STU-2024-000001" disabled={busy || sent} onChange={e => setStudentCode(e.target.value)} /></div>}
      {changing && <div className="field-group"><label className="field-label" htmlFor="current-password">Mật khẩu hiện tại</label>
        <input id="current-password" className="field-input" type={show ? 'text' : 'password'} autoComplete="current-password" required maxLength={72}
          disabled={busy} value={current} onChange={e => setCurrent(e.target.value)} /></div>}
      {sent && !changing && <div className="field-group"><label className="field-label" htmlFor="reset-code">Mã xác thực</label>
        <input id="reset-code" className="field-input" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required
          disabled={busy} value={code} onChange={e => setCode(e.target.value)} /></div>}
      {(changing || sent) && <>
        <div className="field-group"><label className="field-label" htmlFor="new-password">Mật khẩu mới</label>
          <input id="new-password" className="field-input" type={show ? 'text' : 'password'} autoComplete="new-password" required minLength={12} maxLength={72}
            aria-describedby="password-policy" disabled={busy} value={password} onChange={e => setPassword(e.target.value)} />
          <small id="password-policy">Ít nhất 12 ký tự, tối đa 72 byte UTF-8.</small></div>
        <div className="field-group"><label className="field-label" htmlFor="confirm-password">Nhập lại mật khẩu mới</label>
          <input id="confirm-password" className="field-input" type={show ? 'text' : 'password'} autoComplete="new-password" required maxLength={72}
            disabled={busy} value={confirm} onChange={e => setConfirm(e.target.value)} /></div>
        <label className="password-visibility"><input type="checkbox" checked={show} onChange={e => setShow(e.target.checked)} /> Hiện mật khẩu</label>
      </>}
      <button type="submit" className="btn-primary" disabled={busy || (!changing && !sent && remaining > 0)}>{busy ? 'Đang xử lý…' : changing ? 'Đổi mật khẩu' : sent ? 'Xác thực và đặt mật khẩu mới' : remaining > 0 ? `Gửi lại sau ${remaining}s` : 'Gửi mã xác thực'}</button>
      {sent && !changing && <div className="password-actions">
        <button type="button" disabled={busy || remaining > 0} onClick={sendCode}>{remaining > 0 ? `Gửi lại sau ${remaining}s` : 'Gửi lại mã'}</button>
        <button type="button" disabled={busy} onClick={() => { setSent(false); setCode(''); setPassword(''); setConfirm(''); setError(''); setNotice(''); }}>Đổi mã sinh viên</button>
      </div>}
    </form>
    <p className="auth-hint"><Link to={changing ? '/' : '/login'}>{changing ? 'Về trang chủ' : 'Quay lại đăng nhập'}</Link></p>
  </section></div></main>;
}
