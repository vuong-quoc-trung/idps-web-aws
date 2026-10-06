/* ============================================================
   LoginPage — /login
   ============================================================ */
import { useState, type FormEvent } from 'react';
import { useNavigate, Navigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import './LoginPage.css';

// VS Code logo SVG inline
function BrandLogo() {
  return (
    <svg width="44" height="44" viewBox="0 0 44 44" fill="none" aria-hidden="true">
      <rect width="44" height="44" rx="12" fill="url(#login-brand-grad)" />
      <path
        d="M22 10L10 17v10l12 7 12-7V17L22 10z"
        stroke="white" strokeWidth="1.8" strokeLinejoin="round" fill="none"
      />
      <path
        d="M22 10v17M10 17l12 7 12-7"
        stroke="white" strokeWidth="1.8" strokeLinejoin="round"
      />
      <defs>
        <linearGradient id="login-brand-grad" x1="0" y1="0" x2="44" y2="44">
          <stop stopColor="#007acc" />
          <stop offset="1" stopColor="#005f9e" />
        </linearGradient>
      </defs>
    </svg>
  );
}

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      id="theme-toggle"
      className="theme-toggle"
      onClick={toggleTheme}
      aria-label={theme === 'dark' ? 'Chuyển sang chế độ sáng' : 'Chuyển sang chế độ tối'}
      title={theme === 'dark' ? 'Chế độ sáng' : 'Chế độ tối'}
    >
      {theme === 'dark' ? (
        /* Sun icon */
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="5" stroke="currentColor" strokeWidth="1.75" />
          <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
            stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
        </svg>
      ) : (
        /* Moon icon */
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"
            stroke="currentColor" strokeWidth="1.75" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!loading && user) return <Navigate to="/" replace />;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Đăng nhập thất bại');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      {/* Theme toggle */}
      <ThemeToggle />

      {/* Animated background */}
      <div className="auth-bg" aria-hidden="true">
        <div className="orb orb-1" />
        <div className="orb orb-2" />
        <div className="orb orb-3" />
        <div className="grid-overlay" />
      </div>

      <div className="auth-container">
        {/* Branding */}
        <div className="auth-brand">
          <div className="brand-icon"><BrandLogo /></div>
          <div className="brand-text">
            <span className="brand-name">Student Web</span>
            <span className="brand-sub">Hệ thống quản lý sinh viên</span>
          </div>
        </div>

        {/* Card */}
        <div className="auth-card">
          <div className="auth-card-header">
            <h1>Đăng nhập</h1>
            <p>Nhập thông tin tài khoản của bạn để tiếp tục</p>
          </div>

          {error && (
            <div className="alert alert-error" role="alert" id="login-error">
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" />
                <path d="M8 4.5v4M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              {error}
            </div>
          )}

          <form id="login-form" className="auth-form" onSubmit={handleSubmit} noValidate>
            {/* Username */}
            <div className="field-group">
              <label className="field-label" htmlFor="login-username">Tên đăng nhập</label>
              <div className="input-wrapper">
                <span className="input-icon">
                  <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="5" r="3" stroke="currentColor" strokeWidth="1.5" />
                    <path d="M2 14c0-3.314 2.686-6 6-6s6 2.686 6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </span>
                <input
                  id="login-username"
                  name="username"
                  type="text"
                  className="field-input"
                  placeholder="Nhập tên đăng nhập"
                  autoComplete="username"
                  autoFocus
                  required
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  aria-describedby={error ? 'login-error' : undefined}
                  disabled={submitting}
                />
              </div>
            </div>

            {/* Password */}
            <div className="field-group">
              <label className="field-label" htmlFor="login-password">Mật khẩu</label>
              <div className="input-wrapper">
                <span className="input-icon">
                  <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                    <rect x="2" y="7" width="12" height="8" rx="2" stroke="currentColor" strokeWidth="1.5" />
                    <path d="M5 7V5a3 3 0 016 0v2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    <circle cx="8" cy="11" r="1.2" fill="currentColor" />
                  </svg>
                </span>
                <input
                  id="login-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  className="field-input"
                  placeholder="Nhập mật khẩu"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  disabled={submitting}
                />
                <button
                  type="button"
                  id="toggle-password"
                  className="input-action"
                  onClick={() => setShowPassword(v => !v)}
                  aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                >
                  {showPassword
                    ? <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M2 8s2-4 6-4 6 4 6 4-2 4-6 4-6-4-6-4z" stroke="currentColor" strokeWidth="1.5" /><circle cx="8" cy="8" r="1.5" stroke="currentColor" strokeWidth="1.5" /><path d="M2 2l12 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
                    : <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M2 8s2-4 6-4 6 4 6 4-2 4-6 4-6-4-6-4z" stroke="currentColor" strokeWidth="1.5" /><circle cx="8" cy="8" r="1.5" stroke="currentColor" strokeWidth="1.5" /></svg>
                  }
                </button>
              </div>
            </div>

            <button
              type="submit"
              id="login-submit"
              className="btn-primary"
              disabled={submitting || !username || !password}
            >
              {submitting ? (
                <><span className="spinner" aria-hidden="true" />Đang đăng nhập…</>
              ) : (
                <>Đăng nhập
                  <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </>
              )}
            </button>
          </form>

          <p className="auth-hint">
            Lần đầu đăng nhập?&nbsp;
            <Link to="/activate" id="activate-link">Kích hoạt tài khoản</Link>
          </p>
        </div>

        <p className="auth-footer">
          © {new Date().getFullYear()} Student Web · Hệ thống quản lý thông tin sinh viên
        </p>
      </div>
    </div>
  );
}
