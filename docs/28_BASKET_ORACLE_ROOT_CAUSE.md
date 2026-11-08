# Basket Oracle HTTP500 root cause — 2026-11-08

**CASE A — root cause VERIFIED: TEST_FIXTURE_ERROR.** Fixture đăng nhập seeded admin,
nhưng yêu cầu CREATE một ProductId/BasketId pair đã có sẵn. Actual database unique
constraint từ chối INSERT, application trả500; Oracle đúng khi không báo success.
**Không sửa fixture/app/Oracle hoặc chạy lại preflight/main trong milestone này.**

Baseline `2ba9722`, branch `feature/ai-idps-shadow-integration`, initial worktree sạch,
remote đồng bộ. [Machine report](../ai-training/reports/BASKET_ORACLE_ROOT_CAUSE_20261108.json),
[bounded diagnosis](../ai-training/scripts/diagnose-basket-oracle.py),
[non-mutating tests](../ai-training/tests/test_basket_oracle_diagnosis.py).

## Existing evidence và application contract

Reuse locked `control-03`: POST `/api/BasketItems/`, JSON ProductId1, own BasketId từ
login, quantity1. Previous run `request-v3-grounded-20261108-r1` có actual500 và
`owned_product_quantity_response=false`; intent/outcomeUNKNOWN, no server exception
được retained, main0. Các containers cũ đã cleanup nên state lịch sử không còn để
query; không claim read lại exact original database. Source pin và reproduction
trên fresh identical image là evidence mới, không sửa hoặc relabel old receipts.

Image installed:
`docker.io/bkimminich/juice-shop@sha256:318714401c46c3c0a2458b5dccfc84af8e4839181d1a723701f8a6822b19294f`.
Đọc source từ image và đối chiếu source trong container thực thi; hashes khớp.

| Layer | Contract của installed version |
|---|---|
| Method/route | Authenticated POST `/api/BasketItems`; trailing slash thực tế tới cùng create handler |
| Authentication | JWT `isAuthorized`, `appendUserId`; logged-in user mapped vào request |
| JSON fields | ProductId, BasketId, quantity; raw JSON parser giữ fields để tạo item |
| Ownership | Own BasketId phải bằng user.bid; mismatch branch401 |
| Product/quantity | Quantities row của ProductId phải tồn tại, đủ stock và per-user limit; overstock/limit branch400 |
| Mutation | `BasketItemModel.build(...)` rồi `.save()`; **CREATE/INSERT**, không increment/upsert |
| Success | Handler trả JSON `{status:success,data:addedBasketItem}`, default200 |
| Duplicate pair | Unique composite ProductId/BasketId; save exception → `next(error)` →500 |
| Readback | Authenticated GET `/rest/basket/:id`, products cùng BasketItem quantity |

`build/data/datacreator.js` seed admin basket có ProductId1 quantity2; relation
`belongsToMany(...through BasketItemModel)` tạo pair uniqueness. Actual SQLite PRAGMA
index query xác nhận unique index trên **ProductId + BasketId**; không chỉ suy từ ORM.
Source `build/routes/basketItems.js:79` là actual awaited `.save()` nơi exception
propagate. Source foreign keys tới Baskets/Products được query riêng.

## Bounded reproduction và read-only state

Execution **`request-v3-basket-diagnostic-20261108-r1`**, disposable Juice lab,
internal owned network, loopback19280, no production services. **Hai HTTP diagnostic
transactions**: original duplicate POST và authenticated GET own basket. Một HTTP
login setup hoàn tất riêng; không readiness HTTP polling. Không có third Basket probe.

| Read-only prerequisite / state | Before POST | After POST / GET |
|---|---|---|
| User exists, basket exists và owned by authenticated user | True | True |
| ProductId1 exists | True | True |
| Quantity row, stock≥1, allowed limit≥1 | True | True |
| Existing target pair | **1row, quantity2** | **1row, quantity2** |
| Total items trong own basket |3|3|
| Unique index(ProductId,BasketId) |True|True|

Witness mở SQLite với **OPEN_READONLY**, chỉ SELECT/PRAGMA; IDs/credentials/token
chỉ ởRAM/stdin, output chỉ booleans/counts/quantities/schema. `PRAGMA foreign_keys=false`
trên **witness connection** không chứng minh setting connection của application;
không suy causality từ flag đó. Actual failure là UNIQUE, không phải FK.

POST giữ nguyên original schema/path/quantity, được backend xử lý qua auth/ownership/
quantity checks rồi save. Sanitized response evidence:

- HTTP **500**.
- Exception **SequelizeUniqueConstraintError**.
- Database category **SQLITE_CONSTRAINT**.
- Constraint fields **BasketId, ProductId**.
- Stack locations: `query.js:185`, `query-interface.js:308`, `model.js:2490`,
  **`basketItems.js:79`**; không persist SQL/messages/full stack hoặc field values.

GET trả **200**, owned basket identity và DB state khớp; target quantity vẫn2,
không thỏa expected added quantity1. Không có successful basket mutation, không
DELETE/repair seed rows, không thay constraints hoặc application exception handling.

Causal order được xác minh:

```text
Seeded admin basket already contains product1 at quantity2
→ fixture requests a new CREATE(product1, own basket, quantity1)
→ INSERT conflicts with composite unique pair
→ SequelizeUniqueConstraintError / SQLITE_CONSTRAINT
→ existing application error handler returns HTTP500
→ Oracle correctly refuses success; evidence remains UNKNOWN
```

Root **TEST_FIXTURE_ERROR**; manifestation **APPLICATION_ERROR500**. Existing app
có thể có error-response design chưa lý tưởng cho duplicate create, nhưng không
map500→400/409 hoặc sửa backend trong diagnosis task. Không phải wrong owner,
missing product/stock/quantity, absent seeds, route/parser failure hoặc positive
Oracle misinterpretation trong reproduction này. Không khẳng định mọi500 chung cause.

## Oracle decision và correction đề xuất

Oracle success cần: verified identity/ownership, valid product/stock/limit,
**pair absent trước CREATE**, expected success response, actual pair newly persisted
với quantity1 và authenticated readback. Request schema hợp lệ không đủ bảo đảm
state preconditions; HTTP success hoặc authenticated basket read không chứng minh
CREATE mới đã thành công. Intent, rejected execution outcome và security label tách
biệt. Diagnostic failure không được đổi thành benign success hoặc attack sample.

Current Oracle refusal đúng. **BASKET_ORACLE=BLOCKED_FIXTURE_PRECONDITION** vì chưa
thực hiện một valid CREATE với initially-absent pair. Success200 được xác minh từ
source contract, không nói đã có positive CREATE trong lượt này. Basket preflight
**NOT_RERUN**; historical UNKNOWN giữ byte-identical.

**Một corrective task nhỏ nhất:** chuẩn bị dedicated authenticated test account/
own basket ban đầu rỗng trong disposable lab; read-only assert ProductId1 pair absent,
đủ stock/ownership trước existing CREATE, rồi kiểm một POST/readback khi được yêu cầu.
Giữ ProductId1/quantity1, method/endpoint và dynamic own BasketId binding. Không xóa
seed rows, đổiPOST→PUT/upsert hoặc đổi ProductId/expected status để épPASS.

Đây là fixture/environment assumption revision, phải version/review/bind rõ trước
capture; không sửa silent parent precommitment/role/Oracle hoặc lập luận fresh ID
là independent novelty. Task này **chỉ đề xuất**, chưa sửa account setup hay chạy
positive replay/main. Các campaign workflows khác chưa được qualify thêm.

Một secondary tooling limitation đã xác minh: image distroless entrypoint là
`/nodejs/bin/node`, `node` không có trongPATH. Existing `product_witness` dùng `node`
quaPATH nên có blocker riêng khi tới product preflight; **không phải cause của Basket
HTTP500**, không sửa nó trong milestone này hoặc claim product Oracle đãPASS.

## Tooling corrections và giới hạn evidence

Các attempts trước actual reproduction không hoàn tất Basket requests:

1. Read-only helper gọi `node` quaPATH → executable127, sửa riêng diagnostic tool
   sang installed absolute binary; application/collector cũ không đổi.
2. Seed DB readiness không đồng nghĩa HTTP listener ready → login connection reset;
   không có Basket dispatch. Có tối đa1setup login dispatch response unconfirmed,
   ghi riêng thay vì che count.
3. JS readiness check bị escape lỗi trong Python string; sửa raw string, kiểm
   `node --check` bằng đúng pinned runtime,0HTTP. Prior logs/artifacts giữ nguyên.

Sau explicit namespace listener+seed checks, final run hoàn tất đúng2Basketdiagnostics
và1login setup. Không thêm HTTP probes sau khi root cause đủ evidence. Không thu raw
body/headers/response/cookies/token hoặc direct secret digests. Fresh diagnostic IDs
và ordinal session_group-0001 chỉ giữlocal, không admit vào dataset. Identity là
collector receipt + actual authenticated handler/read-only binding, không PCAP hoặc
independent external reviewer. Independent human review vẫnPENDING.

Private evidence `.local-dev/basket-oracle-20261108/verified-reproduction/` có source
snapshots, readonly before/after, sanitized errors, numeric receipts và manifest.
Manifest fingerprint:
`0c23e60cfc23e72cfcda48c62a8a8dfa26393df7a8873c34e4e2dec78ea0b74d`.

## Dataset, safety và trạng thái cuối

Parent fingerprint giữ
`5c95afd6555502725a10ddb4a77d2c4f80a039dfd5c93448bb658252b5367e0d`:
TRAIN43/37views, CAL13/13, DEV86/83. New main receipts0, new derivative0, new trained
checkpoint0; strict splits/roles/Oracle history không đổi. Both older UNKNOWN
receipts giữ nguyên. No sealed access, model scores, training, promotion, AWS hoặc
AI firewall enforcement. Frozen models/encoders/thresholds, Rules/Policy/Web/Nginx/
Suricata/correlation, oldPGvolumes và published Releases giữ nguyên;158pinsPASS.

13targeted testsPASS: state/constraint causal checks, rejection khi thiếu prereqs hoặc
có side effects, sensitive error redaction, JS readonly/runtime contract; Ruff/format
PASS. Quota25%onecore, cutoff85°C, reserve4GiB; peak64°C trong workloads trước final
report, sensor/watchdog healthy. No sustained-training thermal claim. All owned lab
containers/network/listener/watchdogs dừng; không đóng user applications hoặc thay
host/auth/security protections. No seed repairs hoặc app behavior changes.

| Final status | Result |
|---|---|
| BASKET_ROOT_CAUSE | VERIFIED |
| BASKET_APPLICATION_CONTRACT | VERIFIED |
| BASKET_ORACLE | BLOCKED_FIXTURE_PRECONDITION |
| BASKET_PREFLIGHT | NOT_RERUN |
| MAIN_CAPTURE | NOT_STARTED |
| REQUEST_V3_TRAINING | NOT_STARTED |
| DATASET_COVERAGE | UNCHANGED |

Dừng tại root-cause diagnosis; không tự thực hiện corrective task.
