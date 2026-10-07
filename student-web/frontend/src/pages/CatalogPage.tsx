/**
 * CatalogPage — Academic catalog management
 * Tabs: Khoa | Ngành | Chương trình đào tạo | Lớp
 * Access: ADMIN + STAFF only (ProtectedRoute handles this)
 */
import { useState, lazy, Suspense, type JSX } from 'react';
import AppHeader from '../components/AppHeader';
import './CatalogPage.css';

const FacultyTab = lazy(() => import('../components/catalog/FacultyTab'));
const MajorTab   = lazy(() => import('../components/catalog/MajorTab'));
const ProgramTab = lazy(() => import('../components/catalog/ProgramTab'));
const ClassTab   = lazy(() => import('../components/catalog/ClassTab'));

type TabId = 'faculty' | 'major' | 'program' | 'class';

interface TabConfig {
  id: TabId;
  label: string;
  title: string;
  description: string;
  icon: JSX.Element;
}

const TABS: TabConfig[] = [
  {
    id: 'faculty',
    label: 'Khoa',
    title: 'Quản lý Khoa',
    description: 'Danh sách các khoa trong trường. Khoa là đơn vị quản lý các ngành đào tạo.',
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <rect x="1" y="7" width="14" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.35"/>
        <path d="M5 7V5a3 3 0 016 0v2" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round"/>
        <path d="M8 1v2" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round"/>
        <circle cx="8" cy="11" r="1.5" fill="currentColor"/>
      </svg>
    ),
  },
  {
    id: 'major',
    label: 'Ngành',
    title: 'Quản lý Ngành',
    description: 'Danh sách ngành học thuộc các khoa. Mỗi ngành có thể có nhiều chương trình đào tạo.',
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <path d="M2 4h12M2 8h8M2 12h10" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    id: 'program',
    label: 'Chương trình ĐT',
    title: 'Quản lý Chương trình đào tạo',
    description: 'Chương trình đào tạo xác định bằng cấp, số tín chỉ, số học kỳ cho mỗi ngành.',
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <rect x="2" y="2" width="12" height="12" rx="2" stroke="currentColor" strokeWidth="1.35"/>
        <path d="M5 6h6M5 9h4" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    id: 'class',
    label: 'Lớp',
    title: 'Quản lý Lớp',
    description: 'Danh sách các lớp sinh viên. Mỗi lớp gắn với một chương trình đào tạo và khoá nhập học.',
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <circle cx="5" cy="5" r="2" stroke="currentColor" strokeWidth="1.35"/>
        <circle cx="11" cy="5" r="2" stroke="currentColor" strokeWidth="1.35"/>
        <path d="M1 13c0-2.21 1.79-4 4-4M15 13c0-2.21-1.79-4-4-4" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round"/>
        <path d="M6.5 13c0-1.38 1.12-2.5 2.5-2.5" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round"/>
      </svg>
    ),
  },
];

function TabSpinner() {
  return (
    <div style={{ padding: '48px', textAlign: 'center', color: 'var(--text-muted)' }}>
      <span className="spinner" style={{ margin: '0 auto', display: 'block', width: 20, height: 20, borderWidth: 2 }} />
    </div>
  );
}

export default function CatalogPage() {
  const [activeTab, setActiveTab] = useState<TabId>('faculty');
  const tab = TABS.find(t => t.id === activeTab)!;

  return (
    <div className="catalog-page">
      <AppHeader />

      <div className="catalog-inner">
        {/* Page heading */}
        <div className="resource-header">
          <div className="resource-title">
            <h1>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" style={{ verticalAlign: 'middle', marginRight: 8 }}>
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" stroke="currentColor" strokeWidth="1.75"/>
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" stroke="currentColor" strokeWidth="1.75"/>
              </svg>
              Quản lý danh mục học vụ
            </h1>
            <p>{tab.description}</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="catalog-tabs" role="tablist" aria-label="Danh mục học vụ">
          {TABS.map(t => (
            <button
              key={t.id}
              id={`catalog-tab-${t.id}`}
              className={`catalog-tab${activeTab === t.id ? ' active' : ''}`}
              role="tab"
              aria-selected={activeTab === t.id}
              aria-controls="catalog-tabpanel"
              onClick={() => setActiveTab(t.id)}
            >
              <span className="tab-icon">{t.icon}</span>
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div id="catalog-tabpanel" className="resource-section" role="tabpanel" aria-labelledby={`catalog-tab-${activeTab}`}>
          <div className="resource-header">
            <div className="resource-title">
              <h2>{tab.title}</h2>
            </div>
          </div>

          <Suspense fallback={<TabSpinner />}>
            {activeTab === 'faculty'  && <FacultyTab />}
            {activeTab === 'major'    && <MajorTab />}
            {activeTab === 'program'  && <ProgramTab />}
            {activeTab === 'class'    && <ClassTab />}
          </Suspense>
        </div>
      </div>
    </div>
  );
}
