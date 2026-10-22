import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import './AppFooter.css';

// Replace these sample contact values when official support details are available.
const FOOTER_CONTACT = {
  address: '54 Nguyễn Lương Bằng, Phường Liên Chiểu, Thành phố Đà Nẵng',
  phone: '+84 774 155 608',
  email: 'dutstudentsystem@gmail.com',
};

export default function AppFooter() {
  const { user } = useAuth();
  return <footer className="dut-footer">
    <div className="dut-footer-inner">
      <div className="dut-footer-main">
        <Link to="/" className="dut-footer-brand" aria-label="DUT - Thông tin sinh viên, về trang chủ">
          <img src="/images/dut-logo.jpg" alt="" width="40" height="40" />
          <span><strong>DUT - THÔNG TIN SINH VIÊN</strong><span>Kết nối học tập · Đồng hành cùng sinh viên</span></span>
        </Link>
        <nav className="dut-footer-nav" aria-label="Điều hướng cuối trang">
          <Link to="/">Trang chủ</Link>
          {user?.role === 'STUDENT' && <Link to="/profile">Hồ sơ của tôi</Link>}
          <Link to="/catalog">Chương trình &amp; Lớp</Link>
        </nav>
      </div>
      <address className="dut-footer-contact" aria-label="Địa chỉ và liên hệ">
        <div className="dut-footer-contact-address"><span className="dut-footer-contact-label">Địa chỉ trường</span>
          <span>Trường Đại học Bách khoa – Đại học Đà Nẵng</span>
          <span>{FOOTER_CONTACT.address}</span>
        </div>
        <div><span className="dut-footer-contact-label">Điện thoại </span>
          <span>{FOOTER_CONTACT.phone}</span>
        </div>
        <div><span className="dut-footer-contact-label">Email hỗ trợ</span>
          <span>{FOOTER_CONTACT.email}</span>
        </div>
      </address>
      <div className="dut-footer-bottom">
        <span>© {new Date().getFullYear()} · Cổng thông tin sinh viên</span>
        <span className="dut-footer-project">Đồ án PBL4 <span aria-hidden="true">·</span> Phiên bản thử nghiệm</span>
      </div>
    </div>
  </footer>;
}
