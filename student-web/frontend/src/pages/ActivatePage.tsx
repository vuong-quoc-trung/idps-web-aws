/* ============================================================
   ActivatePage — /activate
   First-time account activation using a one-time token
   ============================================================ */
import { useState, type FormEvent } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { activateAccount } from '../api/authApi';
import { useTheme } from '../contexts/ThemeContext';
import './ActivatePage.css';

type Step = 'form' | 'success' | 'error';

function validatePassword(pwd: string): string | null {
  if (pwd.length < 12) return 'Mật khẩu phải có ít nhất 12 ký tự';
  if (new TextEncoder().encode(pwd).length > 72)
    return 'Mật khẩu vượt quá 72 byte UTF-8';
  return null;
}

function PasswordStrength({ password }: { password: string }) {
  const checks = [
    { label: 'Ít nhất 12 ký tự', ok: password.length >= 12 },
    { label: 'Chữ hoa (A-Z)', ok: /[A-Z]/.test(password) },
    { label: 'Chữ thường (a-z)', ok: /[a-z]/.test(password) },
    { label: 'Chữ số (0-9)', ok: /[0-9]/.test(password) },
    { label: 'Ký tự đặc biệt', ok: /[^A-Za-z0-9]/.test(password) },
  ];
  const score = checks.filter(c => c.ok).length;
  const levels = ['', 'Rất yếu', 'Yếu', 'Trung bình', 'Mạnh', 'Rất mạnh'];
  const colors = ['', '#f14c4c', '#f97316', '#cca700', '#4ec94e', '#007acc'];

  if (!password) return null;
  return (
    <div className="pwd-strength">
      <div className="strength-bar">
        {[1, 2, 3, 4, 5].map(i => (
          <div key={i} className="strength-segment"
            style={{ background: i <= score ? colors[score] : undefined }} />
        ))}
      </div>
      <p className="strength-label" style={{ color: colors[score] }}>{levels[score]}</p>
      <ul className="strength-checks">
        {checks.map(c => (
          <li key={c.label} className={c.ok ? 'ok' : ''}>
            <span className="check-icon">{c.ok ? '✓' : '○'}</span>{c.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button id="theme-toggle" className="theme-toggle" onClick={toggleTheme}
      aria-label={theme === 'dark' ? 'Chuyển sang chế độ sáng' : 'Chuyển sang chế độ tối'}>
      {theme === 'dark' ? (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="5" stroke="currentColor" strokeWidth="1.75" />
          <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
            stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"
            stroke="currentColor" strokeWidth="1.75" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}

// Icon helpers outside render
const EyeOff = () => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
    <path d="M2 8s2-4 6-4 6 4 6 4-2 4-6 4-6-4-6-4z" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="8" cy="8" r="1.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M2 2l12 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);
const EyeOn = () => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
    <path d="M2 8s2-4 6-4 6 4 6 4-2 4-6 4-6-4-6-4z" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="8" cy="8" r="1.5" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

export default function ActivatePage() {
  const [searchParams] = useSearchParams();

  const [token, setToken] = useState(searchParams.get('token') ?? '');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [showCfm, setShowCfm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [step, setStep] = useState<Step>('form');

  const mismatch = confirm.length > 0 && confirm !== password;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldError(null);
    const pwdErr = validatePassword(password);
    if (pwdErr) { setFieldError(pwdErr); return; }
    if (password !== confirm) { setFieldError('Mật khẩu xác nhận không khớp'); return; }
    setSubmitting(true);
    try {
      await activateAccount(token.trim(), password);
      setStep('success');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Kích hoạt tài khoản thất bại');
      setStep('error');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <ThemeToggle />

      <div className="auth-bg" aria-hidden="true">
        <div className="orb orb-1" style={{ background: 'radial-gradient(circle, var(--role-admin-text, #6f42c1) 0%, transparent 65%)' }} />
        <div className="orb orb-2" style={{ background: 'radial-gradient(circle, var(--orb-2-color) 0%, transparent 65%)' }} />
        <div className="orb orb-3" />
        <div className="grid-overlay" />
      </div>

      {/* *** Fixed: use auth-container with correct centering *** */}
      <div className="auth-container auth-container--wide">
        {/* Branding */}
        <div className="auth-brand">
          <div className="brand-icon">
            <svg width="44" height="44" viewBox="0 0 44 44" fill="none" aria-hidden="true">
              <rect width="44" height="44" rx="12" fill="url(#act-brand-grad)" />
              <path d="M22 10L10 17v10l12 7 12-7V17L22 10z" stroke="white" strokeWidth="1.8" strokeLinejoin="round" fill="none" />
              <path d="M22 10v17M10 17l12 7 12-7" stroke="white" strokeWidth="1.8" strokeLinejoin="round" />
              <defs>
                <linearGradient id="act-brand-grad" x1="0" y1="0" x2="44" y2="44">
                  <stop stopColor="#6f42c1" />
                  <stop offset="1" stopColor="#4c2e8e" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <div className="brand-text">
            <span className="brand-name">Student Web</span>
            <span className="brand-sub">Kích hoạt tài khoản lần đầu</span>
          </div>
        </div>

        <div className="auth-card">
          {/* SUCCESS */}
          {step === 'success' && (
            <div className="result-state success-state">
              <div className="result-icon success-icon">
                <svg width="36" height="36" viewBox="0 0 40 40" fill="none">
                  <circle cx="20" cy="20" r="18" stroke="currentColor" strokeWidth="2" className="success-ring" />
                  <path d="M12 20l6 6 10-12" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <h1>Kích hoạt thành công!</h1>
              <p>Tài khoản của bạn đã được kích hoạt. Hãy đăng nhập để tiếp tục.</p>
              <Link to="/login" id="go-to-login" className="btn-primary" style={{ textDecoration: 'none' }}>
                Đến trang đăng nhập
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                  <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </Link>
            </div>
          )}

          {/* ERROR */}
          {step === 'error' && (
            <div className="result-state error-state">
              <div className="result-icon error-icon">
                <svg width="36" height="36" viewBox="0 0 40 40" fill="none">
                  <circle cx="20" cy="20" r="18" stroke="currentColor" strokeWidth="2" />
                  <path d="M13 13l14 14M27 13l-14 14" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                </svg>
              </div>
              <h1>Kích hoạt thất bại</h1>
              <p>{error}</p>
              <button id="retry-activate" className="btn-primary"
                onClick={() => { setStep('form'); setError(null); }}>
                Thử lại
              </button>
              <p className="auth-hint" style={{ marginTop: 4 }}>
                <Link to="/login" id="back-to-login-from-error">Quay lại đăng nhập</Link>
              </p>
            </div>
          )}

          {/* FORM */}
          {step === 'form' && (
            <>
              <div className="auth-card-header">
                <h1>Đặt mật khẩu lần đầu</h1>
                <p>Nhập token kích hoạt và tạo mật khẩu mới cho tài khoản</p>
              </div>

              {error && (
                <div className="alert alert-error" role="alert" id="activate-error">
                  <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" />
                    <path d="M8 4.5v4M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                  {error}
                </div>
              )}

              <form id="activate-form" className="auth-form" onSubmit={handleSubmit} noValidate>
                {/* Token */}
                <div className="field-group">
                  <label className="field-label" htmlFor="activate-token">Token kích hoạt</label>
                  <div className="input-wrapper">
                    <span className="input-icon">
                      <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                        <path d="M10 2a4 4 0 00-3.873 5H3l-1 1v2h1v1h2v-1h1v-2l-.127-.127A4 4 0 1010 2z"
                          stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                        <circle cx="10" cy="5" r="1" fill="currentColor" />
                      </svg>
                    </span>
                    <input
                      id="activate-token"
                      type="text"
                      className="field-input"
                      placeholder="Dán token vào đây"
                      autoFocus={!token}
                      required
                      value={token}
                      onChange={e => setToken(e.target.value)}
                      disabled={submitting}
                      style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', letterSpacing: '0.3px' }}
                    />
                  </div>
                  <p className="field-hint">Token do quản trị viên cung cấp, có hiệu lực trong 24 giờ</p>
                </div>

                {/* New password */}
                <div className="field-group">
                  <label className="field-label" htmlFor="activate-password">Mật khẩu mới</label>
                  <div className="input-wrapper">
                    <span className="input-icon">
                      <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                        <rect x="2" y="7" width="12" height="8" rx="2" stroke="currentColor" strokeWidth="1.5" />
                        <path d="M5 7V5a3 3 0 016 0v2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                        <circle cx="8" cy="11" r="1.2" fill="currentColor" />
                      </svg>
                    </span>
                    <input
                      id="activate-password"
                      type={showPwd ? 'text' : 'password'}
                      className="field-input"
                      placeholder="Tối thiểu 12 ký tự"
                      autoComplete="new-password"
                      required
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      disabled={submitting}
                    />
                    <button type="button" id="toggle-new-password" className="input-action"
                      onClick={() => setShowPwd(v => !v)}
                      aria-label={showPwd ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}>
                      {showPwd ? <EyeOff /> : <EyeOn />}
                    </button>
                  </div>
                  <PasswordStrength password={password} />
                </div>

                {/* Confirm */}
                <div className="field-group">
                  <label className="field-label" htmlFor="activate-confirm">Xác nhận mật khẩu</label>
                  <div className="input-wrapper">
                    <span className="input-icon">
                      <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                        <rect x="2" y="7" width="12" height="8" rx="2" stroke="currentColor" strokeWidth="1.5" />
                        <path d="M5 7V5a3 3 0 016 0v2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                        <path d="M6 11l1.5 1.5L10 9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </span>
                    <input
                      id="activate-confirm"
                      type={showCfm ? 'text' : 'password'}
                      className={`field-input ${mismatch ? 'input-error' : ''}`}
                      placeholder="Nhập lại mật khẩu"
                      autoComplete="new-password"
                      required
                      value={confirm}
                      onChange={e => setConfirm(e.target.value)}
                      disabled={submitting}
                    />
                    <button type="button" id="toggle-confirm-password" className="input-action"
                      onClick={() => setShowCfm(v => !v)}
                      aria-label={showCfm ? 'Ẩn xác nhận' : 'Hiện xác nhận'}>
                      {showCfm ? <EyeOff /> : <EyeOn />}
                    </button>
                  </div>
                  {mismatch && (
                    <p className="field-error-text">Mật khẩu xác nhận không khớp</p>
                  )}
                </div>

                {fieldError && (
                  <div className="alert alert-error" role="alert">
                    <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                      <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" />
                      <path d="M8 4.5v4M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                    {fieldError}
                  </div>
                )}

                <button
                  type="submit"
                  id="activate-submit"
                  className="btn-primary"
                  disabled={submitting || !token || !password || !confirm || mismatch}
                >
                  {submitting
                    ? <><span className="spinner" aria-hidden="true" />Đang kích hoạt…</>
                    : <>Kích hoạt tài khoản
                      <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                        <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </>
                  }
                </button>
              </form>

              <p className="auth-hint">
                Đã có mật khẩu?&nbsp;
                <Link to="/login" id="back-to-login">Đăng nhập</Link>
              </p>
            </>
          )}
        </div>

        <p className="auth-footer">
          © {new Date().getFullYear()} Student Web · Token có hiệu lực trong 24 giờ
        </p>
      </div>
    </div>
  );
}
