/**
 * DashboardPage — Modern Academic Portal Dashboard
 * Tailored for ADMIN/STAFF (metrics, quick actions, recent students)
 * and STUDENT (student card, completion widget, fast services)
 */
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import AppHeader from '../components/AppHeader';
import { studentApi } from '../api/studentApi';
import { facultyApi, majorApi, classApi } from '../api/academicApi';
import { myProfileApi } from '../api/profileApi';
import type { StudentSummary, StudentDetail, CompletionStatus, StudentStatus } from '../types/student';
import './DashboardPage.css';

const ROLE_WELCOME: Record<string, string> = {
  ADMIN: 'Bảng điều khiển Quản trị viên',
  STAFF: 'Bảng điều khiển Học vụ',
  STUDENT: 'Cổng thông tin Sinh viên',
};

const STATUS_LABELS: Record<StudentStatus, string> = {
  ACTIVE: 'Đang học',
  GRADUATED: 'Đã tốt nghiệp',
  SUSPENDED: 'Đình chỉ',
  INACTIVE: 'Ngừng hoạt động',
};

const STATUS_CLASSES: Record<StudentStatus, string> = {
  ACTIVE: 'status-active',
  GRADUATED: 'status-graduated',
  SUSPENDED: 'status-suspended',
  INACTIVE: 'status-inactive',
};

const MISSING_FIELD_LABELS: Record<string, string> = {
  dateOfBirth: 'Ngày sinh',
  gender: 'Giới tính',
  placeOfBirth: 'Nơi sinh',
  oldPlaceOfBirth: 'Quê quán',
  ethnicity: 'Dân tộc',
  nationality: 'Quốc tịch',
  citizenId: 'Số CCCD',
  citizenIdIssueDate: 'Ngày cấp CCCD',
  healthInsuranceNumber: 'Số thẻ BHYT',
  healthInsuranceExpiry: 'Hạn thẻ BHYT',
  trainingProgram: 'Chương trình đào tạo',
  personalEmail: 'Email cá nhân',
  phoneNumber: 'Số điện thoại',
  currentAddress: 'Địa chỉ thường trú',
  permanentOrFamilyAddress: 'Hộ khẩu / Nhà gia đình',
  father: 'Thông tin Bố (họ tên, ngày sinh)',
  mother: 'Thông tin Mẹ (họ tên, ngày sinh)',
  familyMember: 'Nhân thân gia đình',
  emergencyContact: 'Liên hệ khẩn cấp',
};

export default function DashboardPage() {
  const { user } = useAuth();
  const isAdminOrStaff = user?.role === 'ADMIN' || user?.role === 'STAFF';

  // Admin/Staff metrics
  const [stats, setStats] = useState<{
    totalStudents: number;
    activeStudents: number;
    completedStudents: number;
    facultiesCount: number;
    majorsCount: number;
    classesCount: number;
    recentStudents: StudentSummary[];
  } | null>(null);

  // Student metrics
  const [studentDetail, setStudentDetail] = useState<StudentDetail | null>(null);
  const [completion, setCompletion] = useState<CompletionStatus | null>(null);
  const [studentAcademic, setStudentAcademic] = useState<{ className?: string; majorName?: string }>({});

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;

    let isMounted = true;
    setLoading(true);

    if (isAdminOrStaff) {
      Promise.all([
        studentApi.list({ size: 100 }),
        facultyApi.list(0),
        majorApi.list(0),
        classApi.list(0),
      ])
        .then(([stdRes, facRes, majRes, clsRes]) => {
          if (!isMounted) return;
          const students = stdRes.content || [];
          const active = students.filter(s => s.status === 'ACTIVE').length;
          const completed = students.filter(s => s.profileStatus === 'COMPLETE').length;
          setStats({
            totalStudents: stdRes.totalElements || students.length,
            activeStudents: active,
            completedStudents: completed,
            facultiesCount: facRes.totalElements || facRes.content.length,
            majorsCount: majRes.totalElements || majRes.content.length,
            classesCount: clsRes.totalElements || clsRes.content.length,
            recentStudents: students.slice(0, 5),
          });
        })
        .catch(() => {})
        .finally(() => {
          if (isMounted) setLoading(false);
        });
    } else if (user.role === 'STUDENT') {
      Promise.all([
        myProfileApi.getProfile().catch(() => null),
        myProfileApi.getCompletion().catch(() => null),
        classApi.listAll().catch(() => ({ content: [] })),
        majorApi.listAll().catch(() => ({ content: [] })),
      ])
        .then(([sv, comp, clsList, majList]) => {
          if (!isMounted) return;
          setStudentDetail(sv);
          setCompletion(comp);
          if (sv) {
            const cls = clsList.content?.find(c => c.id === sv.classId);
            const maj = majList.content?.find(m => m.id === sv.majorId);
            setStudentAcademic({
              className: cls ? cls.code : sv.classId ? `Lớp #${sv.classId}` : undefined,
              majorName: maj ? maj.name : sv.majorId ? `Ngành #${sv.majorId}` : undefined,
            });
          }
        })
        .catch(() => {})
        .finally(() => {
          if (isMounted) setLoading(false);
        });
    }

    return () => {
      isMounted = false;
    };
  }, [user, isAdminOrStaff]);

  if (!user) return null;

  const initials = (user.fullName ?? user.username)
    .split(' ')
    .map(w => w[0])
    .slice(-2)
    .join('')
    .toUpperCase();

  // Completion calculation for student
  const isComplete =
    completion?.status === 'COMPLETE' ||
    completion?.complete === true ||
    (completion?.missingFields && completion.missingFields.length === 0);
  const missingCount = completion?.missingFields?.length ?? 0;
  const totalFields = 17;
  const displayPct = isComplete ? 100 : Math.max(0, Math.min(99, Math.round(((totalFields - missingCount) / totalFields) * 100)));

  return (
    <>
      <AppHeader />
      <main className="dashboard-main">
        <div className="dashboard-content">
          {/* Welcome Card */}
          <div className="welcome-card">
            <div className="welcome-glow" aria-hidden="true" />
            <div className="welcome-body">
              <div className="welcome-avatar" style={{ position: 'relative', overflow: 'hidden' }}>
                {studentDetail?.avatarUrl ? (
                  <img
                    src={studentDetail.avatarUrl}
                    alt={user.fullName ?? user.username}
                    style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', objectFit: 'cover' }}
                    onError={e => { (e.currentTarget as HTMLElement).style.display = 'none'; }}
                  />
                ) : null}
                <span>{initials}</span>
              </div>
              <div className="welcome-text-wrap">
                <div className="welcome-badge-row">
                  <span className={`dashboard-role-badge role-${user.role.toLowerCase()}`}>
                    {user.role === 'ADMIN' ? 'Quản trị viên hệ thống' : user.role === 'STAFF' ? 'Cán bộ quản lý học vụ' : 'Học viên / Sinh viên'}
                  </span>
                  <span className="dashboard-date-chip">
                    {new Date().toLocaleDateString('vi-VN', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                  </span>
                </div>
                <h1 className="welcome-title">{ROLE_WELCOME[user.role] ?? 'Chào mừng bạn!'}</h1>
                <p className="welcome-subtitle">
                  Xin chào <strong>{user.fullName ?? user.username}</strong>
                  {user.studentCode && <> · Mã số sinh viên: <code className="mono-code">{user.studentCode}</code></>}
                  {studentAcademic.className && <> · Lớp: <strong>{studentAcademic.className}</strong></>}
                  {studentAcademic.majorName && <> · Ngành: <strong>{studentAcademic.majorName}</strong></>}
                  {studentDetail?.status && (
                    <span className={`status-pill ${STATUS_CLASSES[studentDetail.status]}`} style={{ marginLeft: 8 }}>
                      {STATUS_LABELS[studentDetail.status]}
                    </span>
                  )}
                </p>
              </div>
            </div>
          </div>

          {/* ──────────────── ADMIN / STAFF VIEW ──────────────── */}
          {isAdminOrStaff && (
            <>
              {/* KPI Cards */}
              <div className="dashboard-section-header">
                <h2 className="dashboard-section-title">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M18 20V10M12 20V4M6 20v-6" />
                  </svg>
                  Chỉ số học vụ & Hệ thống
                </h2>
              </div>

              <div className="info-grid">
                <MetricCard
                  icon={
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
                      <circle cx="9" cy="7" r="4" />
                      <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" />
                    </svg>
                  }
                  label="Tổng số sinh viên"
                  value={loading ? '...' : (stats?.totalStudents ?? 0).toLocaleString('vi-VN')}
                  subLabel={loading ? undefined : `${stats?.activeStudents ?? 0} đang theo học`}
                  accent="blue"
                />

                <MetricCard
                  icon={
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
                      <path d="M6 12v5c0 3 6 3 6 3s6 0 6-3v-5" />
                    </svg>
                  }
                  label="Khoa đào tạo"
                  value={loading ? '...' : (stats?.facultiesCount ?? 0).toString()}
                  subLabel="Đơn vị quản lý học vụ"
                  accent="purple"
                />

                <MetricCard
                  icon={
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="2" y="3" width="20" height="14" rx="2" />
                      <line x1="8" y1="21" x2="16" y2="21" />
                      <line x1="12" y1="17" x2="12" y2="21" />
                    </svg>
                  }
                  label="Ngành đào tạo"
                  value={loading ? '...' : (stats?.majorsCount ?? 0).toString()}
                  subLabel="Chuyên ngành tuyển sinh"
                  accent="green"
                />

                <MetricCard
                  icon={
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2" />
                      <rect x="8" y="2" width="8" height="4" rx="1" />
                      <path d="M9 14l2 2 4-4" />
                    </svg>
                  }
                  label="Lớp học sinh viên"
                  value={loading ? '...' : (stats?.classesCount ?? 0).toString()}
                  subLabel="Lớp học đang quản lý"
                  accent="orange"
                />
              </div>

              {/* Quick Actions Bar */}
              <div className="dashboard-section-header" style={{ marginTop: 'var(--space-4)' }}>
                <h2 className="dashboard-section-title">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                  </svg>
                  Lối tắt tác vụ nhanh
                </h2>
              </div>

              <div className="quick-action-grid">
                <Link to="/students" className="quick-action-card">
                  <div className="quick-action-icon action-blue">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
                      <circle cx="8.5" cy="7" r="4" />
                      <line x1="20" y1="8" x2="20" y2="14" />
                      <line x1="23" y1="11" x2="17" y2="11" />
                    </svg>
                  </div>
                  <div className="quick-action-content">
                    <h3 className="quick-action-title">Quản lý hồ sơ sinh viên</h3>
                    <p className="quick-action-desc">Tra cứu, thêm mới, xem mức độ hoàn thiện hồ sơ sinh viên</p>
                  </div>
                </Link>

                <Link to="/catalog" className="quick-action-card">
                  <div className="quick-action-icon action-green">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
                      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
                    </svg>
                  </div>
                  <div className="quick-action-content">
                    <h3 className="quick-action-title">Danh mục học vụ</h3>
                    <p className="quick-action-desc">Cấu hình Khoa, Ngành học, Chương trình đào tạo và các Lớp sinh viên</p>
                  </div>
                </Link>

                {user.role === 'ADMIN' && (
                  <>
                    <Link to="/admin" className="quick-action-card">
                      <div className="quick-action-icon action-purple">
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <circle cx="12" cy="12" r="3" />
                          <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z" />
                        </svg>
                      </div>
                      <div className="quick-action-content">
                        <h3 className="quick-action-title">Tài khoản & Phân quyền</h3>
                        <p className="quick-action-desc">Tạo tài khoản cán bộ, khóa tài khoản và cấp lại mã kích hoạt</p>
                      </div>
                    </Link>

                    <Link to="/admin?tab=logs" className="quick-action-card">
                      <div className="quick-action-icon action-orange">
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M12 2L3 6v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V6l-9-4z" />
                          <path d="M9 12l2 2 4-4" />
                        </svg>
                      </div>
                      <div className="quick-action-content">
                        <h3 className="quick-action-title">Nhật ký truy cập hệ thống</h3>
                        <p className="quick-action-desc">Giám sát các thao tác gọi API, địa chỉ IP và mã trạng thái HTTP</p>
                      </div>
                    </Link>
                  </>
                )}
              </div>

              {/* Recent Students Card */}
              {stats?.recentStudents && stats.recentStudents.length > 0 && (
                <div className="dashboard-table-card">
                  <div className="dashboard-table-header">
                    <div>
                      <h3 className="dashboard-table-title">Sinh viên mới cập nhật</h3>
                      <p className="dashboard-table-desc">Danh sách sinh viên vừa được ghi nhận trong hệ thống</p>
                    </div>
                    <Link to="/students" className="btn-table-more">
                      Xem tất cả →
                    </Link>
                  </div>

                  <div className="dashboard-table-wrap">
                    <table className="dashboard-data-table">
                      <thead>
                        <tr>
                          <th>MSSV</th>
                          <th>Họ và tên</th>
                          <th>Email</th>
                          <th>Trạng thái</th>
                          <th style={{ textAlign: 'right' }}>Thao tác</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stats.recentStudents.map(sv => (
                          <tr key={sv.id}>
                            <td className="mono-text">{sv.studentCode}</td>
                            <td className="name-cell">
                              <strong>{sv.fullName}</strong>
                            </td>
                            <td>{sv.schoolEmail ?? '—'}</td>
                            <td>
                              <span className={`status-pill ${STATUS_CLASSES[sv.status]}`}>
                                {STATUS_LABELS[sv.status]}
                              </span>
                            </td>
                            <td style={{ textAlign: 'right' }}>
                              <Link to={`/students/${sv.id}`} className="btn-view-detail">
                                Chi tiết
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}

          {/* ──────────────── STUDENT VIEW ──────────────── */}
          {!isAdminOrStaff && (
            <>
              {/* Profile Completion Widget */}
              <div className="dashboard-completion-card">
                <div className="completion-card-header">
                  <div className="completion-card-left">
                    <div className="completion-status-icon">
                      {isComplete ? (
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--clr-success-500)" strokeWidth="2.5">
                          <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
                          <polyline points="22 4 12 14.01 9 11.01" />
                        </svg>
                      ) : (
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2">
                          <circle cx="12" cy="12" r="10" />
                          <line x1="12" y1="8" x2="12" y2="12" />
                          <line x1="12" y1="16" x2="12.01" y2="16" />
                        </svg>
                      )}
                    </div>
                    <div>
                      <h2 className="completion-card-title">Tiến độ hoàn thiện hồ sơ sinh viên</h2>
                      <p className="completion-card-desc">
                        {isComplete
                          ? 'Chúc mừng! Bạn đã hoàn thành 100% việc kê khai thông tin hồ sơ theo quy định của nhà trường.'
                          : `Hồ sơ của bạn còn thiếu ${missingCount} mục thông tin bắt buộc. Vui lòng bổ sung để đảm bảo quyền lợi học vụ.`}
                      </p>
                    </div>
                  </div>
                  <div className="completion-card-right">
                    <span className={`completion-percentage-badge ${isComplete ? 'complete' : ''}`}>
                      {displayPct}%
                    </span>
                    <Link to="/profile" className="btn-complete-profile">
                      {isComplete ? 'Xem lại hồ sơ' : 'Cập nhật ngay →'}
                    </Link>
                  </div>
                </div>

                <div className="completion-progress-track">
                  <div
                    className={`completion-progress-fill ${isComplete ? 'complete' : ''}`}
                    style={{ width: `${displayPct}%` }}
                  />
                </div>

                {missingCount > 0 && completion?.missingFields && (
                  <div className="completion-missing-box">
                    <span className="missing-box-label">Các mục cần bổ sung:</span>
                    <div className="missing-tags-flow">
                      {completion.missingFields.map(f => (
                        <span key={f} className="missing-field-tag" title={f}>
                          <span className="dot-warn" />
                          {MISSING_FIELD_LABELS[f] ?? f}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Student Quick Access Grid */}
              <div className="dashboard-section-header">
                <h2 className="dashboard-section-title">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="3" width="7" height="7" />
                    <rect x="14" y="3" width="7" height="7" />
                    <rect x="14" y="14" width="7" height="7" />
                    <rect x="3" y="14" width="7" height="7" />
                  </svg>
                  Dịch vụ & Hồ sơ cá nhân
                </h2>
              </div>

              <div className="student-service-grid">
                <Link to="/profile" className="student-service-card">
                  <div className="service-card-icon service-blue">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
                      <circle cx="12" cy="7" r="4" />
                    </svg>
                  </div>
                  <h3>Thông tin cá nhân & Nhân khẩu</h3>
                  <p>Kê khai nơi sinh, quê quán, dân tộc, tôn giáo, thông tin thẻ BHYT và CCCD gắn chip</p>
                  <span className="service-arrow">Truy cập →</span>
                </Link>

                <Link to="/profile" className="student-service-card">
                  <div className="service-card-icon service-green">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
                      <circle cx="12" cy="10" r="3" />
                    </svg>
                  </div>
                  <h3>Địa chỉ cư trú</h3>
                  <p>Cập nhật địa chỉ thường trú, hộ khẩu gia đình và nơi ở trọ hiện tại phục vụ quản lý</p>
                  <span className="service-arrow">Truy cập →</span>
                </Link>

                <Link to="/profile" className="student-service-card">
                  <div className="service-card-icon service-purple">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
                      <circle cx="9" cy="7" r="4" />
                      <path d="M23 21v-2a4 4 0 00-3-3.87" />
                      <path d="M16 3.13a4 4 0 010 7.75" />
                    </svg>
                  </div>
                  <h3>Nhân thân & Khẩn cấp</h3>
                  <p>Khai báo thông tin người thân trong gia đình và số điện thoại liên hệ khi có sự cố</p>
                  <span className="service-arrow">Truy cập →</span>
                </Link>

                <Link to="/catalog" className="student-service-card">
                  <div className="service-card-icon service-orange">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
                      <path d="M6 12v5c0 3 6 3 6 3s6 0 6-3v-5" />
                    </svg>
                  </div>
                  <h3>Chương trình đào tạo & Ngành</h3>
                  <p>Tra cứu danh mục khoa, ngành đào tạo, tổng số tín chỉ và thông tin lớp học</p>
                  <span className="service-arrow">Truy cập →</span>
                </Link>
              </div>

              {/* Notice Card */}
              <div className="dashboard-notice-card">
                <div className="notice-icon">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--clr-warning-400)" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                </div>
                <div className="notice-content">
                  <h4 className="notice-title">Lưu ý quan trọng về thông tin hồ sơ</h4>
                  <p className="notice-text">
                    Sinh viên cần hoàn thiện đầy đủ các mục thông tin trước khi bắt đầu học kỳ mới. Các thông tin về CCCD và BHYT cần đối chiếu chính xác với giấy tờ gốc để đảm bảo quyền lợi bảo hiểm y tế và cấp bằng tốt nghiệp sau này.
                  </p>
                </div>
              </div>
            </>
          )}
        </div>
      </main>
    </>
  );
}

function MetricCard({
  icon,
  label,
  value,
  subLabel,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  subLabel?: string;
  accent: 'blue' | 'green' | 'purple' | 'orange';
}) {
  return (
    <div className={`metric-card metric-card-${accent}`}>
      <div className="metric-icon">{icon}</div>
      <div className="metric-info">
        <p className="metric-label">{label}</p>
        <p className="metric-value">{value}</p>
        {subLabel && <p className="metric-sublabel">{subLabel}</p>}
      </div>
    </div>
  );
}
