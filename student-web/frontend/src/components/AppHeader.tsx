import { useState, useRef, useEffect } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import type { CurrentUser } from '../types/auth';
import './AppHeader.css';

const ROLE_LABELS: Record<CurrentUser['role'], string> = {
  ADMIN:   'Quản trị viên',
  STAFF:   'Nhân viên',
  STUDENT: 'Sinh viên',
};
const ROLE_CLASSES: Record<CurrentUser['role'], string> = {
  ADMIN:   'role-admin',
  STAFF:   'role-staff',
  STUDENT: 'role-student',
};

function Avatar({ user, size = 28 }: { user: CurrentUser; size?: number }) {
  const initials = (user.fullName ?? user.username)
    .split(' ').map(w => w[0]).slice(-2).join('').toUpperCase();
  return (
    <div className="avatar" style={{ width: size, height: size }} aria-hidden="true">
      <span>{initials}</span>
    </div>
  );
}

function ThemeToggleBtn() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      id="header-theme-toggle"
      className="header-theme-toggle"
      onClick={toggleTheme}
      aria-label={theme === 'dark' ? 'Chuyển sang chế độ sáng' : 'Chuyển sang chế độ tối'}
      title={theme === 'dark' ? 'Chế độ sáng' : 'Chế độ tối'}
    >
      {theme === 'dark' ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="5" stroke="currentColor" strokeWidth="1.75"/>
          <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
            stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"/>
        </svg>
      ) : (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
          <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"
            stroke="currentColor" strokeWidth="1.75" strokeLinejoin="round"/>
        </svg>
      )}
    </button>
  );
}

export default function AppHeader() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const mobileMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handle = (e: MouseEvent) => {
      const target = e.target as Node;
      if (menuRef.current && !menuRef.current.contains(target)) setOpen(false);
      if (mobileMenuRef.current && !mobileMenuRef.current.contains(target)) {
        const toggleBtn = document.getElementById('mobile-menu-toggle');
        if (!toggleBtn || !toggleBtn.contains(target)) {
          setMobileOpen(false);
        }
      }
    };
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  useEffect(() => {
    const handle = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        setMobileOpen(false);
      }
    };
    document.addEventListener('keydown', handle);
    return () => document.removeEventListener('keydown', handle);
  }, []);

  // Close mobile menu on route changes
  useEffect(() => {
    setMobileOpen(false);
    setOpen(false);
  }, [location.pathname]);

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logout();
      navigate('/login', { replace: true });
    } finally {
      setLoggingOut(false);
      setOpen(false);
      setMobileOpen(false);
    }
  }

  if (!user) return null;

  const pathname = location.pathname;

  return (
    <header className="app-header" id="app-header">
      <div className="header-inner">
        {/* Mobile Hamburger Toggle */}
        <button
          id="mobile-menu-toggle"
          className="mobile-menu-toggle"
          onClick={() => setMobileOpen(v => !v)}
          aria-label={mobileOpen ? 'Đóng menu' : 'Mở menu điều hướng'}
          aria-expanded={mobileOpen}
          aria-controls="mobile-nav-drawer"
        >
          {mobileOpen ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="3" y1="12" x2="21" y2="12"/>
              <line x1="3" y1="6" x2="21" y2="6"/>
              <line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          )}
        </button>

        {/* Logo */}
        <Link to="/" className="header-logo" id="header-logo" aria-label="Trang chủ">
          <div className="header-logo-icon">
            <svg width="26" height="26" viewBox="0 0 32 32" fill="none">
              <rect width="32" height="32" rx="7" fill="url(#hg2)"/>
              <path d="M16 7L7 12v8l9 5 9-5v-8L16 7z" stroke="white" strokeWidth="1.5" strokeLinejoin="round" fill="none"/>
              <path d="M16 7v13M7 12l9 5 9-5" stroke="white" strokeWidth="1.5" strokeLinejoin="round"/>
              <defs>
                <linearGradient id="hg2" x1="0" y1="0" x2="32" y2="32">
                  <stop stopColor="#007acc"/>
                  <stop offset="1" stopColor="#005f9e"/>
                </linearGradient>
              </defs>
            </svg>
          </div>
          <span className="header-logo-text">Student Web</span>
        </Link>

        {/* Desktop Nav */}
        <nav className="header-nav" aria-label="Điều hướng chính">
          <Link
            to="/"
            className={`nav-link ${pathname === '/' ? 'active' : ''}`}
            id="nav-home"
          >
            Trang chủ
          </Link>

          {(user.role === 'ADMIN' || user.role === 'STAFF') && (
            <>
              <Link
                to="/catalog"
                className={`nav-link ${pathname.startsWith('/catalog') ? 'active' : ''}`}
                id="nav-catalog"
              >
                Danh mục học vụ
              </Link>
              <Link
                to="/students"
                className={`nav-link ${pathname.startsWith('/students') ? 'active' : ''}`}
                id="nav-students"
              >
                Sinh viên
              </Link>
            </>
          )}

          {user.role === 'STUDENT' && (
            <>
              <Link
                to="/profile"
                className={`nav-link ${pathname === '/profile' ? 'active' : ''}`}
                id="nav-profile"
              >
                Hồ sơ của tôi
              </Link>
              <Link
                to="/catalog"
                className={`nav-link ${pathname.startsWith('/catalog') ? 'active' : ''}`}
                id="nav-catalog"
              >
                Chương trình & Lớp
              </Link>
            </>
          )}

          {user.role === 'ADMIN' && (
            <Link
              to="/admin"
              className={`nav-link ${pathname.startsWith('/admin') ? 'active' : ''}`}
              id="nav-admin"
            >
              Quản trị
            </Link>
          )}
        </nav>

        {/* Right controls */}
        <div className="header-right" ref={menuRef}>
          <ThemeToggleBtn />

          <button
            id="user-menu-button"
            className="user-menu-trigger"
            onClick={() => setOpen(v => !v)}
            aria-haspopup="true"
            aria-expanded={open}
            aria-label="Menu tài khoản"
          >
            <Avatar user={user} />
            <div className="user-info">
              <span className="user-display-name">{user.fullName ?? user.username}</span>
              <span className={`user-role-badge ${ROLE_CLASSES[user.role]}`}>
                {ROLE_LABELS[user.role]}
              </span>
            </div>
            <span className={`chevron ${open ? 'open' : ''}`} aria-hidden="true">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </span>
          </button>

          {/* User Dropdown */}
          {open && (
            <div className="user-dropdown" id="user-dropdown" role="menu">
              <div className="dropdown-header">
                <Avatar user={user} size={34} />
                <div>
                  <p className="dropdown-name">{user.fullName ?? user.username}</p>
                  <p className="dropdown-username">@{user.username}</p>
                  {user.studentCode && (
                    <p className="dropdown-meta">MSSV: {user.studentCode}</p>
                  )}
                </div>
              </div>

              <div className="dropdown-divider" />

              <div className="dropdown-section">
                <Link
                  to="/"
                  className="dropdown-item"
                  id="menu-home"
                  role="menuitem"
                  onClick={() => setOpen(false)}
                >
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                    <path d="M2 7l6-5 6 5v7a1 1 0 01-1 1H3a1 1 0 01-1-1V7z" stroke="currentColor" strokeWidth="1.35" strokeLinejoin="round"/>
                  </svg>
                  Trang chủ
                </Link>

                {user.role === 'STUDENT' && (
                  <>
                    <Link
                      to="/profile"
                      className="dropdown-item"
                      id="menu-profile"
                      role="menuitem"
                      onClick={() => setOpen(false)}
                    >
                      <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                        <circle cx="7" cy="4" r="2.5" stroke="currentColor" strokeWidth="1.25"/>
                        <path d="M1.5 12.5c0-3.038 2.462-5.5 5.5-5.5s5.5 2.462 5.5 5.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
                      </svg>
                      Hồ sơ cá nhân
                    </Link>
                    <Link
                      to="/catalog"
                      className="dropdown-item"
                      id="menu-catalog-student"
                      role="menuitem"
                      onClick={() => setOpen(false)}
                    >
                      <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                        <rect x="2" y="2" width="12" height="12" rx="2" stroke="currentColor" strokeWidth="1.35"/>
                        <path d="M5 6h6M5 9h4" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round"/>
                      </svg>
                      Chương trình & Lớp
                    </Link>
                  </>
                )}

                {(user.role === 'ADMIN' || user.role === 'STAFF') && (
                  <>
                    <Link
                      to="/students"
                      className="dropdown-item"
                      id="menu-students"
                      role="menuitem"
                      onClick={() => setOpen(false)}
                    >
                      <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                        <path d="M8 2L1 5.5l7 3.5 7-3.5L8 2z" stroke="currentColor" strokeWidth="1.35" strokeLinejoin="round"/>
                        <path d="M3.5 7.5v4.5C3.5 13.5 8 14.5 8 14.5s4.5-1 4.5-2.5V7.5" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round"/>
                      </svg>
                      Quản lý sinh viên
                    </Link>
                    <Link
                      to="/catalog"
                      className="dropdown-item"
                      id="menu-catalog"
                      role="menuitem"
                      onClick={() => setOpen(false)}
                    >
                      <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                        <rect x="2" y="2" width="12" height="12" rx="2" stroke="currentColor" strokeWidth="1.35"/>
                        <path d="M5 6h6M5 9h4" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round"/>
                      </svg>
                      Danh mục học vụ
                    </Link>
                  </>
                )}

                {user.role === 'ADMIN' && (
                  <Link
                    to="/admin"
                    className="dropdown-item"
                    id="menu-admin"
                    role="menuitem"
                    onClick={() => setOpen(false)}
                  >
                    <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                      <path d="M7 1l1.5 3 3.5.5-2.5 2.5.5 3.5L7 9l-3 1.5.5-3.5L2 4.5 5.5 4z"
                        stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/>
                    </svg>
                    Quản trị hệ thống
                  </Link>
                )}
              </div>

              <div className="dropdown-divider" />

              <div className="dropdown-section">
                <button
                  id="logout-button"
                  className="dropdown-item logout-item"
                  role="menuitem"
                  onClick={handleLogout}
                  disabled={loggingOut}
                >
                  {loggingOut ? (
                    <><span className="spinner spinner-sm" aria-hidden="true" />Đang đăng xuất…</>
                  ) : (
                    <>
                      <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                        <path d="M5 2H3a1 1 0 00-1 1v8a1 1 0 001 1h2" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
                        <path d="M9.5 9.5L12 7l-2.5-2.5M12 7H5.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                      Đăng xuất
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Mobile Navigation Drawer */}
      {mobileOpen && (
        <div className="mobile-nav-drawer" id="mobile-nav-drawer" ref={mobileMenuRef}>
          <div className="mobile-nav-user-bar">
            <Avatar user={user} size={32} />
            <div className="mobile-user-meta">
              <span className="mobile-user-name">{user.fullName ?? user.username}</span>
              <span className={`user-role-badge ${ROLE_CLASSES[user.role]}`}>
                {ROLE_LABELS[user.role]}
              </span>
            </div>
          </div>

          <nav className="mobile-nav-links" aria-label="Menu di động">
            <Link
              to="/"
              className={`mobile-nav-link ${pathname === '/' ? 'active' : ''}`}
              onClick={() => setMobileOpen(false)}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2 7l6-5 6 5v7a1 1 0 01-1 1H3a1 1 0 01-1-1V7z" stroke="currentColor" strokeWidth="1.35" strokeLinejoin="round"/>
              </svg>
              Trang chủ
            </Link>

            {(user.role === 'ADMIN' || user.role === 'STAFF') && (
              <>
                <Link
                  to="/students"
                  className={`mobile-nav-link ${pathname.startsWith('/students') ? 'active' : ''}`}
                  onClick={() => setMobileOpen(false)}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M8 2L1 5.5l7 3.5 7-3.5L8 2z" stroke="currentColor" strokeWidth="1.35" strokeLinejoin="round"/>
                    <path d="M3.5 7.5v4.5C3.5 13.5 8 14.5 8 14.5s4.5-1 4.5-2.5V7.5" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round"/>
                  </svg>
                  Quản lý sinh viên
                </Link>
                <Link
                  to="/catalog"
                  className={`mobile-nav-link ${pathname.startsWith('/catalog') ? 'active' : ''}`}
                  onClick={() => setMobileOpen(false)}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <rect x="2" y="2" width="12" height="12" rx="2" stroke="currentColor" strokeWidth="1.35"/>
                    <path d="M5 6h6M5 9h4" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round"/>
                  </svg>
                  Danh mục học vụ
                </Link>
              </>
            )}

            {user.role === 'STUDENT' && (
              <>
                <Link
                  to="/profile"
                  className={`mobile-nav-link ${pathname === '/profile' ? 'active' : ''}`}
                  onClick={() => setMobileOpen(false)}
                >
                  <svg width="16" height="16" viewBox="0 0 14 14" fill="none">
                    <circle cx="7" cy="4" r="2.5" stroke="currentColor" strokeWidth="1.25"/>
                    <path d="M1.5 12.5c0-3.038 2.462-5.5 5.5-5.5s5.5 2.462 5.5 5.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
                  </svg>
                  Hồ sơ của tôi
                </Link>
                <Link
                  to="/catalog"
                  className={`mobile-nav-link ${pathname.startsWith('/catalog') ? 'active' : ''}`}
                  onClick={() => setMobileOpen(false)}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <rect x="2" y="2" width="12" height="12" rx="2" stroke="currentColor" strokeWidth="1.35"/>
                    <path d="M5 6h6M5 9h4" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round"/>
                  </svg>
                  Chương trình & Lớp
                </Link>
              </>
            )}

            {user.role === 'ADMIN' && (
              <Link
                to="/admin"
                className={`mobile-nav-link ${pathname.startsWith('/admin') ? 'active' : ''}`}
                onClick={() => setMobileOpen(false)}
              >
                <svg width="16" height="16" viewBox="0 0 14 14" fill="none">
                  <path d="M7 1l1.5 3 3.5.5-2.5 2.5.5 3.5L7 9l-3 1.5.5-3.5L2 4.5 5.5 4z"
                    stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/>
                </svg>
                Quản trị hệ thống
              </Link>
            )}

            <button
              className="mobile-nav-link logout-btn"
              onClick={handleLogout}
              disabled={loggingOut}
            >
              <svg width="16" height="16" viewBox="0 0 14 14" fill="none">
                <path d="M5 2H3a1 1 0 00-1 1v8a1 1 0 001 1h2" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
                <path d="M9.5 9.5L12 7l-2.5-2.5M12 7H5.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              {loggingOut ? 'Đang đăng xuất…' : 'Đăng xuất'}
            </button>
          </nav>
        </div>
      )}
    </header>
  );
}
