# Chuẩn bị và pilot trước train chính thức

## Nguồn HTTP độc lập AIT và quyết định research corpus — 2026-11-02T19:10+07:00

Đã tải trực tiếp archive `russellmitchell_no-pcaps.zip` từ [AIT Log Data Set V2.1 trên Zenodo](https://zenodo.org/records/19483937) vào vùng private `ai-training/.artifacts/source_screen_20261102/ait/` (522.084.364 byte, SHA256 `51a03f51daea0fbbdcfe9b8abe0dbbe10633716f4f98074f861204a162ee1978`, MD5 khớp `abb43a46c70939ad9f98669e3510d2b7`). Metadata API ghi **CC BY-NC-SA 4.0** và open access. Đây là Apache HTTP log thu trong testbed doanh nghiệp mô phỏng có hành vi người dùng và attacker chạy thật trong testbed, **không phải traffic Internet sản xuất**. Chỉ dùng nghiên cứu phi thương mại nội bộ; quyền chia sẻ feature/weights cần xem lại điều khoản trước khi công bố. Biblio-US17 vẫn `PENDING`, không thử lại archive 401; mẫu thư xin quyền ở mục dưới.

Audit có mục tiêu trên bốn file Apache intranet: 7.695 JSON label refs **khác số dòng**, đều nằm trong 8.530 dòng của file đích `.2`, có thời điểm trong cửa sổ attack do nhà phát hành công bố; `gather/attacker_0/logs/attacks.log` tồn tại và hash SHA256 `eb7e96b8ad1270ab96c43de8575631aafb48a0a865e97c1c5c9f8cc117289f06`. Label của nhà phát hành chủ yếu là hoạt động scanner (`dirb` 4.462, `wpscan` 3.186); `webshell_cmd` 32, `webshell_upload` 3. Các nhãn sinh từ **rule/timeline của kịch bản**, không phải review ngữ nghĩa độc lập từng request. Chỉ lấy 2.831 dòng intranet **trước** lúc attacker bắt đầu 03:01 UTC làm ứng viên benign hẹp; 604 dòng không nhãn trong/sau cửa sổ attack và 54 dòng không có method/URI parse được vẫn `unknown`/loại khỏi view. Không quy mọi dòng không nhãn thành benign, không suy exploit outcome từ status.

`project_request` parse được **10.526 Apache observations** ứng viên (2.831 benign tiền tấn công, 7.695 attack nhãn publisher) thành 70 số; `bounded_spec` mã hóa đủ 76 số hữu hạn cho từng dòng. Không có Student audit, request ID chung, body, EVE flow hoặc 137 đặc trưng full-only; không điền giả. Có **71** method+target hash khác nhau trong benign và **7.682** trong attack; còn 76-feature views chỉ **25 benign / 3.146 attack**, với **4 view trùng nhãn** (818 benign observations và 13 attack observations). 2.831 benign rows vì vậy không thay được 25 model views. Chỉ một testbed/campaign, phần attack tập trung vào scan, benign tiền tấn công khác pha thời gian; chia ngẫu nhiên từng dòng sẽ leakage/học shortcut. Không thể đạt gate hiện hữu ≥32 views **mỗi source × mỗi role × mỗi class** ngay cả trước split, cũng chưa có hai nguồn đủ hai lớp. **AIT là ứng viên research có provenance tốt hơn các nguồn rule-only trước, nhưng 0 request được đưa vào corpus study đáng tin hay formal admission ở lượt này.**

Kiểm parity thực tế trên 8 request Oracle development cũ: Nginx raw target ↔ EVE `ai_query_numeric` version 2 khớp **8/8** sau ghép `X-Request-Id`; projector request-only/encoder 70+6 chạy **8/8**, tạo 7 model views. Chỉ có 60 tên số trùng giữa projector và EVE; **6/8 request** có ít nhất một giá trị khác vì request-only alias/drop field nhạy cảm còn EVE numeric project từ target trước bước mask. Đây là **hai profile khác nhau**, không được dùng EVE numbers làm vector request-only rồi tuyên bố parity; 137 full-only không được zero-fill. AIT chỉ kiểm profile method/URI, không chứng nhận parity live edge hay GLU 207.

**Quyết định:** 0 request được formal admission, 0 nhãn intent được review độc lập; 10.526 là observations có nhãn/cửa sổ kịch bản từ **một** nguồn ngoài, không phải 10.526 request train-eligible hoặc 10.526 Ground Truth. Không chạy study ngắn. Bước có giá trị nhất: người có email xin quyền Biblio-US17 bằng thư bên dưới; đồng thời cần nguồn/campaign thứ hai có benign và attack được xác minh request-bound, đủ view diversity, rồi khóa split theo source/campaign/time và purge exact-view overlap trước calibration/validation. Không hạ gate hiện hành.

**Cấu hình study tối thiểu khi gate thực sự qua:** hai source groups độc lập đều có hai lớp và ≥32 request **cùng ≥32 distinct 76-feature views** cho từng `train`/`calibration`/`val` × benign/attack; tổng sàn lý thuyết là 384 views trước test riêng. Dùng `training_pool=curated_multisource`, cùng `request-structure-v1`/`bounded-request-v1` 76 cột, cùng split, seeds và ngân sách FPR để so `deep_mlp` nhỏ với baseline lexical cố định; `residual_glu` 76 cột chỉ là ablation nếu dữ liệu đủ. Chỉ pilot 1–2 epoch theo cap hiện hành, threshold trên calibration, báo cáo theo source/campaign/family và latency trên validation. GLU **9.675.784/207** vẫn là model khác input; không gọi phép thử request-only là kết quả của nó và không dùng holdout khóa để chọn threshold.

## Quyết định nguồn nhãn độc lập — 2026-11-02

Đây là **screening có mục tiêu** trên nguồn chưa giải quyết; không chạy lại corpus audit, campaign, study hoặc trainer. Formal evidence-v2 và `configs/scale_policy.yaml` giữ nguyên. Lượt này phát **0 request**, thêm **0 nhãn benign/attack xác minh độc lập**, admission mới **0**; 8 request Oracle trước vẫn UNKNOWN. Raw MWAD chỉ lưu private, không đưa URI/query vào báo cáo hoặc Git.

| Nguồn | Bằng chứng có thật | Quyết định |
| --- | --- | --- |
| [Biblio-US17, bài báo nhà xuất bản](https://link.springer.com/article/10.1186/s42400-024-00336-3) | Tác giả mô tả 47.402.907 request website thật, RID nối RAW/LABEL theo ngày và thứ tự, 327.906 LVL1 attack đã được chuyên gia xác nhận qua S2/S3. S2=0 là cảnh báo giả được xem thủ công. | **Ứng viên nhãn độc lập mạnh nhất**, nhưng con số là claim của tác giả, chưa kiểm row. CLEAN gồm cả S2=-1/S3=-1 chưa review từng request; không lấy toàn CLEAN làm benign. [idUS](https://idus.us.es/items/53034f60-d215-44b0-a198-eb8a5229218e) ghi CC BY-NC-ND 4.0; endpoint archive trả 401, cần bản được cấp quyền và kiểm quyền dùng. Chỉ có method/URI/status/size/RID; không tạo thời gian chính xác/flow/207 feature. **0 admitted**. |
| [MWAD, repo tác giả](https://github.com/paul12345-cyber/Multimodal-web-attack-Dataset) | Pin revision `a7a19c525bfa94095120c7fa5731ccf33bf2022e`, CC BY 4.0. Hai CSV private: 1.000 URI/1.000 flow vectors, mỗi bảng 500/500 nhãn; 975 URI hash và 989 vector hash khác nhau. | **Research-only**. Không có request ID, timestamp, campaign hoặc khóa ghép URI→flow; nhãn do chiến dịch tác giả sinh, chỉ SQLi, hai block nhãn theo row order. Không chứng nhận 1.000 cặp request vật lý hay independent semantic review; **0 admitted**. |
| [WAF-Bench-77, dataset card](https://huggingface.co/datasets/netgoat-ai/WAF-Bench) | Pin revision `674f8bdcfc2d177beaf323cb80d3d889baaff063`; kiểm private `test.jsonl` 77 ID riêng, 57 malicious/20 benign, CC BY 4.0. | Chỉ fixture kiểm nhanh request-view: chính tác giả ghi **synthetic**, không có physical capture/application oracle, 20 benign còn dưới tối thiểu 32/source/role/class trước khi chia. Public test đã exposed, không train/admission hay coi là final holdout. |
| [CSIC2010 qua IMPACT](https://www.impactcybertrust.org/dataset_view?idDataset=940) | Nguồn gốc ghi rõ `anomalous` gồm request sai cấu trúc **không có ý định độc hại**. | Nhãn binary trong research cũ đo anomaly, **không phải attack intent**; không đổi lịch sử hoặc promote thành formal. |
| [OWASP CRS regression](https://coreruleset.org/docs/index.print), [CICIDS2017](https://www.unb.ca/cic/datasets/ids-2017.html) | Test CRS là expected rule match; CICIDS gắn flow theo lịch attack/network tuple. | Không có per-HTTP-request intent review đủ gate; chỉ fixture/flow research, **0 admitted**. |

**Oracle hiện xác nhận được:** request thật/ID/method/target/clock giữa Student–Nginx–EVE offline, body POST khớp PCAP, response status và thao tác STAFF tạo khoa làm DB `0→1`; đã cleanup lab. Đây là facts về quan sát và side effect **của thao tác hợp lệ**, không xác nhận attack intent hay exploit outcome của SQLi/XSS. Plan intent, HTTP status, rule alert và không thấy side effect đều không tạo ground truth. Cơ chế machine-verifiable có thể được xem xét nếu reviewer độc lập phê duyệt *trước* exact case/body + oracle dự kiến, ký nguồn/plan, capture chứng minh mỗi request khớp, oracle ứng dụng do trust domain khác collector cung cấp và kiểm hậu nghiệm trên mẫu bất đồng. Đây là **tiêu chí đề xuất, chưa được phê duyệt**, và không tự thay evidence-v2/human review.

**Điều kiện study ngắn tiếp theo:** cần ít nhất hai nguồn hai lớp có nhãn request-bound đáng tin; mỗi nguồn × train/calibration/validation × benign/attack có ≥32 request **và** ≥32 model views khác nhau, không trùng group/view giữa partition, embargo 300 giây khi có clock thật; profile request-only phải có cùng feature train/inference và tránh source/label shortcut. Benchmark CSIC/PKDD cũ là retrospective research, không phải study tổng quát hóa mới. Biblio nếu được cấp quyền chỉ có thể mở đường cho **request-only** study sau audit label scope, license, dedup và split; không thể tự đưa vào GLU 207/ba nguồn. Formal `scale_policy.yaml` vẫn yêu cầu 2M admitted, 3 môi trường, 7 ngày, 120 campaign, 95% ba nguồn và family/partition coverage. Chưa có corpus đáp ứng, nên study mới, formal training và champion đều **NOT_RUN**.

**Đường ngắn nhất có giá trị:** xin quyền bản Biblio-US17 qua [idUS request-a-copy](https://idus.us.es/items/53034f60-d215-44b0-a198-eb8a5229218e/request-a-copy?bitstream=17b2ff3b-90ea-48a4-8ecd-a12edc394361), làm rõ quyền nghiên cứu/biến đổi feature, lấy RAW+LABEL+README và xác minh phạm vi S2/S3 trên RID. Song song cần một nguồn/ứng dụng khác có benign+attack được người độc lập review và request/campaign/time provenance; review 162 hồ sơ lab hiện có có thể giúp development nhưng **không** tạo môi trường độc lập. Sau đó mới khóa protocol study, so MLP/GLU trên cùng visible features/FPR budget và tách acceptance chưa xem. Không liên hệ tác giả hoặc tự ký/review thay người có thẩm quyền trong lượt này.

### Phương án truy cập Biblio-US17 và nội dung xin quyền sẵn dùng

Kiểm lại ngày 02/11: trang [request-a-copy](https://idus.us.es/items/53034f60-d215-44b0-a198-eb8a5229218e/request-a-copy?bitstream=17b2ff3b-90ea-48a4-8ecd-a12edc394361) trả HTTP 200, còn endpoint nội dung archive trả **401**. idUS metadata ghi CC BY-NC-ND 4.0, archive khoảng 1,223 GB; giấy phép bài báo khác giấy phép dataset. [Tóm tắt giấy phép Creative Commons](https://creativecommons.org/licenses/by-nc-nd/4.0/) giới hạn mục đích thương mại và chia sẻ bản chuyển thể, nên phải hỏi người cấp quyền về việc giữ feature/model nội bộ và việc chia sẻ artifact trước khi sử dụng. Không dùng đường dẫn thay thế để vượt quyền.

Người sở hữu email có thể mở form trên và dán nội dung sau. Thay các ô vuông bằng thông tin thật; **không gửi password, khóa riêng hoặc log raw**. Chưa ai trong project gửi yêu cầu thay bạn.

> **Subject:** Request for authorized research access to Biblio-US17 (DOI 10.12795/11441/148254)
>
> Dear Biblio-US17 repository team,
>
> I am working on a non-commercial research/learning project on HTTP intrusion detection. I would like authorized access to the Biblio-US17 archive, particularly the RAW, LABEL and README files, to audit request-level label provenance and evaluate a privacy-preserving request-only model. I will keep raw records private, cite the dataset and paper, and will not redistribute the raw data.
>
> Please confirm whether I may use the archive for private feature extraction and model training, and whether I may share aggregate results, derived numeric features or trained model weights. Please also advise any access, privacy, attribution or redistribution conditions beyond the repository's CC BY-NC-ND 4.0 notice.
>
> Name: [your name]
>
> Affiliation, if any: [your affiliation or independent researcher]
>
> Contact: [your email]

Sau khi **được cấp quyền thật**, giữ nguyên bản tải ở vùng private, ghi SHA/terms, kiểm RAW↔LABEL theo RID, mâu thuẫn/duplicate và scope S2/S3. Chỉ xét `LVL1` attack có xác nhận chuyên gia và một tập benign có review rõ; `S2=-1/S3=-1` vẫn không được tự coi là human-reviewed. Chia theo ngày/file RID và model view; không bịa timestamp từ thứ tự RID. Không truy cập archive hoặc tính số request mới ở lượt này.

### Accounting development và feature visibility

Corpus cũ `forward-development-v2` có **118.760 research rows/vectors**, trong đó **55.559 nhãn 0** và **63.201 nhãn 1** theo publisher/runner (SR-BH 24.287/55.713; Student lab 31.272/7.488). Admission file cho phép *technical research fitting* và split có 0 group/model-view collision, nhưng `label_basis` ghi rõ **chưa có independent human review**; các rows này không phải 118.760 physical requests đã xác minh, không là final test, và **0 nhãn intent đủ tin cho study tổng quát hóa mới**. Ngoài ra WAF-Bench có 20/57 nhãn do bên ngoài biên soạn, nhưng là synthetic fixture, không cộng vào HTTP requests thực. Oracle 8 case chỉ xác minh sự kiện quan sát, 8 intent UNKNOWN. Formal admitted **0**.

| Dữ liệu | Feature thực sự có thể lấy | Không được suy diễn |
| --- | --- | --- |
| Biblio khi có quyền | `METHOD` + `URI` đủ đầu vào về mặt schema cho projector request-only **70 số gốc**, encoder tạo thêm 6 tương tác thành **76 đầu vào**; chỉ những dòng parse được mới thành development view. `RESP_CODE/SIZE` có sau response và RID cho ngày/thứ tự. | Clock chính xác, client/session/UA/body/flow, latency, 207 full-view, hoặc clean toàn tập được review. |
| MWAD | CSV URI cho cấu trúc URI; CSV flow cho 22 số flow **riêng biệt**. | Method nếu không ghi, khóa URI↔flow, timestamp/campaign, ba nguồn; không ghép hai CSV theo thứ tự để tuyên bố cặp request. |
| WAF-Bench đã kiểm | Method/path/query object/header/body cho fixture. 56/77 có query; **13 body-only**, gồm **8 malicious**, sẽ mất tín hiệu body với profile 76 cột. | Byte/ordering/encoding query gốc từ JSON object, physical request/time/response/flow; không đo FPR thực từ 20 benign synthetic. |
| Student lab development | Ba nguồn offline và request/response/DB Oracle ở 8 case; 207 post-response theo contract hiện hành khi telemetry đủ. | Intent cho 8 case, live Rust/edge receipt-time parity, pre-response blocking hoặc độc lập môi trường. |

So trực tiếp current `request_view.columns()` và `bounded_spec()/feature_spec.json`: projector cho **70 số gốc**, encoder thêm **6 tương tác** thành 76; **70/76 tên cột request-only trùng tên với 207**, còn **137 cột chỉ có trong 207** (behavior theo actor/time, prior-flow, status/latency/response, role/UA, availability). Trùng tên không bảo đảm cùng giá trị hoặc cùng thời điểm; không padding các cột thiếu bằng 0 để dùng lại GLU 207. Request-only research baseline hiện có trong code, dùng cùng phép che bí mật và chỉ method/URI; nó chỉ đo khả năng học cú pháp request. So sánh với GLU 207 chỉ công bằng trên cùng cohort và visibility có thật, không so điểm khác dữ liệu/nhãn như một cuộc đấu model. Chưa có dữ liệu mới đáp ứng research study hai nguồn hai lớp, nên **không chạy pilot mới**.

## Oracle quan sát development đã chạy thật — 2026-11-02T11:09+07:00

Pilot **riêng** `dev-oracle-observation-v1` đã chạy 8 request trên lab AI-owned loopback. Plan ở `ai-training/.artifacts/devgt1/plan/plan.json` được khóa trước request: SHA nội dung `08361b0f05836e4e774b2050f96e3575a09d8803ecc942d9b10fb5a5e3e61936`, SHA file `f73e25029a921834ef9d1f70ec1e21744f9a0f834039b2b16a2991e7d9b163c6`. Plan pin code thực thi, Student backend Git tree, Nginx template, exact 8 case và partition development. Đây **không** phải plan-v3 có chữ ký ở mục kế tiếp: plan-v3 vẫn chưa có reviewer/public key/approval và chưa phát request.

Oracle thực tế tại `ai-training/.artifacts/devgt1/run/oracle-verification/report.json` (SHA nội dung `973faa9afc23e2333d1f8444e5b56e6a0813d83c55084f11aa7b71be0c46db28`) tái kiểm **8/8 request vật lý**, **8/8 Student–Nginx–Suricata EVE**, **8/8 response status**, **2/2 POST body bytes trong PCAP private**, và **1 thao tác STAFF tạo khoa** có DB count `0→1`, HTTP 201, request ID khớp. Suricata decode **offline** từ PCAP thật, không phải sensor realtime. `cleanup-verification.json` xác nhận DB Docker tạm biến mất và cổng lab đóng. Response ledger chỉ lưu SHA/độ dài/status; không xuất password hoặc token. Report pin SHA của plan, capture, ba nguồn, response, before/after DB và cleanup; blind queue `run/review/` tái kiểm 8/8 với nhãn null.

Các điều trên là **sự kiện quan sát do collector/lab kiểm**. Intent benign/attack được xác minh độc lập **0/0**, exploit outcome của attack **0**, cả **8 intent UNKNOWN**, formal admission **0**. HTTP 200/201, rule alert, claim trong plan và DB side effect của một mutation hợp lệ không tự chứng minh ngữ nghĩa attack. Capture mới chỉ dành cho development; không nhập formal training. Không có reviewer độc lập hay môi trường đánh giá độc lập, nên signed pilot và gate evidence-v2 vẫn nguyên trạng.

Audit `ai-training/.artifacts/devgt1/lineage-audit/report.json` đọc lại ba capture pending cũ và lượt mới: **170 request ID khác nhau**, 10 campaign ID trong **một kiểu môi trường lab**, 79 target hash/91 lượt lặp target; 0 va chạm ID trong bốn capture này. Bản `lineage-audit-all-unsealed/report.json` thêm capture v1 cách ly: **218 ID/13 campaign ID/79 target hashes/139 lượt lặp target**, 0 va chạm trong năm capture. Audit mới chưa quét sealed historical cohort hoặc toàn bộ log lịch sử, nên không chứng nhận global dedup hay tăng tổng 75.360 lên 75.368 request duy nhất. 75.360 là tổng theo report lịch sử, còn formal admitted vẫn **0/2.000.000**. Không chạy study mới: 8 nhãn UNKNOWN không đủ tập hai lớp cho validation/calibration có ý nghĩa.

Quy trình đã tự động hóa phần khách quan `plan/code SHA → lab cô lập → request → Student/Nginx/PCAP/EVE → response/DB oracle → cleanup → blind queue → cross-capture ID audit`. Phần cần nguồn độc lập hoặc người có trách nhiệm vẫn là chứng cứ intent/benign request-bound, chính sách chấp nhận machine labels, campaign/môi trường khác, split theo source/campaign/time và parity 207 feature khi inference sau response. Batch/resume SQLite cũ đã kiểm ở 162 hồ sơ, chưa benchmark 2 triệu; không lặp pilot này để tăng số lượng. Pilot chạy với `CPUQuota=400%`, `AllowedCPUs=0-7`, `MemoryMax=12G`, không dùng dịch vụ trả phí hoặc traffic ngoài lab.

## Ground Truth pilot có protocol ký trước capture — 2026-11-02

Đã khóa plan 8 request trong lab AI-owned loopback, gồm 4 GET benign (một hard negative), 2 GET có attack intent SQLi/XSS dự kiến và 2 POST phục vụ đăng nhập/tạo khoa. Plan đọc được mục đích, method, URI và body không chứa password; pin SHA của collector. `plan-v1`/`plan-v2` là bản soạn trước khi collector source ổn định, **superseded, chưa ký/chạy**. Chỉ dùng `ai-training/.artifacts/ground_truth_pilot_20261102/plan-v3/plan.json`: plan SHA `a38ecc02822e9a2618dcfaa442d00492ae4ce438efc5f6bdd73c3866a5129eb2`, file SHA `4a61049c9a8a6bf05345f203ef95d392c8f2ffd54b23366ba37b12b078d7f9e4`, collector SHA `30c5eee796b6a6544eebabb7268f24a135614efa5d5d9b6905cad9e8c367174e`. Sửa collector sau khi ký sẽ làm preflight từ chối chạy.

**Gói reviewer ngắn:** [APPROVAL_PACKAGE.md](.artifacts/ground_truth_pilot_20261102/APPROVAL_PACKAGE.md) nằm private mode 0600, chứa 8 URI/body được phép, giới hạn lab, rủi ro, SHA, hướng dẫn tạo/giữ khóa Ed25519 và lệnh ký. Không có private key/chữ ký trong gói. Approval mới sẽ ký thêm SHA của **10 file thực thi AI**, Git tree của Student backend và SHA mẫu Nginx; `verify-protocol` và collector so lại trước traffic. Chữ ký vẫn chỉ chứng minh key possession; operator cần xác nhận reviewer thật sự độc lập qua kênh riêng.

**Trạng thái thật:** plan đã tạo và test fixture kiểm đường ký/ghép/oracle; **chưa có reviewer độc lập, chữ ký hay capture pilot thật**. Không có thêm nhãn được xác minh: 162 hồ sơ cũ UNKNOWN, 0 benign/0 attack xác nhận độc lập, 0 admission. 29 bất đồng runner/cú pháp được phân nhóm: 7 runner-benign có cue (5 `hard_negative_1`, 2 `hard_negative_2`); 22 runner-attack thiếu cue (7 command, 9 SQLi, 6 XSS). Đây là giới hạn của regex và claim runner, không phải nhãn sai được chứng minh; không lặp lại các kiểm tra ID/hash đã PASS.

Người phê duyệt **khác collector** cần đọc plan thật, xác nhận ngữ nghĩa từng case và phạm vi lab. Họ giữ khóa Ed25519 riêng, công bố public key qua kênh tin cậy, ký từ terminal riêng tư. Lệnh mẫu (thay đường dẫn key và reviewer ID bằng giá trị thật; không gửi private key, password hay raw logs vào chat):

```bash
cd /home/trung/projects/idps-web-aws
PLAN=ai-training/.artifacts/ground_truth_pilot_20261102/plan-v3
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/evidence-lab-campaign.py sign-protocol \
  --plan "$PLAN" --reviewer-id '<reviewer-doc-lap>' \
  --private-key '<private-ed25519-key>' --trusted-reviewer-key '<trusted-public-key>' \
  --output ai-training/.artifacts/ground_truth_pilot_20261102/approval-v3.json
```

Chữ ký chứng minh **quyền sở hữu khóa**, không tự chứng minh danh tính hay tính độc lập của reviewer. Operator phải kiểm điều này qua kênh ngoài hệ thống. Collector `collect-three-source` từ chối pilot thiếu chữ ký hoặc source/plan bị đổi **trước khi khởi động lab**. Sau chữ ký thật, chạy pilot đúng một lần trong lab loopback với cgroup ≤4 CPU/12 GiB, rồi tạo blind queue và `stage-protocol`. Bước stage tái kiểm Student/Nginx/EVE, request ID, method, target SHA, timestamp sau approval/preflight và đúng một request mỗi case. Chỉ GET có đủ ba nguồn mới được ghi `MACHINE_VERIFIED_PROTOCOL_MATCH` ở **staging**; hai POST giữ UNKNOWN vì body thực chưa được bind với signed plan. Oracle DB đọc marker khoa trước và sau POST trong disposable DB; đó là **quan sát do collector ghi**, không phải oracle độc lập và không chứng minh attack intent/exploit outcome. Tất cả `formal_training_eligible=false`; gate evidence-v2 hiện hành không thay đổi.

Collector dừng Student, sensor và PostgreSQL Docker `--rm` trong `finally` sau khi đọc oracle; `verify_lab_cleanup` kiểm marker/cleanup, process identity, container biến mất và ba cổng loopback đóng. Kết quả dự kiến ở `gtp3/cleanup-verification.json`; nếu cleanup fail, pipeline không tiếp tục decode/correlation để tuyên bố pilot PASS. Hai lab ba nguồn cũ đã được kiểm lại bằng verifier này và PASS; pilot mới chưa chạy. Container không có mount persistence được chỉ định, nên mutation tạo khoa biến mất cùng disposable DB khi stop. Đây là xác minh dọn lab, không phải application oracle độc lập.

| Bước có thể tự kiểm | Ý nghĩa cho admission hiện hành |
| --- | --- |
| Chữ ký, plan SHA, 10 code SHA, Student Git tree/Nginx template và thời điểm preflight | Chứng minh integrity và key possession; tính độc lập/đúng ngữ nghĩa của reviewer cần xác nhận ngoài hệ thống |
| Student/Nginx/EVE, PCAP, request ID, method, target, status, timestamp và đúng 1 request/case | Chứng minh request quan sát khớp protocol; không tự xác nhận intent hoặc exploit outcome |
| DB count 0→1 cho `faculty_create` rồi xác minh disposable DB đã bị xóa | Xác nhận collector quan sát được side effect benign và trạng thái lab được dọn; không là oracle độc lập cho attack |
| Evidence-v2 review, prepared dataset/provenance và corpus gate | Vẫn cần reviewer độc lập và điều kiện dữ liệu; pilot staging không tự chuyển sang admitted |

Lệnh tiếp tục **chỉ sau khi chữ ký thật đã có**; người vận hành kiểm SHA/key fingerprint trước khi chạy. Output `gtp3` ngắn để Unix socket của lab không vượt giới hạn đường dẫn:

```bash
cd /home/trung/projects/idps-web-aws
PLAN=ai-training/.artifacts/ground_truth_pilot_20261102/plan-v3
APPROVAL=ai-training/.artifacts/ground_truth_pilot_20261102/approval-v3.json
PUBKEY='<trusted-public-key>'
PILOT=ai-training/.artifacts/gtp3
systemd-run --user --scope -p CPUQuota=400% -p AllowedCPUs=0-7 -p MemoryMax=12G -p MemoryHigh=11G -p MemorySwapMax=0 \
  env PYTHONPATH=ai-training/src PYTHONDONTWRITEBYTECODE=1 \
  ai-training/.venv/bin/python ai-training/scripts/evidence-lab-campaign.py collect-three-source \
  --plan "$PLAN" --output "$PILOT" --nginx-bin "$PWD/.local-dev/foundation/tools/runtime/usr/sbin/nginx" \
  --suricata-runtime "$PWD/ai-training/.artifacts/upgrade_20261028/tools/runtime" \
  --protocol-approval "$APPROVAL" --trusted-reviewer-key "$PUBKEY"
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/prepare-evidence-review.py \
  --plan "$PLAN" --lab "$PILOT/lab" --capture "$PILOT/capture" \
  --three-source "$PILOT/correlated" --output "$PILOT/review"
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/evidence-lab-campaign.py stage-protocol \
  --plan "$PLAN" --lab "$PILOT/lab" --capture "$PILOT/capture" \
  --review "$PILOT/review" --three-source "$PILOT/correlated" \
  --approval "$APPROVAL" --trusted-reviewer-key "$PUBKEY" \
  --application-oracle "$PILOT/application-oracle.json" --output "$PILOT/staged"
```

Nếu một bước fail, giữ artifact lỗi để điều tra, không đổi plan đã ký hoặc gán nhãn cho capture một phần. Cần tạo plan mới và ký lại trước lượt thử mới.

Nếu pilot được ký/chạy thành công, cần pin artifact capture/PCAP/EVE, đánh giá độc lập cơ chế trust và sampling audit theo campaign, phê duyệt chính sách machine labels rồi mới xem xét admission. Việc này vẫn chỉ tạo một campaign **development trong một lab**, chưa có tập prospective độc lập, chưa có parity live edge/207 features và chưa mở study/train. Để mở rộng tới 2 triệu request phải có nhiều nguồn/campaign được phép, dedup toàn cục, label provenance và kiểm toán theo batch; không nhân số request bằng observations hoặc lặp plan này.

**Đánh giá mở rộng:** Quy trình ký exact 8 case và `stage-protocol` đọc cả shard vào RAM chỉ phù hợp pilot nhỏ. `review-evidence.py auto` đã có SQLite/batch/resume cho 162 hồ sơ và kiểm lại khi crash, nhưng chưa benchmark 2 triệu. Ở quy mô lớn cần protocol ký theo campaign/template/seed và version code, mapping deterministic tới từng request ID/target, xác minh stream theo shard, dedup toàn cục bằng khóa request vật lý, partition source/campaign/time khóa trước capture, cùng kiểm toán ngẫu nhiên theo family/môi trường. Reviewer độc lập phải phê duyệt ngữ nghĩa và chính sách machine labels cho từng loại generator/oracle; đợt ký này **không** tự mở quyền admission cho các campaign tương lai. Xây phần scale sau khi pilot thật chứng minh ba nguồn và trust boundary hoạt động; hiện 0 throughput/quality evidence ở quy mô 2 triệu.

## Lượt review tự động blind, batch và resume — 2026-11-02

`review-evidence.py auto` đã chạy trên **162/162 request** qua ba capture shards private. Mỗi shard được tái kiểm plan/capture/queue, SHA từng dòng Student/Nginx/EVE khi có, method/status/clock/campaign và PCAP body provenance. SQLite private giữ một record cho một request ID/event key; chạy thử 65 record rồi `--resume` thêm 97, chạy lại thêm 0. Không phát request mới, không đọc holdout. `auto-compare` chỉ được mở claim runner **sau khi** blind DB hoàn tất và pin hash; không sửa blind records. 39 query có một cue cú pháp để ưu tiên triage; khi đối chiếu hậu kiểm có 7 cue trên claim benign và 22 claim attack không có cue. Đây là bất đồng tín hiệu yếu, **không phải nhãn sai đã chứng minh**.

Kết quả nhãn: **0 oracle verified, 0 AI model proposed, 0 independent human reviewed, 162 intent UNKNOWN, 0 admitted**. Bộ cue là luật cú pháp định trước, không được gọi là AI model hoặc ground truth. 12 POST có body PCAP, 6 POST cũ thiếu body; 102 query chỉ nhìn thấy trong Nginx lab private. 162 request có 78 target views, 84 lượt lặp view và 36 view xuất hiện xuyên campaign: không chia các campaign cùng lab thành train/val/test. Dedup ở đây theo request ID trong registry; sealed historical cohort không đọc nên chưa có global dedup. SQL/JSON report không lưu plaintext query, password hoặc token. [Machine report](reports/ATTACK_EVIDENCE_20261101.json) pin artifact và SHA; artifact active private là `ai-training/.artifacts/evidence_campaign_20261102/auto-review-v3/` và `auto-review-v3-unblind/`. V1/V2 là lượt kỹ thuật đã superseded, giữ private để truy vết.

Lệnh chạy lại hoặc tiếp tục trên cùng artifact private:

```bash
REG=ai-training/.artifacts/evidence_campaign_20261102/review-registry.json
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/review-evidence.py --registry "$REG" auto --output ai-training/.artifacts/evidence_campaign_20261102/auto-review-v3 --batch-size 32 --resume
```

Với corpus tương lai, registry có thể chứa nhiều capture shards; mỗi shard được xác minh trước khi ghi batch vào SQLite. Nếu tiến trình bị ngắt sau một commit nhưng trước report, dùng `--resume --recover`: tool kiểm lại **mọi record cũ với capture thật**, từ chối record lạ/sai và ghi report mới; không dùng `--recover` cho bản complete bị đổi SHA. Test đã giả lập mất report ở checkpoint rồi phục hồi. Chưa benchmark luồng này ở 2 triệu request, nên chưa tuyên bố đạt throughput/quy mô production. Capture mới cần pin request ID, UTC clock, source SHA, query visibility, body HMAC và application oracle độc lập *ngay khi thu*, cùng provenance người vận hành; app oracle phải có chứng cứ state/side-effect, không chỉ status/alert. Gate evidence-v2 hiện hành vẫn yêu cầu người review độc lập và dataset/provenance request-bound. Nếu muốn chấp nhận machine-verified labels về sau, cần phê duyệt chính sách riêng về trust boundary của oracle, ký/chứng thực producer, test tamper/disagreement và audit mẫu theo campaign; **chưa sửa gate**. Hiện tự động hóa đã thay thế 162 lượt đối chiếu cơ học, nhưng **0 trong 162 kết luận ngữ nghĩa** có thể bỏ qua người review theo gate hiện hành. 29 disagreement giúp ưu tiên chứ không cấp nhãn.

## Review riêng tư 162 hồ sơ và POST body evidence — 2026-11-02

Đã chuẩn bị công cụ terminal `scripts/review-evidence.py` trên ba queue private, mỗi queue 54 request. Công cụ tái kiểm hash/ID/timestamp/campaign và nguồn Student–Nginx, thêm EVE HTTP/flow khi đã capture; hiện **162 chưa được người độc lập review, 0 benign/0 attack được xác minh, 0 admitted**. Người review xem facts và query được che PII/secret trước; chỉ sau khi lưu quyết định bất biến mới dùng `unblind` để xem claim của runner. Cú pháp/rule/status/plan không là ground truth. Công cụ yêu cầu tự khai danh tính khác collector nhưng không thể xác thực danh tính hay tính đúng của nhãn.

Hai PCAP ba nguồn đã được kiểm byte HTTP/response ID và target SHA: **12/12 POST** có body thực được quan sát (mỗi lượt 6). Artifact private `body-evidence-v1` chỉ lưu độ dài, tên field allowlist và HMAC với khóa 0600; không ghi giá trị password/token. HMAC chứng minh cùng bytes khi đọc lại PCAP, **không cho biết ý định tấn công hoặc exploit thành công**. Sáu POST của queue hai nguồn cũ không có PCAP body tương ứng: phải để `unknown` nếu không có bằng chứng độc lập khác, tuyệt đối không tái dựng từ runner/status. PCAP/khóa/raw Nginx chỉ ở máy riêng tư; không đưa vào Git. Query Nginx lab tồn tại trong capture private và chỉ hiển thị cục bộ sau mask; edge production vẫn chưa chứng nhận numeric query parity.

Người độc lập chạy trong terminal riêng tư từ root repo (không chuyển artifact private qua Git):

```bash
REG=ai-training/.artifacts/evidence_campaign_20261102/review-registry.json
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/review-evidence.py --registry "$REG" sources
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/review-evidence.py --registry "$REG" review --source eve_novel --reviewer-id <id-nguoi-review-thuc> --output ai-training/.artifacts/evidence_campaign_20261102/human-review/eve_novel
```

Lặp lệnh `review` với `eve_first` và `two_source`, thay cả `--source` và thư mục `--output`; có thể thoát `q` rồi chạy lại đúng reviewer ID để tiếp tục. Mỗi request chọn `b`/`a`/`u`, ghi family cho attack và giải thích ngữ nghĩa tối thiểu 20 ký tự dựa trên HTTP/ứng dụng đã quan sát. **Với POST, HMAC không hiển thị nội dung: muốn kết luận benign/attack, người review phải tự xem body trong PCAP private và xác nhận câu hỏi riêng của tool; nếu chưa xem, chọn `u`.** Thiếu bằng chứng thì chọn `u`. Xong từng queue, chạy `status` rồi `finalize` với cùng `--source`/`--output`; `finalize` khóa hash quyết định nhưng **không cấp admission**. Có thể `unblind --source eve_novel --request-id <ID> --output <thư-mục-review>` sau khi đã quyết định ID đó để đối chiếu proposal. Không sửa quyết định cũ nếu bất đồng; mở vòng review mới riêng và truy vết bất đồng.

Sau human review, cần kiểm chứng độc lập danh tính/quy trình và semantics, gắn quyết định với `event_key` của **prepared dataset thực**, lập evidence-v2 manifest có capture + intent provenance + semantic review riêng, rồi chạy `scripts/audit-label-evidence.py` và corpus catalog gate hiện có. Công cụ review chưa tự chuyển self-attestation thành nhãn đủ điều kiện. Cần thêm nguồn/môi trường/campaign được cấp phép độc lập có cả benign/attack, split và live 207-feature parity trước formal training. Không phát campaign cùng lab chỉ để tăng số dòng.

207 feature hiện là hợp đồng **post-response**: status, latency, response bytes và các behavioral counts chỉ có sau response; không hợp lệ để chặn trước response. Causal profile lấy flow đã hoàn tất trước thời điểm request theo `available_at=max(EVE timestamp, flow.end+65s)`; không lấy flow tương lai của chính request. 18 dynamics dùng lịch sử tới request hiện tại. `InferencePipeline` dùng cùng spec `state_limits`/207 cột và từ chối implementation SHA khác, nhưng live bridge Rust, thời gian nhận event và query trước mask chưa được chứng nhận. Không tuyên bố realtime/production parity từ replay PCAP offline.

## Tiếp tục admission và capture khác target — 2026-11-02T08:54+07:00

Hai lượt AI-owned ba nguồn chạy liên tiếp trên **cùng lab loopback** đều khớp 54/54 Student audit + masked Nginx + Suricata EVE HTTP/flow; Suricata đọc PCAP thật **offline**, chưa phải sensor realtime đang chạy liên tục. Lượt mới `ai-training/.artifacts/eve3-1102c/` có 54 request và 42 target hash mới so với các lượt trước. Profile `novel-v2` chốt trước khi gửi, 30 target attack/hard-negative khác hai plan cũ, dùng nhiều endpoint/query/hard-negative mới; 3 campaign vẫn development một môi trường, không dùng làm validation/test. Masked Nginx có `query_string=null` ở 54/54 request; EVE v2 cung cấp numeric query từ packet trước redaction và khớp private Nginx 54/54. Đây là **parity của đường offline trong lab**, chưa chứng minh live production EVE adapter hoặc toàn bộ 207 feature tại inference. Flow EVE kết thúc/phát muộn tối đa 11,341s; chỉ dùng khi đã phát, không điền ngược thông tin tương lai.

Đã tự động lập hồ sơ 3 queue, tổng **162 pending request**: 54 hai nguồn cũ, 54 ba nguồn cũ, 54 ba nguồn mới; 48 request auth-boundary v1 vẫn cách ly. Từng `review-assist.jsonl` lưu **facts blind** (ID, SHA, nguồn, clock, method/status, sự hiện diện query, thiếu oracle) và `review-proposals.jsonl` lưu riêng claim từ runner + gợi ý cú pháp. Reviewer đọc facts/capture riêng tư trước, ghi nhận định độc lập, **sau đó mới mở proposals** để đối chiếu. File proposal không phải model prediction hay ground truth. Ở campaign mới, cue xuất hiện ở 9 request runner khai benign và chỉ 15/18 request runner khai attack; tự gắn nhãn từ cú pháp sẽ sai. Cả 162 vẫn `unknown`/`label=null`, 0 reviewer độc lập, 0 admission. Artifact mới: `ai-training/.artifacts/evidence_campaign_20261102/assist-old54-v2/`, `assist-new54-v2/`, và `ai-training/.artifacts/eve3-1102c/assist-v2/`; report ở mỗi thư mục pin SHA facts/proposals và queue. Raw query/body chỉ ở capture private; facts/proposals không ghi plaintext.

Audit bốn capture + bảy Student log lịch sử chưa sealed: **210 ID request mới khác nhau** (48 cách ly +162 pending), 78 target hash, 132 lượt lặp target, 0 va chạm với **227.619 ID** lịch sử được quét. Log lịch sử có cả setup/observations, không phải count request admission; sealed cohort không đọc nên dedup toàn cục chưa được chứng nhận. Tổng theo capture reports 75.150 lịch sử +210 mới = **75.360 request ghi nhận/2 triệu (3,77%)**; **0/2 triệu admitted**. 9 campaign ID development hợp lệ trong một lab, 3 campaign v1 cách ly, **0 campaign/môi trường đánh giá độc lập**. Mô hình GLU 9.675.784/207 và MLP 252.680 không đổi; formal train bị gate chặn đúng thiết kế.

Quy trình còn cần người review **khác collector** xác nhận semantic intent theo request, campaign và ngữ cảnh ứng dụng; POST thiếu body evidence trong audit/Nginx/EVE, exploit outcome cần oracle ứng dụng độc lập. Plan/response/status/alert và cú pháp không tự xác nhận. Sau review mới tạo evidence-v2 ledger, prepared dataset/provenance và chạy catalog admission; cần thêm campaign ở môi trường hoặc nguồn được cấp phép độc lập, cân bằng benign/attack, cùng live visibility contract trước study MLP/GLU. [Report](reports/ATTACK_EVIDENCE_20261101.json), [handoff](FINAL_TRAINING_HANDOFF.json), ledger 06 mục 38. Không chạy train dài, mở holdout, chọn champion hay bật chặn.

## Capture ba nguồn trên lab AI — 2026-11-02T08:31+07:00

Đã khắc phục khoảng trống EVE của collector evidence: Nginx của lượt capture 01/11 chạy ở host, còn sensor PCAP chạy trong network namespace riêng. Lượt mới dùng Nginx AI-owned trong namespace, `tcpdump` bắt gói TCP loopback thật rồi Suricata đọc PCAP offline. Không sửa Student/Security. `ai-training/.artifacts/eve3-1102b/` giữ PCAP, EVE đã khử query/UA, hai log gốc private, report và queue. `correlated-v2/report.json` xác nhận **54/54 request ID** khớp Student + Nginx + EVE HTTP, 54 flow, 18 alert, 1 stats; 0 sai khác numeric query projection giữa Nginx lab private và EVE; timestamp client→EVE HTTP tối đa 0,708s. Flow được phát ra muộn tới 10,811s sau HTTP: giá trị flow chỉ là bằng chứng khi sensor thực sự phát, không được đưa ngược vào feature tại thời điểm request. Alert không phải nhãn.

Queue mới `eve3-1102b/review-three-source-v2/blind-review.jsonl` giữ **54/54 `unknown`, null-label, 0 admission**, liên kết hash dòng Nginx/Student/EVE HTTP và flow record; không chứa raw query/IP/payload. Tái kiểm chỉ đọc:

```bash
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/prepare-evidence-review.py \
  --verify-existing --plan ai-training/.artifacts/evidence_campaign_20261102/plan-v1 \
  --lab ai-training/.artifacts/eve3-1102b/lab --capture ai-training/.artifacts/eve3-1102b/capture \
  --three-source ai-training/.artifacts/eve3-1102b/correlated-v2 \
  --output ai-training/.artifacts/eve3-1102b/review-three-source-v2 \
  --collector-source ai-training/.artifacts/evidence_campaign_20261102/collector-source-v3.py
```

Lượt cũ 54 hồ sơ hai nguồn vẫn pending; không gắn EVE mới ngược về các request đó. Ba campaign mới là development trên **cùng lab và cùng target variants**; không bổ sung môi trường hay syntax độc lập. Audit ba capture: 156 ID request khác nhau (48 cách ly + 54 cũ + 54 mới), 36 target hash, 120 lượt lặp target; 0 ID va chạm trong phạm vi 73.218 ID Student từ ba log *không sealed*. Cohort sealed không đọc và không có chứng nhận unique toàn cục của 75.150 request lịch sử. Tổng số request được ghi nhận theo các báo cáo capture là 75.306/2.000.000 (3,77%) nhưng **scale admitted 0/2.000.000**. Không coi count này là corpus đủ train.

Quy trình review mục dưới vẫn áp dụng: reviewer khác collector xem raw private request và ngữ cảnh ứng dụng trước khi mở planned intent; chỉ xác nhận nhãn nếu có bằng chứng ngữ nghĩa request-bound. EVE flow/alert, status 200/401 và planned label không tự phê duyệt intent hoặc exploit outcome. Queue mới chỉ thêm bằng chứng đối chiếu network. Formal feature profile 207 cột vẫn **chưa chứng nhận parity**: Nginx lab private query và EVE numeric projection nhìn thấy trước mask, còn edge production dùng mask khác. Không đưa capture mới vào training/inference chính thức cho đến khi contract quan sát được thống nhất và evidence-v2 admission qua gate. [Report](reports/ATTACK_EVIDENCE_20261101.json), [handoff](FINAL_TRAINING_HANDOFF.json), ledger 06 mục 37.

## Tiếp tục 54 hồ sơ capture — 2026-11-01T11:45+07:00

**Chưa duyệt nhãn hoặc train:** 54/54 blind-review item đã được đọc lại từ plan/capture và hai log nguồn; tất cả vẫn `unknown`, `label=null`, `training_eligible=false`. Verifier hiện đối chiếu method, status, path + hash target, timestamp ba phía và SHA từng dòng. Bản source collector gốc cho plan-v2 được giữ riêng tại `.artifacts/evidence_campaign_20261101/collector-source-v2.py` đúng SHA đã pin (`3c6aad3e...`); dùng bản này khi kiểm capture cũ, không dùng source hiện hành đã được nâng cấp. Lệnh tái kiểm chỉ đọc:

**Model check không fit:** bundle pilot `scale_upgrade_20261030/pilot/residual_glu-bundle` là đúng mô hình 9.675.784 tham số / 207 đầu vào: ONNX SHA khớp report, inference batch 1 cho output hữu hạn, parity cũ trên 69.345 rows và exact resume đã ghi PASS. Bundle `partition_recovery_20261031/study/glu1024-bundle` là model **khác**, 9.541.640 tham số / 76 đầu vào, cùng MLP 219.144 đối chứng; hai bundle 76 cũng đọc được, hash khớp và inference hữu hạn. Tất cả là pilot/development, chưa có formal model được train trên corpus admitted hoặc live serving được nghiệm thu. Cổng `require_scale_dataset(prepared-v5)` vẫn từ chối vì chưa có 2 triệu admitted + independent calibration.

```bash
PYTHONPATH=ai-training/src ai-training/.venv/bin/python ai-training/scripts/prepare-evidence-review.py \
  --verify-existing \
  --plan ai-training/.artifacts/evidence_campaign_20261101/plan-v2 \
  --lab ai-training/.artifacts/evidence_campaign_20261101/lab-v2 \
  --capture ai-training/.artifacts/evidence_campaign_20261101/capture-v2 \
  --output ai-training/.artifacts/evidence_campaign_20261101/review-v3 \
  --collector-source ai-training/.artifacts/evidence_campaign_20261101/collector-source-v2.py
```

**Quy trình cho reviewer độc lập** (người khác collector; chỉ trong workspace riêng tư):

Artifacts `.artifacts/` bị Git ignore và chỉ tồn tại trên máy hiện tại; reviewer khác máy cần bản sao qua kênh riêng được phép, có checksum/kiểm quyền truy cập. Không đưa raw Nginx query, Student audit hoặc credential vào Git để thực hiện review.

1. Xác nhận lệnh trên trả `BLIND_QUEUE_REVERIFIED_NO_LABELS_APPROVED`, sau đó lấy từng `request_id` từ `review-v3/blind-review.jsonl`. Mỗi ID phải có đúng một dòng ở `lab-v2/access-lab.log` và `lab-v2/student-audit.log` với SHA như queue. Không sao chép raw query, IP, cookie hay credential ra báo cáo công khai.

   Để xem một request trong terminal riêng tư, đặt `REVIEW_REQUEST_ID` rồi chạy đoạn chỉ đọc dưới đây. Nó chỉ in method/path/query/status/timestamp, không in body, IP, user hay header; query vẫn có thể nhạy cảm và không được dán vào chat hoặc issue công khai.

   ```bash
   REVIEW_REQUEST_ID='ID_TRONG_BLIND_QUEUE' python3 - <<'PY'
   import json, os
   from pathlib import Path
   root = Path('ai-training/.artifacts/evidence_campaign_20261101/lab-v2')
   rid = os.environ['REVIEW_REQUEST_ID']
   for name in ('access-lab.log', 'student-audit.log'):
       with (root / name).open() as stream:
           found = [row for line in stream if (row := json.loads(line)).get('request_id') == rid]
       if len(found) != 1:
           raise SystemExit(f'{name}: cần đúng một dòng, thấy {len(found)}')
       row = found[0]
       print(name, {key: row.get(key) for key in
           ('timestamp', 'http_method', 'uri_path', 'query_string', 'status', 'status_code')})
   PY
   ```
2. Trước khi nhìn planned intent, xem request thực trong hai log và ngữ cảnh hợp lệ của ứng dụng. Ghi riêng kết luận semantic `attack` / `benign` / `unknown`, attack family nếu có, mức nhìn thấy payload và lý do gắn với event key. Query Nginx ở lab là dữ liệu private; Student audit đã mask và **không thay thế** query gốc cho semantic review. POST login không có body được xác minh trong hai log, nên thiếu bằng chứng thì giữ `unknown`.
3. Sau kết luận blind, mở `plan-v2/plan.json` để kiểm campaign/case/target hash đã đăng ký trước capture. Runner intent là provenance cần đối chiếu, không tự động là nhãn đúng. HTTP 200/401 hoặc Suricata alert không chứng minh intent hay exploit outcome. Giữ `exploit_outcome=unknown` trừ khi có oracle ứng dụng độc lập.
4. Lưu nhận xét và artifact semantic riêng, bất biến, request-bound; không sửa `blind-review.jsonl`. Reviewer ghi danh tính thật/đơn vị review, khác collector. Bất đồng hoặc thiếu dữ liệu giữ pending; không điền nhãn dựa trên model/rule. Khi có dataset + provenance bất biến, lập evidence-v2 ledger với capture, intent provenance và semantic artifact theo đúng `src/idps_ai/data/label_evidence.py`; chạy `scripts/audit-label-evidence.py` và catalog admission. Event key trong queue phải được bind lại với event key của dataset thực tế, không coi hash queue là ID model mặc định.

Hai capture mới đã được audit cùng nhau: **102 ID khác nhau, 36 target hash khác nhau, 66 lượt lặp target**, 0 ID trùng với **73.218 ID** trong ba log Student lịch sử *không niêm phong* đã chỉ định. Lặp target là request vật lý khác nhau, nhưng không phải độ đa dạng template mới. Log lịch sử có cả setup event; các ID đó không được cộng thành train rows. Cohort lịch sử đã khóa không được đọc, nên **chưa có chứng nhận dedup toàn cục** cho 75.150 request lịch sử. Artifact chỉ chứa count/hash: `.artifacts/evidence_campaign_20261101/lineage-audit-v2/report.json`.

Campaign tiếp theo phải đăng ký trước source/environment/time/seed/template và role; cần ứng dụng hoặc thời điểm độc lập, phiên benign/hard-negative/attack đủ sâu qua cửa sổ 10/60/300 giây, Student + Nginx + EVE với request ID/clock/capture SHA, và cùng khả năng quan sát query với edge. Tách một tập prospective sealed không dùng chỉnh model; 3 campaign hiện tại và 3 campaign v1 bị cách ly đều là development. Không chạy collector mới cho đến khi có target được cấp phép, reviewer độc lập và thiết kế nguồn EVE/feature parity rõ ràng.

## Thu thập HTTP có bằng chứng ngay từ lúc phát request — 2026-11-01T11:21+07:00

AI-owned disposable Student/Nginx lab `127.0.0.1:18881` đã chạy 3 campaign development theo plan có SHA được ghi trước khi gửi. Lượt đầu 48 request bị cách ly: 45/48 trả 401 do runner chưa đăng nhập, không đại diện cho hành vi ứng dụng. Đã sửa **collector AI** để đăng nhập bằng tài khoản fixture riêng và thu lại trên lab mới. Lượt đạt kiểm tra vận hành có **54 request ID duy nhất**, 54/54 khớp Nginx + Student audit về ID/method/status; 0 workload bị 401 chặn trước ứng dụng. Plan gồm 36 benign/hard-negative intent và 18 attack intent, nhưng đây là khai báo hành động của runner, **không phải 36/18 nhãn đã được người độc lập phê duyệt**. 54/54 exploit outcome vẫn `unknown`.

Review queue riêng tư `ai-training/.artifacts/evidence_campaign_20261101/review-v3/blind-review.jsonl` có 54 bản ghi null-label/unknown, SHA source lines và timestamp; không chứa IP, URI/query, UA, body hay password. Chênh lệch clock lớn nhất giữa client/Nginx/Student 0,924s; 30 attack/hard-negative target khác nhau không lặp giữa campaign. Cả 3 campaign thuộc **một lab, một thời điểm và development-only**; không lập validation/test từ chúng. Future holdout chỉ được đặt chỗ, chưa sinh traffic hoặc score. Nginx lab query view vẫn khác edge production mask, EVE chưa thu trong lượt này; cần kiểm parity trước khi đưa vào feature profile hiện hành.

**Admission mới vẫn 0 request; 0 benign/0 attack được review độc lập; 0 campaign đánh giá độc lập.** Cần reviewer độc lập kiểm semantic intent theo capture và plan, sau đó tạo dataset/provenance bất biến + review-v2 evidence ledger và chạy corpus admission gate. Chỉ khi có thêm campaign/source/holdout hợp lệ mới study MLP/GLU. Xem [report](reports/ATTACK_EVIDENCE_20261101.json), handoff và ledger 06 mục 34. Fixture tạm đã dừng Nginx/Student/DB; raw và failed pilot giữ private để truy vết.

## Rà soát 64 hồ sơ và workbook ModSec-WP — 2026-11-01T10:53+07:00

**Formal vẫn NOT_READY; lượt này thêm 0 request admission, 0 positive/0 benign có nhãn độc lập, 0 campaign độc lập được xác minh.** Đã đối chiếu SHA của 64 locator SOC-MLD với raw access log, tạo `ai-training/.artifacts/attack_evidence_20261101/soc-pending-review-final-v2/pending-dossiers.jsonl` (private, mode 600). Cả 64 vẫn unknown/pending; 64 GET, 63 phản hồi 4xx, 1 phản hồi 2xx, 3 có query. Không tìm được EVE HTTP match theo IP/method/target trong ±2s; điều này không chứng minh thiếu traffic. Operator labels thiếu request ID và timezone nên campaign/intent/outcome đều chưa được bind. Hồ sơ chỉ lưu cấu trúc HTTP, SHA và locator; reviewer phải đọc bản capture riêng tư và cung cấp bằng chứng độc lập trước khi quyết định. Split SOC-MLD gốc có 38 attack-instance ID chung, gồm 1.852 train và 1.214/1.220 test rows: không dùng split này để tuyên bố tổng quát hóa.

Đã tải và kiểm SHA workbook ModSec-WP v2 từ [Zenodo DOI](https://zenodo.org/records/21872151), CC BY 4.0 theo API chính thức. Audit streaming 108.883 dòng chỉ thấy 27.686 transaction ID và event key khác nhau; 81.197 dòng lặp, 20 transaction ID có nhãn mâu thuẫn (60 dòng) và 25 request view có nhãn mâu thuẫn. Workbook ghi 108.823 dòng năm 2024 và 60 dòng năm 2026; 18.474 biểu diễn method/URL/body khác nhau. Đây là số dòng/ID/view, **chưa xác minh physical request**. Nhãn publisher có 96.286 attack rows và 12.597 normal rows; toàn bộ chưa được admission do thiếu trail nhãn từng request, campaign IDs và xử lý xung đột. Artifact private `modsec-wp-audit-final/report.json`; không đưa raw payload/PII vào Git. Nguồn e-commerce Ba Lan 2025 có 178.939 log rows theo nhà phát hành, được ghi metadata-only vì không có nhãn intent theo request và URI đã bỏ query. Không có study/training/threshold tuning mới.

## Review nhãn và nguồn attack — 2026-11-01T07:36:28.147641+07:00

**Formal vẫn NOT_READY; không chạy trainer dài.** SOC-MLD mới đã audit198.082 HTTP observations, nhưng không có nhãn request-bound mới đủ tin cậy; 38 attack-instance IDs chung train/test và rule/time fallback phải được review. Không dùng precomputed future-window/SID features. Raw/provenance giữ private, không tạo traffic mới hoặc cộng observations thành request mới.

Corpus gate hiện yêu cầu evidence review v2 theo từng event: capture + intent provenance + independent semantic review, thêm application oracle nếu khẳng định success/failure. Pending/unknown vẫn null, boolean-only approval không còn mở formal. Tool `scripts/audit-label-evidence.py` kiểm integrity/binding; không tự chứng nhận sự thật hoặc tạo nhãn mới. `scripts/audit-soc-mld.py` audit pinned ZIP offline trong resource envelope, không execute code publisher; kết quả active đã có, không cần chạy lại.

Catalog đã cập nhật source screening và điều kiện balanced independent acceptance. Giữ kín toàn bộ holdout, gồm148WCP case files; scale-admitted0/2M, champion=null, formal_command=null. Xem [report](reports/ATTACK_EVIDENCE_20261101.json), [hợp đồng nhãn](../docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md) và ledger06 mục32. Kết quả model cũ giữ làm bằng chứng, không lặp HPO trên validation đã exposed.

Kiểm chứng cuối: **211 pytest PASS, 0 skip**; Ruff/format/compile/canonical PASS; **53/53 gate kỹ thuật legacy PASS**, corpus formal **NOT_READY/0 eligible** (exit 3 đúng thiết kế). Giữ nguyên SHA của **2.941 file** cũ và source/config freeze trong final test; không sửa hai Web. Handoff format 10, ledger 32.

## Hiện trạng dữ liệu và model — 2026-11-01T06:48:58.523006+07:00

**Chưa sẵn sàng train chính thức hoặc chọn champion.** Đã thêm audit nguồn publisher-benign open-appsec có Apache-2.0: 811.129 record ngoài reserved, 756.548 signature biểu diễn HTTP khác nhau, 54.391 trùng/190 quarantine; 44.437 numeric projections. 148 website case files dự phòng chưa đọc/project/score. Không coi số signature là verified physical requests hoặc automatic training admission.

Frozen weights/threshold MLP 219k và GLU 9,54M trên 13.290 validation/160 case: GLU 5 FP=0,0376%, MLP 174 FP=1,3093%. Ngược với hard negatives lab cũ, GLU FPR 10,73%/MLP 0%. Mô hình có điểm yếu theo miền; nguồn mới chỉ benign nên Recall/F1/PR-AUC không xác định, chưa champion. Trong 139 syntax-benign subset: GLU 2 FP, MLP 34 FP. Giữ toàn bộ primary sample, không retune threshold hoặc HPO từ kết quả này.

**198 pytest PASS/0 skip**, 53 gate kỹ thuật legacy PASS; Student/Security/contracts/Docker giữ nguyên, 2.682 protected SHA giữ nguyên. 0 optimizer update thực mới, không training dài hạn/enforcement. Organization X vẫn unknown; tổng lab 75.150 HTTP giữ nguyên, scale-admitted 0/2M. Cần positive/nhãn/campaign và validation độc lập trước study tiếp.

Xem [report](reports/GENERALIZATION_QUALITY_20261101.json), [handoff format 9](FINAL_TRAINING_HANDOFF.json), [data protocol](../docs/02_DATA_STRATEGY_AND_FEATURE_ENGINEERING.md), ledger 06 mục 31. Root private `ai-training/.artifacts/generalization_quality_20261101/CURRENT_WORK.json` giữ trạng thái tiếp tục. Existing baseline/checkpoint cần frozen source/config/data/environment đúng hash, không force-resume package hiện hành. `formal_command=null`; các lệnh/snapshot phía dưới là lịch sử, không phải authorization chạy formal.

Công cụ mới đọc offline, không gửi traffic đến website gốc: `scripts/import-wcp-http.py` yêu cầu pinned source/provenance/key/protocol và output mới; `scripts/evaluate-wcp-http.py` yêu cầu frozen model registry, validation only và từ chối ghi đè. Không cần chạy lại audit/evaluation đã hoàn tất. Job dữ liệu/eval chạy user cgroup 4 CPU/MemoryMax 16 GiB; ceil toàn luồng≤8 CPU/16 GiB theo runbook.

## Nâng cấp 9,68M / mục tiêu 2M — nghiệm thu kỹ thuật, dữ liệu còn thiếu — 2026-10-30T15:52:59+07:00

**Đã kiểm chứng phần kỹ thuật; chưa hoàn thành mục tiêu dữ liệu/production.**
Chỉ sửa AI và docs. Corpus vẫn **69.345 request duy nhất, một lab**, nhãn scripted
intent; không thêm request hoặc môi trường. Re-extraction v5 không phải dữ liệu mới.
Chưa có review nhãn độc lập, **0 request được admission cho formal scale**; mục tiêu
2M đa dạng chưa đạt. Không nhân bản hoặc cộng các bản projection/cache vào số lượng.

| Giai đoạn | Trạng thái cuối phiên |
| --- | --- |
| Data | Catalog/provenance/replay/holdout checks đã có; corpus 2M và shared-scaler assembly nhiều môi trường còn thiếu |
| Features/architecture/algorithms | v5/207 cột, thêm 18 dynamics; residual SwiGLU **9.675.784** tham số thực; AdamW/smoothing/dropout/warmup-cosine |
| Tests/readiness | **134/134 pytest PASS, 0 skipped**; **53/53 gate kỹ thuật PASS** trên cùng 69k |
| Pilot | 4 neural candidates × 2 epoch, fresh-process resume và reference khớp chính xác; ONNX mọi 69.345 vectors/candidate PASS |
| Evaluation | Calibration 3 campaign, selection 6 campaign; fit không nhìn validation; test quality giữ kín; tree32 iteration đối chứng |
| Integration | Offline shadow512 request PASS, không gọi Web/firewall; live/TLS/receipt-time/response NOT_RUN |
| Formal/champion | NOT_RUN / chưa chọn; không tự chạy ca dài và chưa đủ data gate |
| Cleanup | Chỉ cache tái tạo được: giải phóng 498.14 MiB; giữ raw/checkpoint/log/evidence cũ |

AP selection cao nhất ở lượt ngắn: **gated_residual**. Main challenger
AP **0.997228**, recall **98.92%**, FPR **0.823%**,
p95 ONNX model-only **5.363 ms**. Model lớn không mặc định tốt hơn;
khác biệt thuật toán/regularization không phải thí nghiệm riêng tác dụng số tham số.
Một lab và sáu nhóm selection không chứng minh FPR/zero-day/production generalization.

[Báo cáo đo thực](reports/SCALE_UPGRADE_20261030.json), [handoff hiện hành](FINAL_TRAINING_HANDOFF.json),
ledger06 mục25. Tất cả snapshot cũ bên dưới là lịch sử; không dùng readiness/source
cũ cho source hiện hành hoặc force-resume checkpoint khác contract.

## Bàn giao corpus và mô hình sâu revision 4.1 — 2026-10-30T09:08:21+07:00

| Hạng mục | Kết quả đo thực |
| --- | --- |
| Corpus | 69,345 request; 297,685 observations từ Student, Nginx và Suricata thật |
| Split và nhãn | 69,345 vectors có nhãn được duyệt; train: 41,607 / val: 13,869 / test: 13,869; groups 27/9/9 |
| Đặc trưng | ai-features-4.1 / normalizer 4.1, 189 cột, projection v2; canonical 1.0 giữ nguyên |
| Mô hình | Residual nhỏ đối chứng; MLP 248.072 / DAE 294.717 / gated residual 445.448 tham số |
| Readiness | 53/53 PASS; payload và hard negatives có identity riêng giữa các temporal bands |
| Pilot | 4 mô hình × 5 epoch; resume qua process mới khớp reference; ONNX 69,345/69,345 vectors PASS từng mô hình |
| Kiểm thử và phạm vi | 118 pytest PASS, 0 skipped; giữ nguyên hash 366 file dịch vụ/contract và 1.946 artifact cũ |
| Train dài / chất lượng trên test / deploy | NOT_RUN; chưa chọn Champion Model hoặc nghiệm thu Rust/live/enforcement |

Ứng viên lớn cho thí nghiệm tiếp: **gated_residual** (AP 0.999077, precision 97.61%, recall 99.16%, FPR 0.996%).
Residual đối chứng: AP 0.999165, precision 97.64%, recall 99.55%, FPR 0.986%. Các số đo trên validation còn sơ bộ
vì cùng tập này được dùng để calibration và so sánh ứng viên. Tăng tham số không
bảo đảm tốt hơn; không kéo dài train chỉ để đủ thời gian.

Manifest hiện hành: [FINAL_TRAINING_HANDOFF.json](FINAL_TRAINING_HANDOFF.json).
Xem [báo cáo](reports/PRETRAIN_EXPANDED_20261030.json) và mục 24 của ledger 06. Các snapshot bên dưới là lịch sử.

Lệnh ca tiếp do người dùng tự chạy, **chưa được thực thi**:

```bash
bash /home/trung/projects/idps-web-aws/ai-training/scripts/train-expanded-session.sh gated_residual
```

## Chuẩn bị mạng sâu/corpus 60–80k — revision 4.1

Phạm vi phiên mới chỉ AI và docs. Đã triển khai projection v2 / 189 đặc trưng cùng ba
mạng sâu (248.072/294.717/445.448 tham số), giữ math/checkpoint/cgroup/ONNX contract.
Corpus mới thu từ Student export của HEAD hiện hành, Nginx và Suricata thật;
45 campaign / 27-9-9 groups, 480 giây/campaign và gap 620 giây. Hard-negative payload
identities được tách như attack views, không chỉ kiểm request ID khác nhau.

Source v4/148 cột cũ và các report/pilot trước không được ghi đè hoặc force-resume.
Revision 4.1 tránh gọi hai vector khác thứ tự/số cột bằng cùng contract. Model sâu
chỉ là candidate; không hứa chống overfit, thêm zero-day detection hoặc train
đủ 150 phút. Pilot 5 epoch phải so fresh-process resume với reference và ONNX toàn
bộ vector; test quality giữ kín. Model/threshold không được promote tại đây.

Runbook mới ở đầu [README](README.md). Handoff hiện hành đặt tại
`ai-training/FINAL_TRAINING_HANDOFF.json`; bản có cùng tên trong
`upgrade_20261028` thuộc experiment lịch sử. Ca dài dùng
`train-expanded-session.sh`, chỉ do người vận hành khởi động sau khi gate/pilot
hoàn tất. Trạng thái đo cuối ghi trong report mới và ledger 06 mục 24.

## Nâng cấp sau chẩn đoán — 29/10/2026

Ca11,616giây trước đó không báo lỗi optimizer/checkpoint/ONNX. Model nhỏ và
early stopping giải thích thời gian; chất lượng vẫn hạn chế:59/148cột hằng số,
query payload counters bằng0, campaign có nhiều lặp. Không ép ca đó chạy tiếp.

Đợt mới bổ sung shared numeric EVE bridge, feature/normalizerv4, policy corpus
sâu hơn và weighted residual candidate có train/validation loss history.
30campaign có plan riêng, nhóm18/6/6,480giây thật/campaign và gap620giây thật;
thêm CRUD, đọc public, UA thường đa dạng, batch hợp lệ và hard negatives.
Canonical1.0, Student/Security và artifact cũ giữ riêng. Đây vẫn là lab một host,
scripted intent và tài khoản giả; cần dữ liệu người dùng/traffic đại diện sau này.

Các alias URL decode về cùng payload được kiểm bằng identity hash. Bản trùng ở
holdout sau giữ làm context nhưng không được nhận nhãn training/evaluation;
evidence có danh sách HMAC request key và lý do loại. Không sửa log gốc hoặc
hạ floor để vượt readiness. Corpus cũ được re-project chỉ là phép chẩn đoán.

Re-projection PCAP cũ là phép chẩn đoán riêng: cùng residual5epoch đạt recall
validation95,39%, khi bỏ projection query/URI ở cùng weights/threshold còn26,93%.
Threshold dùng cùng validation nên kết quả sơ bộ; không tính đây là corpus mới,
không dùng để mở khóa formal gate30campaign. AE và weighted loss không mặc định
tốt hơn supervised residual. Thiếu actor/flow có thể tăng false positives mạnh;
phải đọc cả FPR trong sensitivity, không chỉ recall.

Quy trình/lệnh mới ở đầu [README](README.md#workflow-numeric-query--29102026).
Ca tiếp dùng `train-query-session.sh`; ca `train-first-session.sh` bên dưới đã
terminal. Modelv4 cần cùng bridge trước redaction khi chạy thật; Rust serving,
TLS/receipt-time parity và phản ứng IPS chưa được nghiệm thu trong luồng AI.
Report/ledger mới nhất sẽ ghi số liệu thực của corpus/pilot và trạng thái gate.

**Kết quả cuối corpus mới:**46.230request,198.765observations,30campaign,48/48gate
PASS; feature rows46.134 sau96holdout-overlap exclusions. Split27.738/9.150/9.246,
nhóm18/6/6; canonical1.0/profilev4/148cột. Pilot4ứng viên5epoch, exactresume và
ONNX46.134/46.134từng modelPASS. Residual không trọng số có APvalidation cao nhất
0,99875,recall99,23%,FPR0,747%; đây là candidate cho ca tiếp, chưa champion.
Lệnh `train-query-session.sh` dùng residual seed17/patience8/100epoch/max150phút,
8CPU/16GiB; **ca formal mới chưa chạy**. Chất lượng test vẫn niêm phong và chưa
nghiệm thu live. [Báo cáo](reports/PRETRAIN_UPGRADE_20261029.json), ledger06 mục23
ghi source/hash và các lần kiểm tra thực; các snapshot dưới đây là lịch sử.

## Ca residual đầu tiên — 29/10/2026

Đã thực hiện yêu cầu kiểm data rồi chạy ca tối đa **150 phút** trên source `8171289`.
Data gate mới **35/35 PASS**, dataset **19.275 request / 148 features** giữ nguyên hash.
Ca chạy **17:21:05–17:21:17 +07:00**, hoàn thành sau **11,616 giây**, dừng tại
**epoch 14 / step 2.534** do `early_stopping` (patience 8); checkpoint tốt nhất
ở **epoch 6 / step 1.086**. Không ép chạy tiếp để lấp đầy ngân sách thời gian.
Quota thực **8 CPU / 16 GiB**, MemoryHigh 15 GiB, swap 0; có job nền/log riêng và
sleep inhibitor trong lúc chạy. Đã kiểm checkpoint và ONNX parity **19.275/19.275 PASS**.

Validation-only: precision **90,83%**, recall **44,20%**, FPR **0,943%**, AP **0,7757**;
threshold chọn trên cùng validation nên kết quả sơ bộ. **Không mở test metrics,
chưa chọn champion hoặc triển khai Rust/live/enforcement**. Chưa nghiệm thu endurance
150 phút. Xem [báo cáo ca residual](reports/FORMAL_RESIDUAL_20261029.json) và [ledger06 mục22](../docs/06_AI_HANDOFF_AND_RUN_LEDGER.md#22-ca-train-residual-đầu-tiên--29102026). Các mốc “chưa train” ngày28/S0 phía dưới
là lịch sử. Run early-stopped là terminal; không force-resume bằng script ca đầu.

Cập nhật 28/10/2026: luồng AI dùng `ai-features-3` / `ai-normalizer-3`, 148 cột,
canonical event v1.0 giữ nguyên. Báo cáo ngày27 là lịch sử của corpus hai nguồn;
không dùng checkpoint/report cũ để resume với source hoặc dataset mới.
Báo cáo hiện hành: [PRETRAIN_PILOT_20261028.json](reports/PRETRAIN_PILOT_20261028.json), đóng băng sau capture/readiness/pilot; 19.275 request, 35 gate checks và77 testsPASS.

## Luồng ba nguồn thật

1. `lab-start` build bản Student riêng từ Git, DB PostgreSQL rỗng và tài khoản giả.
   Không đọc `.env`, DB hoặc credential của dịch vụ đang dùng.
2. `lab-capture-eve` chuyển Nginx và HTTP client vào **user/network namespace riêng**.
   Backend được nối bằng Unix socket relay riêng. IP127.0.0.10–24 là địa chỉ bind
   thực trong namespace; không sửa timestamp/IP để tạo split. Host networking,
   firewall và cấu hình Student/Security không bị thay.
3. `tcpdump --immediate-mode -i lo` chỉ bắt TCP18881 trong namespace. PCAP riêng tư
   chứa credential/cookie **của fixture giả**: không đưa vào Git hoặc chia sẻ công
   khai. Thư mục0700, PCAP0600, giới hạn512MiB; STOP hoặc lỗi không cấp readiness.
4. `decode-pcap` chạy Suricata8.0.3 offline, một worker, dùng bản config dẫn xuất và
   nguyên bộ9SID của repo. Giữ cả HTTP/flow bình thường, alert và stats. Suricata
   gửi EVE qua Unix socket0600; bộ lọc chỉ giữ response header `X-Request-Id`, mask
   query/path động và UA trước khi ghi `eve.json`. Không ghi cookie/token/body.
5. `lab-finish` đóng băng snapshot, labels/provenance, correlation, split, scaler,
   vectors, readiness, capacity và rule baseline validation. Chế độ ba nguồn dùng
   `three_source_policy.yaml`; corpus ngày27 không qua được gate mới này.
6. `pilot` chạy từng model2epoch rồi **tiến trình mới** resume đến5epoch, so đúng
   weights/Adam/RNG/sampler/scheduler với reference 5 epoch liên tục, export ONNX.
   Chỉ tính metric trên validation; test chỉ được replay để kiểm parity, không
   dùng nhãn test để chọn threshold hoặc chọn model.

## Quyền bắt gói và AppArmor

Máy hiện tại dùng Podman rootless qua lệnh `docker`. `--network host` cùng
NET_RAW/NET_ADMIN không cấp quyền trên host namespace. Cách đã chọn không cần
sudo để mở packet socket trong namespace riêng. Tuy nhiên AppArmor profile
`tcpdump` đã chặn tín hiệu từ Codex (`peer=chatgpt`). Người dùng đã tự bổ sung:

```apparmor
signal (receive) peer=chatgpt,
```

vào `/etc/apparmor.d/local/usr.bin.tcpdump`, reload profile và dừng các probe cũ.
Đây là thay đổi quyền **nhận tín hiệu dừng**, không cấp capture host, không tắt
AppArmor. Máy khác chỉ cần thao tác này nếu kernel audit xác nhận cùng lỗi.
Muốn thu hồi: xóa đúng dòng bổ sung rồi reload profile bằng quản trị hệ thống.
Không chép binary hoặc tắt sandbox để né profile.

## Corpus và feature availability

- 15 campaign × 1.280 request workload, cộng setup/logout: **19.275 request**; nhóm 9/3/3.
- Mỗi campaign420giây thực; các campaign trong cùng band chạy đồng thời, mỗi
  identity có lịch sử riêng. Hai khoảng nghỉ 620 giây thực giữ embargo300giây ở
  hai phía cutoff. Ba role và payload/UA views được phân band trước khi thu.
- Có đọc/ghi hợp lệ, HEAD/OPTIONS bị policy từ chối,404, role denial, tìm kiếm
  Unicode/O'Connor/percent/thuật ngữ kỹ thuật và singleton login typo; attack
  families gồmSQLi/XSS/traversal/command/scanner/auth burst/bulk-read intent.
- `edge_masked_v1`: mọi adapter đều bỏ query lexical và query-original counters,
  chuẩn hóa path cùng cách. Không chọn view raw giàu hơn từ Suricata/lab. Các
  cột query thiếu dữ liệu được ghi đúng trạng thái, không dựng payload giả.
- Flow là **context của flow client đã hoàn tất trước đó**, không là byte/packet
  riêng của request hiện tại. Chỉ dùng flow kết thúc trước request ít nhất65giây
  (closed timeout60giây + biên dự phòng), lookback record300giây. `available_at=max(timestamp EVE, flow.end+65s)` kết hợp hai ràng buộc mà không cộng timeout lần hai; timestamp gốc không bị đổi. Những request warmup vẫn
  missing; không dùng counter đóng flow tương lai để lấp đầy100%.
- Đây là replay theo packet/event time. Receipt-time delay, TLS/vantage, arrival
  reordering và port Rust/live phải được nghiệm thu riêng khi triển khai.

Đồng bộ masking tránh train bằng thông tin không tồn tại khi chạy thật, nhưng
cũng làm một số họ payload trong query không thể phân biệt chỉ bằng metadata.
Rule engine có thể quan sát raw request trong bộ nhớ; AI metadata không được
hứa thay thế bộ rule đó. Query/body model cần telemetry được phê duyệt riêng.

## Ba ứng viên

| Model | Kiến trúc | Vai trò |
|---|---|---|
| MLP cơ sở |148→32→8 | Supervised baseline |
| Autoencoder |148→32→148 | Chỉ fit benign; reconstruction score không phải xác suất attack |
| Residual tabular |148→64→64+skip→8 | Candidate có sức biểu diễn cao hơn; chưa mặc định tốt hơn baseline |

Residual có14.216tham số FP32, dùng ReLU/softmax/CE và Adam hiện có. Params, activations, gradient và optimizer giữFP32; affine reductions tích lũyFP64 rồi roundFP32 trong cảNumPy/ONNX. Cách này xử lý sai lệch BLAS/MLAS gầnzero, vẫn giữtolerance rtol1e-5/atol1e-6. Arithmetic contract ghi trong checkpoint; không force-load các checkpoint của attempt trước bằng source mới. Gradient được
đối chiếu finite difference; optimizer/checkpoint/ONNX có test. Đây là kiến trúc
nhỏ lấy cảm hứng từ residual learning, không phải bản tái lập nguyên xi benchmark
[ResNet cho tabular data](https://arxiv.org/abs/2106.11959). Byte-CNN/TCN vẫn cần
corpus/sequence contract tương ứng; không đưa LLM/Torch/CUDA vào pipeline này.

## Tài nguyên cho ca sắp tới — cập nhật sau pilot

Cấu hình hiện hành là **8 logical CPU**, `CPUQuota=800%`, `Nice=10`,
`MemoryMax=16GiB`, `MemoryHigh=15GiB`, `MemorySwapMax=0`. NumPy/BLAS/OpenMP/
NumExpr dùng tối đa8luồng; ONNX intra-op8, inter-op1 với execution mode sequential
để không nhân hai pool8×8. `--cpus` là alias của `--max-threads`, chấp nhận6–8CPU
trên máy16luồng; bộ guard vẫn kiểm trần nửa CPU affinity và đọc lại cgroup.

16GiB là mức người dùng chỉ định rõ. Hệ điều hành nhìn thấy32.440.909.824byte RAM,
vì vậy16GiB tương đương khoảng**52,96% RAM OS-visible**, không phải chính xác50%.
Guard ghi tỷ lệ thực tế, không đánh đồng32GB với32GiB. Trần16GiB là giới hạn job;
working set không được cấp phát sẵn16GiB. Nhiệt/độ mượt ca dài vẫn cần đo riêng.

Đã chạy **77tests PASS** và probe systemd guard với**0optimizer step**; không
train lại corpus19.275request, không chạy ca chính thức. Báo cáo mới ở
[RESOURCE_GUARD_20261028.json](reports/RESOURCE_GUARD_20261028.json). Các metric và
thông số2CPU/12GiB trong report pilot trước đó giữ nguyên ý nghĩa lịch sử.

Nguồn guard đổi nên đã chạy lại35data-readiness checks, tạo
`dataset-ready/readiness-resource8/readiness.json`. Bản `readiness-final` cũ,
`dataset-ready/prepared` và toàn bộ`pilot-ready` vẫn giữ nguyên byte. Handoff và
script hiện dùng readiness-resource8; checkpoint pilot cũ không được force-resume
bằng source mới. Ca đầu là một experiment mới.

```bash
bash /home/trung/projects/idps-web-aws/ai-training/scripts/train-first-session.sh
```

Ở mốc 28/10, lệnh này **chưa được thực thi**; ca đầu đã chạy ngày29 và dừng sớm như mục cập nhật đầu trang. Mặc định100epoch, patience8, tối đa150phút,
checkpoint300giây; đạt đích/early stopping sớm thì dừng. Nếu run mới đã cólatest
thì script tiếp đúng run tương thích. Không lặp dữ liệu để đủ số giờ.

## Những gate vẫn riêng

`READY_FOR_OFFLINE_PILOT` không là production certification. Corpus vẫn là lab
loopback với tài khoản/dữ liệu giả, scripted intent, một topology và ít campaign
holdout; chưa có independent human realism review hoặc traffic cloud. Cần thêm
realistic sessions, campaign độc lập, TLS/receipt-time parity, FPR/incident-level
review và shadow trước khi chọn champion hoặc bật phản ứng. Không chạm Rust,
firewall, dashboard hay service config trong luồng AI này.

Xem [README](README.md), [report lịch sử27/10](reports/PRETRAIN_20261027.json) và
[ledger06](../docs/06_AI_HANDOFF_AND_RUN_LEDGER.md). Raw/key/Parquet/weights/PCAP
chỉ nằm trong `.artifacts/`, không ở Git; kho artifact chung chưa được cấp.

Lệnh ca đầu lịch sử: `bash ai-training/scripts/train-first-session.sh`. Run đích đã early-stop ngày29; không dùng lại để ép học thêm cùng run.

Artifact được duyệt: `dataset-ready/prepared`, `dataset-ready/readiness-resource8/readiness.json` và `pilot-ready/` (bản readiness-final gốc vẫn được giữ). Xem `.artifacts/upgrade_20261028/FINAL_TRAINING_HANDOFF.json`. Thư mục `dataset`, report `readiness` cũ và `pilot` là các attempt đã fail hoặc stale và đã được dọn theo yêu cầu. Các lệnh NEXT_COMMANDS cũ đã xóa; chỉ dùng script/handoff hiện hành.
