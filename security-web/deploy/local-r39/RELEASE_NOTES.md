# WebSentinel AI-IDPS 0.1.0-beta.2 · Research Preview

Bản Beta chạy hệ thống Student Web và giám sát AI qua HTTPS loopback trên máy Ubuntu 26.04 amd64 tương thích. Cần quyền quản trị để cài systemd system units. Resource Contract hiện yêu cầu Intel Core Ultra 9 285H với mapping `coretemp` hợp lệ. Guest KVM thiếu cảm biến sẽ bị từ chối ở preflight.

Model mặc định là `r37-hgb-uri100-v1`, với ONNX SHA-256 `91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff` và R36 ExtraTrees làm rollback. Đây là Research/Beta Monitoring. T07 production vẫn BLOCKED và AI automatic ban ở trạng thái OFF. Recall 86,04% và FPR 0,41% là số đo trên WAF development. Khả năng chuyển giao sang Notes và SR-BH còn hạn chế.

Gói phân phối chứa mã ứng dụng Student, phiên bản bất biến của hai model, Rust executables, thư viện ONNX Runtime và notices. Student dùng dependency JAR tải thẳng từ Maven Central theo manifest SHA-256. Suricata dùng cấu hình cơ sở từ gói Ubuntu. Các ảnh trường và tài nguyên thương hiệu chưa xác minh quyền được thay bằng ký hiệu Beta cục bộ.

Xem hướng dẫn cài đặt, yêu cầu TLS và rollback trong `INSTALL.md`. Các điều kiện phát hành và kết quả kiểm thử được ghi trong báo cáo R42 của repository.
