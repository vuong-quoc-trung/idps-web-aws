/* ============================================================
   DashboardPage — placeholder home page after login
   ============================================================ */
import { useAuth } from '../contexts/AuthContext';
import AppHeader from '../components/AppHeader';
import './DashboardPage.css';

const ROLE_WELCOME: Record<string, string> = {
  ADMIN:   'Chào mừng, Quản trị viên!',
  STAFF:   'Chào mừng trở lại!',
  STUDENT: 'Chào mừng đến hệ thống hồ sơ sinh viên!',
};

export default function DashboardPage() {
  const { user } = useAuth();
  if (!user) return null;

  return (
    <>
      <AppHeader />
      <main className="dashboard-main">
        <div className="dashboard-content">
          {/* Welcome card */}
          <div className="welcome-card">
            <div className="welcome-glow" aria-hidden="true" />
            <div className="welcome-body">
              <div className="welcome-avatar">
                {(user.fullName ?? user.username)
                  .split(' ')
                  .map(w => w[0])
                  .slice(-2)
                  .join('')
                  .toUpperCase()}
              </div>
              <div>
                <h1 className="welcome-title">
                  {ROLE_WELCOME[user.role] ?? 'Chào mừng!'}
                </h1>
                <p className="welcome-subtitle">
                  {user.fullName && <><strong>{user.fullName}</strong> · </>}
                  @{user.username}
                  {user.studentCode && <> · MSSV: <strong>{user.studentCode}</strong></>}
                </p>
              </div>
            </div>
          </div>

          {/* Info cards */}
          <div className="info-grid">
            <InfoCard
              icon={
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <circle cx="10" cy="7" r="3.5" stroke="currentColor" strokeWidth="1.5"/>
                  <path d="M3 18c0-3.866 3.134-7 7-7s7 3.134 7 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              }
              label="Vai trò"
              value={{
                ADMIN: 'Quản trị viên',
                STAFF: 'Nhân viên',
                STUDENT: 'Sinh viên',
              }[user.role] ?? user.role}
              accent="blue"
            />
            <InfoCard
              icon={
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <rect x="3" y="3" width="14" height="14" rx="3" stroke="currentColor" strokeWidth="1.5"/>
                  <path d="M7 10l2.5 2.5L13 7.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              }
              label="Trạng thái"
              value={user.enabled ? 'Đang hoạt động' : 'Đã khóa'}
              accent={user.enabled ? 'green' : 'red'}
            />
            <InfoCard
              icon={
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M10 2L2 7v6l8 5 8-5V7L10 2z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
                  <path d="M10 2v11M2 7l8 4 8-4" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
                </svg>
              }
              label="Hệ thống"
              value="Student Web v1"
              accent="purple"
            />
          </div>

          <div className="dashboard-note">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M8 7v5M8 5h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            Đây là trang tổng quan. Các tính năng đầy đủ sẽ được bổ sung tiếp theo.
          </div>
        </div>
      </main>
    </>
  );
}

function InfoCard({
  icon, label, value, accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  accent: 'blue' | 'green' | 'red' | 'purple';
}) {
  return (
    <div className={`info-card info-card-${accent}`}>
      <div className="info-icon">{icon}</div>
      <div>
        <p className="info-label">{label}</p>
        <p className="info-value">{value}</p>
      </div>
    </div>
  );
}
