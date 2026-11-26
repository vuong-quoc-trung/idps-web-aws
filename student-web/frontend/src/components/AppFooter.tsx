import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import './AppFooter.css';

export default function AppFooter() {
  const { user } = useAuth();
  return <footer className="dut-footer">
    <div className="dut-footer-inner">
      <div className="dut-footer-main">
        <Link to="/" className="dut-footer-brand" aria-label="DUT - Thông tin sinh viên, về trang chủ">
          <img src="/images/dut-logo.jpg" alt="" width="40" height="40" />
          <strong>DUT - THÔNG TIN SINH VIÊN</strong>
        </Link>
        <nav className="dut-footer-nav" aria-label="Điều hướng cuối trang">
          <Link to="/">Trang chủ</Link>
          {user?.role === 'STUDENT' && <Link to="/profile">Hồ sơ của tôi</Link>}
          <Link to="/catalog">Chương trình &amp; Lớp</Link>
        </nav>
      </div>
      <div className="dut-footer-bottom">
        <span>© {new Date().getFullYear()} · Cổng thông tin sinh viên</span>
      </div>
    </div>
  </footer>;
}
