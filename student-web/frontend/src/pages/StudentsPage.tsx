/**
 * StudentsPage — danh sách sinh viên với search/filter/pagination
 * ADMIN và STAFF có thể xem + quản lý
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import AppHeader from '../components/AppHeader';
import Modal from '../components/Modal';
import CreateStudentModal from '../components/students/CreateStudentModal';
import EditStudentModal from '../components/students/EditStudentModal';
import { studentApi } from '../api/studentApi';
import { majorApi, classApi } from '../api/academicApi';
import { ApiError } from '../api/client';
import type { StudentSummary, StudentStatus, StudentDetail, StudentListParams } from '../types/student';
import type { Major, StudentClass } from '../types/academic';
import type { Page } from '../api/client';
import './StudentsPage.css';

const STATUS_LABELS: Record<StudentStatus, string> = {
  ACTIVE: '● Đang học',
  GRADUATED: '🎓 Tốt nghiệp',
  SUSPENDED: '⏸ Đình chỉ',
  INACTIVE: '✕ Ngừng',
};

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debouncedValue;
}

export default function StudentsPage() {
  const navigate = useNavigate();

  // ---- List state ----
  const [data, setData]           = useState<Page<StudentSummary> | null>(null);
  const [page, setPage]           = useState(0);
  const [loading, setLoading]     = useState(false);
  const [tableErr, setTableErr]   = useState<string | null>(null);

  // ---- Filters ----
  const [search, setSearch]       = useState('');
  const [majorId, setMajorId]     = useState<number | ''>('');
  const [classId, setClassId]     = useState<number | ''>('');
  const [status, setStatus]       = useState<StudentStatus | ''>('');
  const [profileStatus, setProfileStatus] = useState<string>('');

  const debouncedSearch = useDebounce(search, 400);

  // ---- Filter options ----
  const [majors, setMajors]       = useState<Major[]>([]);
  const [classes, setClasses]     = useState<StudentClass[]>([]);

  // Lookup maps: id → name (derived from loaded arrays)
  const majorMap  = Object.fromEntries(majors.map(m  => [m.id,  m.name]));
  const classMap  = Object.fromEntries(classes.map(c => [c.id,  c.code]));

  // ---- Modals ----
  const [showCreate, setShowCreate] = useState(false);
  const [editStudent, setEditStudent] = useState<StudentDetail | null>(null);
  const [deactivateTarget, setDeactivateTarget] = useState<StudentSummary | null>(null);
  const [deactivating, setDeactivating] = useState(false);
  const [deactivateErr, setDeactivateErr] = useState<string | null>(null);

  // Load filter options + lookup data ONCE on mount
  useEffect(() => {
    Promise.all([
      majorApi.listAll(),
      classApi.listAll(),
    ]).then(([majRes, clsRes]) => {
      setMajors(majRes.content);
      setClasses(clsRes.content);
    }).catch(() => {});
  }, []);

  const load = useCallback(async (p: number, params: StudentListParams) => {
    setLoading(true); setTableErr(null);
    try { setData(await studentApi.list({ ...params, page: p })); }
    catch (e) { setTableErr(e instanceof Error ? e.message : 'Lỗi tải danh sách'); }
    finally { setLoading(false); }
  }, []);

  // Reset to page 0 when filters change
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) { isFirstRender.current = false; return; }
    setPage(0);
  }, [debouncedSearch, majorId, classId, status]);

  useEffect(() => {
    load(page, { search: debouncedSearch || undefined, majorId: majorId || undefined, classId: classId || undefined, status: status || undefined });
  }, [page, debouncedSearch, majorId, classId, status, load]);

  async function openEdit(sv: StudentSummary) {
    try {
      const detail = await studentApi.get(sv.id);
      setEditStudent(detail);
    } catch { /* ignore */ }
  }

  async function handleDeactivate() {
    if (!deactivateTarget) return;
    setDeactivating(true); setDeactivateErr(null);
    try {
      await studentApi.deactivate(deactivateTarget.id);
      setDeactivateTarget(null);
      load(page, { search: debouncedSearch || undefined, majorId: majorId || undefined, classId: classId || undefined, status: status || undefined });
    } catch (e) {
      setDeactivateErr(e instanceof ApiError && e.status === 409
        ? 'Không thể ngừng hoạt động: sinh viên đang trong trạng thái không cho phép'
        : e instanceof Error ? e.message : 'Lỗi ngừng hoạt động');
    } finally { setDeactivating(false); }
  }

  function clearFilters() {
    setSearch(''); setMajorId(''); setClassId(''); setStatus(''); setProfileStatus('');
  }

  const hasFilters = !!search || !!majorId || !!classId || !!status || !!profileStatus;

  // Filter content by profileStatus if selected
  const displayedStudents = useMemo(() => {
    const list = data?.content ?? [];
    if (!profileStatus) return list;
    return list.filter(sv => sv.profileStatus === profileStatus);
  }, [data, profileStatus]);

  // Stats from current page data (rough counts from pagination)
  const totalElements = data?.totalElements ?? 0;

  const pagesArr = data ? Array.from({ length: Math.min(data.totalPages, 7) }, (_, i) => {
    if (data.totalPages <= 7) return i;
    if (page < 4) return i;
    if (page > data.totalPages - 4) return data.totalPages - 7 + i;
    return page - 3 + i;
  }) : [];

  return (
    <div className="students-page">
      <AppHeader />

      <div className="students-inner">
        {/* Header */}
        <div className="students-header">
          <div className="students-title">
            <h2>👨‍🎓 Quản lý sinh viên</h2>
            <p>Tìm kiếm, thêm mới, cập nhật và quản lý trạng thái sinh viên</p>
          </div>
          <button className="btn-add" id="btn-add-student" onClick={() => setShowCreate(true)}>
            <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
              <path d="M7 1v12M1 7h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            Thêm sinh viên
          </button>
        </div>

        {/* Filter bar */}
        <div className="filter-bar">
          <div className="search-box">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M11 11l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            <input className="search-input" id="sv-search" placeholder="Tìm MSSV hoặc họ tên…"
              value={search} onChange={e => setSearch(e.target.value)} />
          </div>
          <select className="filter-select" id="sv-filter-major" value={majorId}
            onChange={e => { setMajorId(e.target.value ? Number(e.target.value) : ''); setClassId(''); }}>
            <option value="">Tất cả ngành</option>
            {majors.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
          <select className="filter-select" id="sv-filter-class" value={classId}
            onChange={e => setClassId(e.target.value ? Number(e.target.value) : '')}>
            <option value="">Tất cả lớp</option>
            {classes.map(c => <option key={c.id} value={c.id}>{c.code}</option>)}
          </select>
          <select className="filter-select" id="sv-filter-status" value={status}
            onChange={e => setStatus(e.target.value as StudentStatus | '')}>
            <option value="">Tất cả trạng thái</option>
            <option value="ACTIVE">Đang học</option>
            <option value="GRADUATED">Tốt nghiệp</option>
            <option value="SUSPENDED">Đình chỉ</option>
            <option value="INACTIVE">Ngừng HĐ</option>
          </select>
          <select className="filter-select" id="sv-filter-profile-status" value={profileStatus}
            onChange={e => setProfileStatus(e.target.value)}>
            <option value="">Tất cả tiến độ hồ sơ</option>
            <option value="COMPLETE">Đã hoàn thiện</option>
            <option value="INCOMPLETE">Chưa hoàn thiện</option>
          </select>
          {hasFilters && (
            <button className="filter-clear" onClick={clearFilters}>✕ Xóa bộ lọc</button>
          )}
        </div>

        {/* Error */}
        {tableErr && (
          <div className="section-error" style={{ fontSize: 'var(--text-sm)' }} role="alert">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/><path d="M8 4.5v4M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
            {tableErr}
          </div>
        )}

        {/* Table */}
        <div className="students-table-wrap">
          <table className="students-table">
            <thead>
              <tr>
                <th style={{ width: 50 }}>ID</th>
                <th>Sinh viên</th>
                <th>Lớp</th>
                <th>Ngành</th>
                <th>Email trường</th>
                <th style={{ width: 130 }}>Hồ sơ</th>
                <th style={{ width: 120 }}>Trạng thái</th>
                <th style={{ width: 90 }}>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8}>
                  <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                    <span className="spinner" style={{ margin: '0 auto', display: 'block', width: 20, height: 20, borderWidth: 2 }} />
                  </div>
                </td></tr>
              ) : displayedStudents.length === 0 ? (
                <tr><td colSpan={8}>
                  <div style={{ padding: '48px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
                    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" style={{ margin: '0 auto 12px', display: 'block' }}>
                      <circle cx="14" cy="14" r="9" stroke="currentColor" strokeWidth="1.5"/>
                      <path d="M21 21l6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                      <path d="M11 14h6M14 11v6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                    </svg>
                    {hasFilters ? 'Không tìm thấy sinh viên phù hợp bộ lọc.' : 'Chưa có sinh viên nào.'}
                  </div>
                </td></tr>
              ) : displayedStudents.map(sv => (
                <tr key={sv.id} onClick={() => navigate(`/students/${sv.id}`)}>
                  <td data-label="ID" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>{sv.id}</td>
                  <td data-label="Sinh viên">
                    <div className="sv-identity">
                      <span className="sv-name">{sv.fullName}</span>
                      <span className="sv-code">{sv.studentCode}</span>
                    </div>
                  </td>
                  <td data-label="Lớp" style={{ fontSize: 'var(--text-sm)' }}>{sv.classId ? (classMap[sv.classId] ?? `Lớp #${sv.classId}`) : '—'}</td>
                  <td data-label="Ngành" style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)' }}>{sv.majorId ? (majorMap[sv.majorId] ?? `Ngành #${sv.majorId}`) : '—'}</td>
                  <td data-label="Email" style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{sv.schoolEmail ?? '—'}</td>
                  <td data-label="Hồ sơ">
                    <span className={`profile-badge ${sv.profileStatus === 'COMPLETE' ? 'complete' : 'incomplete'}`}>
                      {sv.profileStatus === 'COMPLETE' ? '✓ Hoàn thiện' : '⚠ Chưa xong'}
                    </span>
                  </td>
                  <td data-label="Trạng thái">
                    <span className={`status-badge status-${sv.status}`}>{STATUS_LABELS[sv.status]}</span>
                  </td>
                  <td data-label="Thao tác" onClick={e => e.stopPropagation()}>
                    <div className="sv-actions">
                      <button className="sv-action-btn" id={`edit-sv-${sv.id}`} title="Chỉnh sửa" onClick={e => { e.stopPropagation(); openEdit(sv); }}>
                        <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><path d="M9.5 2.5L11.5 4.5L5 11H3V9L9.5 2.5z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/></svg>
                      </button>
                      <button className="sv-action-btn danger" id={`deactivate-sv-${sv.id}`} title="Ngừng hoạt động" onClick={e => { e.stopPropagation(); setDeactivateTarget(sv); }}>
                        <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.25"/><path d="M5 9l4-4M9 9L5 5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/></svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination */}
          {data && data.totalPages > 1 && (
            <div className="sv-pagination">
              <span className="sv-page-info">Tổng <strong>{totalElements}</strong> sinh viên</span>
              <div className="sv-page-controls">
                <button className="sv-page-btn" onClick={() => setPage(p => p - 1)} disabled={page === 0}>
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M8 2L4 6l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </button>
                {pagesArr.map(p => (
                  <button key={p} className={`sv-page-btn ${p === page ? 'active' : ''}`} onClick={() => setPage(p)}>{p + 1}</button>
                ))}
                <button className="sv-page-btn" onClick={() => setPage(p => p + 1)} disabled={page >= (data?.totalPages ?? 1) - 1}>
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      <CreateStudentModal open={showCreate} onClose={() => setShowCreate(false)}
        onCreated={() => load(page, { search: debouncedSearch || undefined, majorId: majorId || undefined, classId: classId || undefined, status: status || undefined })} />

      <EditStudentModal open={!!editStudent} student={editStudent} onClose={() => setEditStudent(null)}
        onUpdated={() => load(page, { search: debouncedSearch || undefined, majorId: majorId || undefined, classId: classId || undefined, status: status || undefined })} />

      {/* Deactivate confirm */}
      <Modal open={!!deactivateTarget} title="Ngừng hoạt động sinh viên" size="sm"
        onClose={() => { setDeactivateTarget(null); setDeactivateErr(null); }}
        footer={<>
          <button className="btn-cancel" onClick={() => { setDeactivateTarget(null); setDeactivateErr(null); }} disabled={deactivating}>Hủy</button>
          <button className="btn-danger" onClick={handleDeactivate} disabled={deactivating}>
            {deactivating && <span className="spinner spinner-sm" />} Ngừng hoạt động
          </button>
        </>}
      >
        <div className="deactivate-confirm">
          <div className="deactivate-icon">⚠️</div>
          <h3>Ngừng hoạt động?</h3>
          <p>Sinh viên <strong>{deactivateTarget?.fullName}</strong> ({deactivateTarget?.studentCode}) sẽ bị đặt trạng thái <strong>INACTIVE</strong>, tài khoản sẽ bị khóa. Hồ sơ và dữ liệu được giữ nguyên.</p>
          {deactivateErr && (
            <div className="form-alert" style={{ textAlign: 'left', width: '100%' }}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/><path d="M8 4.5v4M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
              {deactivateErr}
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}
