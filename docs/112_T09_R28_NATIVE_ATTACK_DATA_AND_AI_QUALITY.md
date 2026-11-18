# T09 R28 — Native Attack Data & AI Quality

**Đã triển khai và kiểm thử bước sàng lọc dữ liệu phòng thủ. Native data gate `BLOCKED_NO_DEFENSIVE_HANDOFF`, quality gate `BLOCKED_NO_INDEPENDENT_NATIVE_COHORT`.** Có 0 HTTP mới, 0 attack hoặc benign mới được xác minh và 0 lineage độc lập mới. Native chính thức TRAIN / DEV / CAL_FIT / CAL_OP / TEST vẫn **0 / 0 / 0 / 0 / 0**. R27 giữ riêng 2 TRAIN và 4 DEV nghiên cứu cho task phân quyền. [Handoff](/home/trung/projects/idps-web-aws/ai-training/contracts/native-defensive-r28/r28-evidence.json)

## Nguồn dữ liệu

Run `t09-r28-defensive-WxsffqW9` đối soát sáu summary đã có cùng registry R27. Thư mục tiếp nhận mặc định `ai-training/.artifacts/defensive-intake/` chưa có `index.json` từ custodian. Phạm vi thực thi là kiểm tra evidence phòng thủ đã lưu và test metadata. Các số lịch sử theo từng nguồn có thể trùng lineage.

| Nguồn | Đối soát | Kết quả sử dụng |
| --- | --- | --- |
| Queue review ba nguồn | 162 định danh request đã xác minh, 0 nhãn độc lập, 0 nhãn Oracle | Chờ bằng chứng ngữ nghĩa gắn với từng request |
| Oracle pilot cũ | 8/8 request khớp ba nguồn, cả 8 intent unknown | Hữu ích cho kiểm cơ chế liên kết request |
| Grounded request-v3 pilot | 48 record TRAIN nghiên cứu theo T06, gồm 27 benign và 21 attack, rút về 42 view cũ. Summary SHA khớp ledger T02 | Giữ phạm vi nghiên cứu cũ. Chưa có chứng nhận source mask và proof tại cutoff cho native hiện hành. 16 DEV và 10 CAL view giữ vai trò bảo vệ |
| Body observability | PASS trong lab, independent review pending | Xác định được khả năng quan sát để thiết kế cohort body. Thiếu hai lớp đã review và lineage đại diện |
| SOC queue | 64 hồ sơ pending, 0 nhãn được duyệt, 0 campaign độc lập được xác minh | Chờ provenance và review |
| ModSec-WP | 108.883 dòng publisher, 0 positive/benign được audit tin cậy theo profile đích | Giữ riêng nhãn publisher và vai trò dữ liệu hiện hành |

Kết quả kiểm kê ghi số đếm theo nguồn, SHA bytes đã đọc và ngưỡng hỗ trợ T07. Lượt này đọc summary metadata đã định danh. Payload, protected CAL/TEST và source roles lịch sử giữ quyền bảo vệ. [Inventory](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r28-defensive-WxsffqW9/inventory.json)

## Thay đổi intake

R11 kết thúc ở sàng lọc trùng request, trùng vector và đếm cụm sơ bộ giữa các bundle. R28 nối thêm bước sàng lọc TRAIN/DEV theo kế hoạch đã khóa, digest intake và audit lineage. Mỗi audit row phải khớp SHA receipt, bao gồm các row không biết nhãn hoặc đã bị loại. Graph dùng lại closure R27 trên session, actor alias, workflow liên quan, campaign, physical alias, vector và cạnh near đã xác minh.

Cả component bị chặn nếu cắt qua role, chứa alias vật lý trùng, nối protected key hoặc có nhãn đối nghịch cho cùng vector. Reader đối chiếu pin registry R27 và bảo vệ bốn request DEV. Nguồn `DEVELOPMENT` giữ DEV, còn TRAIN cần vai trò ứng viên TRAIN được cấp từ nguồn. Thiếu đối soát cross-domain, near hoặc protected roles khiến gate giữ BLOCKED. Các cờ clearance là assertion có SHA từ custodian và cần evidence đi kèm.

`ELIGIBLE_FOR_CONTRACT_REVIEW` chỉ cho biết có view ứng viên hai lớp ở cả hai vai trò. Bước kế tiếp vẫn cần native export T02 và admission T07. Chứng minh tính đại diện, xác minh custody, duyệt ngữ nghĩa và support CAL/TEST nằm ngoài kết quả của checker. Lượt này xác minh nhánh có dữ liệu bằng fixture, còn nhánh dữ liệu thực chỉ có inventory do thiếu handoff. [Hợp đồng và lệnh chạy](/home/trung/projects/idps-web-aws/ai-training/contracts/native-defensive-r28/README.md)

## Chất lượng và quyết định model

R28 chưa có task payload hoặc behavior được admission, cũng chưa có đủ nhãn độc lập và cùng request để đối chiếu score AI, rule và Hybrid. Chưa đo được recall, FPR, confidence bounds, hoặc lợi ích AI bổ sung trên cohort hợp lệ. R27 đã cho thấy authorization control xử lý đúng sáu trường hợp trong panel hẹp. Kết quả đó giữ nguyên phạm vi.

RI v2 phục vụ mặc định và R20 tiếp tục shadow. B16 URI100 vẫn là ứng viên nghiên cứu publisher đã chọn từ R26.1. B16 Notes CAL_OP recall **28,13%** và PKDD benign FPR **10,69%** là kết quả lịch sử theo từng cohort. Core của hai vấn đề vẫn là collision, ranking và threshold transfer. Chưa có nguồn mới đủ điều kiện để quyết định một pilot hoặc so sánh ứng viên mới. Lượt này huấn luyện **0 model** và promotion/release **BLOCKED**. [Kết quả R26.1](/home/trung/projects/idps-web-aws/docs/109_T09_R261_AUTONOMOUS_RECOVERY_AND_MODEL_QUALITY.md)

Để đánh giá một binary claim theo T07 cần tối thiểu 100 attack và 20 cụm độc lập, kèm CAL, coverage và paired comparison đúng scope. Với 0 false alert, cận trên một phía ≤1% cần ít nhất 299 benign anchors độc lập khi K=1 và 492 mỗi endpoint khi K=7. Đây là tính toán support tối thiểu, còn số endpoint thật phải được khóa với claim family. Mục tiêu recall ≥90% tại FPR ≤1% chưa được chứng minh. [T07](/home/trung/projects/idps-web-aws/docs/53_T07_EVALUATION_PROTOCOL_AND_COVERAGE_GATES.md)

## Nghiệm thu và Git

- **24 test PASS**, gồm 11 R28, 5 closure R27, 8 intake/readiness. Ruff check và format PASS. Các test dùng metadata fixture, gồm cả cạnh nối qua bản ghi đã loại, khóa role, alias về DEV, ngoại lệ protected và SHA sai. [JUnit R28 và R27](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r28-defensive-WxsffqW9/r28-test-results.xml) · [JUnit intake](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r28-defensive-WxsffqW9/intake-test-results.xml)
- Resource Adapter **COMPLETED exit 0**, start/runtime `cpu.max=100000 100000`, `memory.max=536870912`, sample CPU lúc admission và telemetry cuối **56°C**. Guardian giữ policy 90/100°C cùng hardware priority. Cleanup được đọc lại trên kernel và systemd cho worker lẫn guardian. Không còn QEMU thử nghiệm. [Acceptance](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r28-defensive-WxsffqW9/acceptance.json)
- Bốn Local services active, PID khớp R27 và NRestarts=0. SHA B16/R20 khớp artifact đã pin. Các gate ONNX/Rust/latency/restart/failover chưa có candidate R28 để nghiệm thu mới. [Acceptance](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r28-defensive-WxsffqW9/acceptance.json)
- SHA 34 file đã sửa từ trước và 168 artifact R27 khớp. Nhánh `feature/ai-idps-shadow-integration`. Commit `d91af37` chứa checker, inventory và tests. Báo cáo và handoff đi trong commit riêng. Manifest SHA của 17 file evidence giữ tại run private. [SHA index](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r28-defensive-WxsffqW9/artifact-index.json) · [Push readback](/home/trung/projects/idps-web-aws/ai-training/.artifacts/t09-r28-defensive-WxsffqW9/git-push.json)

Bước có giá trị nhất là nhận một cohort phòng thủ đã thu có cả ca sự cố được xác minh và traffic benign đại diện, ưu tiên nhóm có request-time body hoặc history thực sự quan sát được. Khóa population, vai trò và custody, chạy intake/closure, rồi đo thêm TP và FP của AI so với rule-only trên cùng roster. Dùng pilot đó để quyết định có train lại hay giữ ứng viên hiện tại.
