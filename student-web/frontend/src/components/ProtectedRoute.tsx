/* ============================================================
   ProtectedRoute — redirects to /login if not authenticated
   ============================================================ */
import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

interface Props {
  /** If true, require specific roles */
  allowedRoles?: Array<'ADMIN' | 'STAFF' | 'STUDENT'>;
}

export default function ProtectedRoute({ allowedRoles }: Props) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="page-loading" role="status" aria-label="Đang tải…">
        <div className="page-loading-inner">
          <span className="spinner" style={{ width: 24, height: 24, borderWidth: 2.5 }} />
          <p>Đang tải…</p>
        </div>
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
