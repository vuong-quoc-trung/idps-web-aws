import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { apiPost } from '../api/client';
import { validEmail } from '../utils/contactValidation';
import './LoginPage.css';
import './PasswordPage.css';

export default function ActivationIdentityForm() {
  const [form, setForm] = useState({ studentCode: '', fullName: '', dateOfBirth: '', gender: '', citizenId: '', classCode: '', familyPhoneNumber: '' });
  const [proof, setProof] = useState('');
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault(); if (busy) return;
    setError(''); setBusy(true);
    try {
      if (!proof) {
        const result = await apiPost<{ proof: string }>('/auth/activation/verify', form);
        setProof(result.proof);
      } else {
        if (!email.trim() || !validEmail(email)) throw new Error('Vui lòng nhập email hợp lệ.');
        await apiPost('/auth/activation/send', { proof, email: email.trim() });
        setProof(''); setSent(true); setEmail('');
      }
    } catch (e) { setError(e instanceof Error ? e.message : 'Không kết nối được máy chủ.'); }
    finally { setBusy(false); }
  }
  const fields: [keyof typeof form, string, string, boolean][] = [
    ['studentCode', 'Mã sinh viên', 'text', true], ['fullName', 'Họ và tên', 'text', true],
    ['dateOfBirth', 'Ngày sinh', 'date', true], ['citizenId', 'Số CCCD', 'text', true],
    ['classCode', 'Mã lớp', 'text', true],
    ['familyPhoneNumber', 'Số điện thoại gia đình (nếu nhà trường đã lưu)', 'tel', false],
  ];
  return <main className="auth-page password-page"><div className="auth-container"><section className="auth-card">
    <div className="auth-card-header"><h1>Kích hoạt tài khoản</h1><p>DUT student system · {sent ? 'Kiểm tra email' : proof ? 'Bước 2 — Email nhận liên kết' : 'Bước 1 — Đối chiếu thông tin'}</p></div>
    {sent ? <div role="status"><p>Link kích hoạt đã được gửi. Kiểm tra hộp thư và thư rác, sau đó mở link để đặt mật khẩu lần đầu. Link có hiệu lực 24 giờ.</p>
      <button className="btn-primary" onClick={() => setSent(false)}>Đối chiếu lại để gửi link mới</button></div>
      : <><p className="auth-hint">{proof ? 'Thông tin đã khớp. Nhập Gmail/email cá nhân bạn sử dụng. Hoàn thành bước này trong 5 phút.' : 'Nhập đúng thông tin nhà trường cung cấp. Không cần thông tin ngân hàng. Nếu hồ sơ chưa có ngày sinh, giới tính hoặc CCCD, hãy liên hệ nhà trường bổ sung.'}</p>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      <form className="auth-form" onSubmit={submit}>
        {proof ? <div className="field-group"><label htmlFor="activation-email" className="field-label">Email cá nhân nhận link</label>
          <input id="activation-email" className="field-input" type="email" autoComplete="email" maxLength={150} required disabled={busy} value={email} onChange={e => setEmail(e.target.value)} /></div>
          : <>{fields.map(([key, label, type, required]) => <div className="field-group" key={key}>
            <label className="field-label" htmlFor={'activation-' + key}>{label}</label>
            <input id={'activation-' + key} className="field-input" type={type} required={required} maxLength={key === 'fullName' ? 120 : 50} disabled={busy}
              value={form[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} /></div>)}
            <div className="field-group"><label htmlFor="activation-gender" className="field-label">Giới tính</label>
              <select id="activation-gender" className="field-input" required disabled={busy} value={form.gender} onChange={e => setForm(f => ({ ...f, gender: e.target.value }))}>
                <option value="">Chọn giới tính</option><option value="MALE">Nam</option><option value="FEMALE">Nữ</option><option value="OTHER">Khác</option>
              </select></div></>}
        <button className="btn-primary" disabled={busy}>{busy ? 'Đang xử lý…' : proof ? 'Gửi link kích hoạt' : 'Đối chiếu thông tin'}</button>
        {proof && <button type="button" disabled={busy} onClick={() => { setProof(''); setError(''); }}>Quay lại đối chiếu</button>}
      </form></>}
    <p className="auth-hint"><Link to="/login">Quay lại đăng nhập</Link></p>
  </section></div></main>;
}
