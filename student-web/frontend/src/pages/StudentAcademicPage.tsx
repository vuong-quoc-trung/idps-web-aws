import { useEffect, useState } from 'react';
import Modal from '../components/Modal';
import AppHeader from '../components/AppHeader';
import { apiGet } from '../api/client';
import './StudentAcademicPage.css';

type Item = { code: string; name: string | null };
type Academic = { faculty: Item; major: Item; program: Item; secondaryProgram: Item | null; studentClass: Item; cohort: number | null };
type Members = { content: { studentCode: string; fullName: string; self: boolean }[]; totalElements: number; totalPages: number };

function AcademicIcon({ kind = 0 }: { kind?: number }) {
  const paths = [
    'M3 21h18M5 21V7l7-4 7 4v14M9 21v-5h6v5M8 9h1m6 0h1M8 12h1m6 0h1',
    'M12 3v6m-7 6v-3h14v3M3 16h4v5H3zm7 0h4v5h-4zm7 0h4v5h-4z',
    'M12 6c-3-2-6-2-9-1v14c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1zm0 0v14',
    'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8m8-7.87a4 4 0 0 1 0 7.75',
  ];
  return <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[kind % paths.length]} /></svg>;
}

export default function StudentAcademicPage() {
  const [academic, setAcademic] = useState<Academic | null>(null);
  const [showMembers, setShowMembers] = useState(false);
  const [retry, setRetry] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    apiGet<Academic>('/me/academic').then(info => {
      if (active) setAcademic(info);
    }).catch(() => {
      if (active) setError('Không tải được thông tin học vụ. Vui lòng thử lại.');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [retry]);
  function reload() {
    setLoading(true); setError(''); setRetry(value => value + 1);
  }
  const cards: [string, Item | null | undefined][] = [
    ['Khoa', academic?.faculty], ['Ngành', academic?.major],
    ['Chương trình đào tạo', academic?.program], ['Lớp của tôi', academic?.studentClass],
    ...(academic?.secondaryProgram ? [['Chương trình thứ hai', academic.secondaryProgram] as [string, Item]] : []),
  ];
  return <>
    <AppHeader />
    <main className="student-academic">
      <header className="academic-hero">
        <div className="academic-hero-copy"><span className="academic-eyebrow"><AcademicIcon kind={2} /> GÓC HỌC VỤ</span>
          <h1>Chương trình &amp; Lớp của tôi</h1>
          <p>Hành trình học tập của bạn, cùng những người bạn đồng hành.</p>
          <button type="button" className="academic-roster-link" aria-haspopup="dialog" disabled={!academic || loading || !!error} onClick={() => setShowMembers(true)}>Xem thành viên lớp <AcademicIcon kind={3} /></button>
        </div>
        {academic && <div className="academic-cohort"><span>KHÓA NHẬP HỌC</span><strong>{academic.cohort ?? '—'}</strong><span>{academic.studentClass.code}</span></div>}
      </header>
      {loading ? <div className="academic-feedback" role="status"><AcademicIcon kind={2} /><p>Đang tải thông tin học vụ…</p></div> : error ?
        <div className="academic-feedback" role="alert"><p>{error}</p><button onClick={reload}>Thử lại</button></div> :
        <>
          <section className="student-academic-grid" aria-label="Thông tin học vụ">
            {cards.map(([label, item], index) => <article key={label} className={index === 3 ? 'academic-card academic-card-class' : 'academic-card'}>
              <div className="academic-card-heading"><span className="academic-card-icon"><AcademicIcon kind={index} /></span><h2>{label}</h2><span className="academic-card-step">0{index + 1}</span></div>
              <p>{item?.name || 'Chưa có tên'}</p><code>{item?.code}</code>
            </article>)}
          </section>

        </>}
      <Modal open={showMembers} title="Thành viên lớp" size="lg" onClose={() => setShowMembers(false)}>
        {showMembers && academic && <ClassMembers className={academic.studentClass.name || academic.studentClass.code} />}
      </Modal>
    </main>
  </>;
}

function ClassMembers({ className }: { className: string }) {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [members, setMembers] = useState<Members | null>(null);
  const [page, setPage] = useState(0);
  const [retry, setRetry] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    apiGet<Members>(`/me/academic/classmates?page=${page}&size=20&search=${encodeURIComponent(query)}`).then(list => {
      if (active) setMembers(list);
    }).catch(() => {
      if (active) setError('Không tải được danh sách thành viên. Vui lòng thử lại.');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [page, retry, query]);
  function reload(nextPage: number) {
    setLoading(true); setError(''); setPage(nextPage); setRetry(value => value + 1);
  }

  if (loading) return <div className="academic-feedback" role="status">Đang tải danh sách thành viên…</div>;
  if (error) return <div className="academic-feedback" role="alert"><p>{error}</p><button onClick={() => reload(page)}>Thử lại</button></div>;
  return (
          <section className="student-classmates" >
            <div className="classmates-heading"><div className="classmates-heading-copy"><span className="academic-card-icon"><AcademicIcon kind={3} /></span><div><h2>Những người bạn cùng lớp</h2>
            <p>{className}</p></div></div>
            <span className="classmates-count"><strong>{members?.totalElements ?? 0}</strong> sinh viên</span></div>
            <form className="classmates-search" onSubmit={event => { event.preventDefault(); setLoading(true); setError(''); setPage(0); setQuery(search.trim()); setRetry(value => value + 1); }}>
              <label htmlFor="class-search">Tìm trong toàn bộ lớp</label>
              <input id="class-search" value={search} maxLength={120} onChange={event => setSearch(event.target.value)} placeholder="Họ tên hoặc mã số sinh viên…" />
              <button type="submit">Tìm kiếm</button>
            </form>
            <div className="student-classmates-table"><table>
              <thead><tr><th scope="col">STT</th><th scope="col">Mã số sinh viên</th><th scope="col">Họ và tên</th></tr></thead>
              <tbody>{members?.content.map((member, index) => <tr key={member.studentCode} className={member.self ? 'classmate-current' : undefined}>
                <td>{page * 20 + index + 1}</td><td><code>{member.studentCode}</code></td>
                <td><div className="classmate-person"><span className="classmate-avatar" aria-hidden="true">{member.fullName.trim().split(/\s+/).slice(-2).map(part => part[0]).join('')}</span><span>{member.fullName}</span> {member.self && <strong className="classmate-self">Bạn</strong>}</div></td>
              </tr>)}</tbody>
            </table></div>
            {!members?.content.length && <p>Không tìm thấy thành viên phù hợp.</p>}
            <nav className="student-classmates-pagination" aria-label="Phân trang thành viên">
              <button disabled={page === 0} onClick={() => reload(page - 1)}>Trang trước</button>
              <span>Trang {page + 1} / {Math.max(1, members?.totalPages ?? 0)}</span>
              <button disabled={page + 1 >= (members?.totalPages ?? 0)} onClick={() => reload(page + 1)}>Trang sau</button>
            </nav>
          </section>
  );
}
