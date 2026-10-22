import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import AppFooter from './components/AppFooter';
import ProtectedRoute from './components/ProtectedRoute';
import PasswordPage from './pages/PasswordPage';
import LoginPage          from './pages/LoginPage';
import ActivatePage       from './pages/ActivatePage';
import DashboardPage      from './pages/DashboardPage';
import CatalogPage        from './pages/CatalogPage';
import StudentsPage       from './pages/StudentsPage';
import StudentDetailPage  from './pages/students/StudentDetailPage';
import ProfilePage        from './pages/ProfilePage';
import UsersPage          from './pages/UsersPage';

function PortalLayout() {
  return <><Outlet /><AppFooter /></>;
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <Routes>
            {/* Public routes */}
            <Route path="/forgot-password" element={<PasswordPage mode="forgot" />} />
            <Route path="/login"    element={<LoginPage />} />
            <Route path="/activate" element={<ActivatePage />} />

            <Route element={<PortalLayout />}>
            {/* All authenticated users */}
            <Route element={<ProtectedRoute />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/change-password" element={<PasswordPage mode="change" />} />
              <Route path="/catalog" element={<CatalogPage />} />
            </Route>

            {/* Admin and Staff only */}
            <Route element={<ProtectedRoute allowedRoles={['ADMIN', 'STAFF']} />}>
              <Route path="/students" element={<StudentsPage />} />
              <Route path="/students/:id" element={<StudentDetailPage />} />
            </Route>

            {/* Student only */}
            <Route element={<ProtectedRoute allowedRoles={['STUDENT']} />}>
              <Route path="/profile" element={<ProfilePage />} />
            </Route>

            {/* Admin only */}
            <Route element={<ProtectedRoute allowedRoles={['ADMIN']} />}>
              <Route path="/admin" element={<UsersPage />} />
            </Route>

            </Route>

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
