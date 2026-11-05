# AI-IDPS — bàn giao nhóm, 05/11/2026

## Phạm vi và trạng thái

Mục tiêu của gói này là clone, phục hồi đúng model rồi inference offline ngay;
tiếp tục training có giới hạn được công bố riêng. Frozen Baseline v1.0 không đổi.
Không bật IPS, không khởi động Web, không sửa Student Web/Security Web, không tự
train và không mở sealed holdout.

**Publication và remote clean-clone đã PASS.** Release
[`ai-research-team-20261105`](https://github.com/vuong-quoc-trung/idps-web-aws/releases/tag/ai-research-team-20261105)
trỏ source `adfce1b14852a8b3678648b165e070e36ad30b7f`. Tải cả ba archive qua URL
public, phục hồi 102 + 138 + 54 files, chạy hai model với golden scores và
19 contract/safety tests đều PASS. SHA256/size do GitHub API trả về khớp manifest;
bootstrap còn kiểm lại nội dung tải xuống. Xem `release/published-assets.json`
và `release/team-verification.json` cho bằng chứng và trạng thái nhánh integration.

Kiểm chứng dùng clone HTTPS cùng máy, không có source overlay hay `--asset-dir`.
Python/dependencies mới được tải trong clone này trong lúc chờ upload; final
bootstrap dùng lại riêng môi trường mới đó. Không dùng cache/venv/model/data cũ
cho inference. Monitor tài nguyên ở ngoài clone chỉ là test harness. Chưa kiểm
trên máy đồng nghiệp. Runtime source đã kiểm là revision trên; các commit tiếp
theo chỉ ghi báo cáo và xác nhận nhánh, không đổi code đã kiểm.

## Clone → setup → verify → run

```sh
git clone --branch feat/ai-model-training https://github.com/vuong-quoc-trung/idps-web-aws.git
cd idps-web-aws
./scripts/bootstrap-team.sh --tests
```

Hỗ trợ tự động hiện tại: Linux x86_64, Python 3.9+ hệ thống, Git, HTTPS Internet,
khoảng 2 GB đĩa trống cho inference và môi trường. Python hệ thống chỉ khởi động
script; uv 0.13.7 tải từ PyPI với SHA256 pin, sau đó cài riêng CPython 3.12.14 từ
Astral python-build-standalone và exact runtime requirements. Không cần sudo,
Docker, credentials deployment hoặc virtualenv của người bàn giao.
Các nền tảng khác chưa được kiểm chứng. Model assets cố định bằng SHA256/size;
file đã tồn tại khác hash sẽ bị từ chối, không ghi đè checkpoint cũ.

Kết quả tại `.team-state/bootstrap-report.json` và `model-smoke-report.json`.
Smoke gồm hai fused records GLU207 và một HTTP request lành tính RIv2; đây là
kiểm tra phục hồi/contract, không là independent quality evaluation. GLU chạy
ONNX frozen cùng đúng preprocessor; native weights/optimizer cũng được kiểm hash
và cấu trúc, không khởi tạo optimizer lớn chỉ để inference. RIv2 dùng native
checkpoint. Golden scores lấy từ output frozen đã tồn tại, không tự đặt nhãn mới.

Chạy lại smoke offline:

```sh
ai-training/.venv/bin/python scripts/verify-team-models.py
ai-training/.venv/bin/python -m idps_ai --help
```

Inference request bundle độc lập (đường dẫn tương đối với repo):

```sh
ai-training/.venv/bin/python ai-training/.artifacts/integration_candidate_20261105/demo-request-bundle/infer.py --help
```

Contract JSON và `infer-mvp` được mô tả trong
`docs/06_AI_HANDOFF_AND_RUN_LEDGER.md` và frozen manifest
`ai-training/RESEARCH_MVP_V1_0_FROZEN.json`; GLU cần causal fused input đủ ba nguồn sau
response, RIv2 chỉ cần HTTP trước response. Không giả lập fused features để biến
request-only data thành GLU evaluation.

## Phân phối qua GitHub Releases

Không dùng Git LFS, không tạo dịch vụ trả phí. Release tag
`ai-research-team-20261105`. Checksum, URL, file count nằm trong
[`release/assets.json`](../release/assets.json). Mỗi archive có manifest riêng,
original path/SHA/size và content objects; file restore giữ nguyên bytes.

| Asset | Dung lượng | Nội dung | Mặc định |
|---|---:|---|---|
| models-core.tar.gz | 158,265,099 bytes | GLU207 checkpoint + optimizer/state, ONNX, 207-feature spec, threshold; RIv2 checkpoint, encoder/source Git, threshold/fit/eval reports; demo RI frozen | Có |
| request-training-recovery.tar.gz | 419,514,083 bytes | WAF rich-v1/v2 numeric derivatives; candidate train/label/view arrays; plan, checkpoints, exact-resume proofs; RIv1 comparison checkpoints; candidate portable bundle | Opt in |
| historical-baselines.tar.gz | 398,550,668 bytes | bounded76 GLU/MLP và scale-up gated/deep/residual checkpoints/bundles | Opt in |

```sh
./scripts/bootstrap-team.sh --tests --with-research-data --with-historical-models
```

Không cần tải khoảng 20 GB raw artifacts để inference. `--asset-dir` chỉ phục vụ
kiểm chứng trước publish bằng archives local; không được gọi đó là kiểm chứng
download GitHub. Không xóa assets đã publish; thay bytes phải dùng version mới.

## Dữ liệu, privacy và provenance

Chỉ chia sẻ numeric feature tensors và group/view hashes của WAF nguồn
[`puyang2025/waf_data_v2`](https://huggingface.co/datasets/puyang2025/waf_data_v2/blob/b035dc17f875f1f732c10654709abed66a4e9742/README.md),
publisher revision `b035dc17f875f1f732c10654709abed66a4e9742`, card ghi MIT.
Attribution: puyang2025, WAF Data v2. Đây là transformed derivatives, không phải
raw HTTP. Numeric tensors không đồng nghĩa với cam kết không thể suy luận nguồn;
không chuyển session bytes hoặc credentials sang kho public. Publisher labels
NORMAL/ANOMALOUS chưa được xác nhận là attack intent. Không formal admission.
Original parquet không phân phối lại; chỉ train split đã được xử lý, không mở
publisher eval/test/heldout mới.

Giữ local nguyên trạng: PCAP, request/response receipts, HTTP sessions, accounts,
redaction/HMAC keys, raw lab logs, DVWA oracle evidence, restricted third-party
sources và full prepared-v5 GLU training data. Hiện **chưa có private shared
store**. Đồng nghiệp chưa thể khôi phục các phần này; cần kho riêng và cấp quyền
trong công việc sau, không hứa full raw research reproducibility.

`release/research-history/` là 553 metadata views có redaction, mỗi view ghi SHA
của original, SHA của derivative trong index và số redactions. Chúng không thay
thế original evidence hoặc independent review. P0/P0.5/integration reports,
source và tests được giữ trong Git. Không thêm human verification: 111 DVWA
requests vẫn chờ independent review; attack attempt, exploit success, unsafe
reflection và UNKNOWN là các khái niệm khác nhau.

`release/model-catalog.json` liệt kê cả model states không chọn upload. Frozen
endpoints, recovery kit và baselines hữu ích được chọn; nhiều pilot/duplicate/
superseded states vẫn local, không xóa. `local-inventory-summary.json` là tổng
kiểm kê tại thời điểm trước khi tạo bản clone kiểm thử, không phải toàn bộ danh
sách file private. Không đưa `.env`, keys, caches, venv hoặc binary archives vào
Git thông thường. `.gitattributes` chỉ chuẩn hóa text LF.

## Training continuity và kết quả nghiên cứu

| Thành phần | Bằng chứng hiện có | Khả năng trên máy khác |
|---|---|---|
| GLU207, 9,675,784 params, step 652 | Frozen inference, checkpoint + Adam/state, ONNX/spec/threshold hashes | Inference; exact historical resume cần source `3a67d15` và full prepared-v5 restricted, chưa có shared restore |
| Request v2, 50,696 params, step 3072 | Frozen inference/fit/eval manifests | INFERENCE_ONLY đã kiểm chứng; không suy ra exact resume chỉ từ checkpoint |
| Integration candidate numeric-mask p=.25 | 120,435 WAF train views, batch256, lr .001, seed31, 3,072 updates (~6.53 epochs); 128 continuous =64+64 và relocate2816→3072 bằng tất cả arrays/RNG/sampler/history | RESUME_EXACT trong môi trường pin tại local; optional archive giữ dữ liệu/state/plan; cần kiểm chứng độc lập trên máy nhận trước khi nhận claim tương đương |
| Historical baselines | Checkpoints + manifests và metadata history | NOT_VERIFIED cho resume tại HEAD; không bỏ source fingerprint checks |

Candidate không cải thiện đủ để thay frozen RIv2; demo vẫn chọn RIv2. Không train
thêm trong bootstrap. New run phải có thư mục mới; tăng terminal target hoặc đổi
plan là experiment mới, không giả exact continuation. Tham khảo
`ai-training/scripts/integration-request-study.py --help` và
`docs/10_AI_INTEGRATION_CANDIDATE_20261105.md`. Không bypass source/data/contract
hashes để ép checkpoint resume. Kiểm chứng full training bằng raw evidence nằm
ngoài phạm vi bàn giao public hiện tại.

## Tài nguyên và giới hạn kiểm chứng

RAM toàn hệ thống tối đa 30 GB dùng chung. Không tái dùng quota lịch sử 800%.
Release build không nén CPU-intensive và smoke ONNX dùng cgroup CPUQuota10%,
period10ms, một CPU affinity, MemoryMax<=2GiB, swap0; watcher độc lập kiểm cảm
biến CPU mỗi .2s và dừng khi >=79°C hoặc heartbeat stale. Đây là cơ chế phản ứng,
không bảo đảm tuyệt đối không overshoot 80°C.

Các lần thử đóng gói nén/native GLU đã bị watchdog dừng, có lần ghi nhận 81°C.
Không bỏ những lần thất bại khỏi báo cáo. Đóng gói không nén sau đó đạt tối đa
51°C; smoke ORT đạt tối đa56°C. Public bootstrap 821.72 giây, max77°C,
peak cgroup memory khoảng1.72GB, peak system used khoảng10.73GB và19tests PASS.
Một quét metadata archive trong phiên prepublication đã chạy ngoài cgroup;
watcher vẫn đo cảm biến toàn máy, nhưng số đo phiên đó không quy riêng cho
bootstrap. Bản quét đã hoàn tất trước khi thao tác dừng được thực hiện.
Không thay thermal protection OS/firmware.
Trước workload mới phải kiểm tra sensor/watchdog và giới hạn tải phù hợp;
bootstrap tự nó không chứng nhận thermal safety trên máy đồng nghiệp.

Clean clone cùng máy chỉ chứng minh không phụ thuộc venv/cache/artifacts cũ,
không tương đương kiểm chứng máy thứ hai hoặc production readiness. Trạng thái
remote download, tests và branch nằm trong `release/team-verification.json`.
Nhánh integration chỉ tạo sau khi source/model handoff được xác nhận; không bắt
đầu integration hoặc AWS deployment trong nhiệm vụ này.
