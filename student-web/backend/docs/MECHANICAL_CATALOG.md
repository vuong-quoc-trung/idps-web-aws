# Danh mục Khoa Cơ khí

Nguồn: bảng 55 dòng người dùng cung cấp. Đây là mã custom nội bộ PBL4, không thay thế mã ngành/CTĐT gốc.

| Mã ngành nguồn | Tên ngành | shortCode | Mã custom | Số CTĐT |
|---|---|---|---|---|
| 7520103 | Cơ khí hàng không | AME | MAJ-AME | 12 |
| 7510202 | Công nghệ chế tạo máy | MFG | MAJ-MFG | 19 |
| 7520114 | Kỹ thuật cơ điện tử | MTE | MAJ-MTE | 24 |

AME = Aviation Mechanical Engineering; MFG = Manufacturing; MTE = Mechatronics Engineering.
Tên ngành Cơ khí hàng không được tạm lấy từ tên chương trình vì cột tên ngành nguồn để trống.

## Quy tắc và dữ liệu thiếu

- Mã CTĐT: `PRG-{shortCode ngành}-{cohort}-{ENG/BSC/MSC}[-variantCode]`.
- Chương trình thường không có hậu tố; CLC dùng `CLC`, HTDN dùng `HTDN`, kỹ sư tài năng dùng `TALENT`.
- `variantCode` là custom 1–6 chữ/số ASCII, bắt đầu bằng chữ; backend chuẩn hóa trim/uppercase.
- 21 tên có “Kỹ sư” được gán ENGINEER. 34 dòng khác giữ degreeType=null trong file nguồn và chưa seed vào bảng chương trình, chờ xác nhận. Không suy loại bằng từ 120/130/150/180 tín chỉ.
- Không tự chia tổng tín chỉ thành bắt buộc/tự chọn. Hai trường này giữ NULL khi thêm mới.
- File JSON giữ đủ mã gốc, tên gốc, ngôn ngữ, tháng bắt đầu/kết thúc, chuyên ngành và khung CTĐT. Các thông tin ngoài schema hiện tại chỉ lưu trong JSON, chưa hiển thị qua API.
- Thời gian tháng/năm được chuẩn hóa YYYY-MM; không tự tạo ngày hoặc tính lại số học kỳ.
- Bản ghi mới active=true để có thể sử dụng danh mục; không suy trạng thái hoạt động từ ngày kết thúc khóa.

## Áp dụng

1. Dừng backend, chạy `sql/007_program_variants.sql` sau 001–006.
2. Chạy `sql/008_seed_mechanical_catalog.sql`: thêm 3 ngành và 21 CTĐT đã rõ loại bằng.
3. Khởi động backend mới. Form CTĐT hỗ trợ mã phân biệt chương trình.

Seed có transaction và có thể chạy lại. Giữ ID, FK, active và dữ liệu hiện có; gặp tên/mã/nội dung mâu thuẫn thì rollback để đối chiếu. Không tự chuyển ngành cũ hoặc đổi mã đang dùng.
Chưa áp dụng vào database của người dùng.

## Đối chiếu toàn bộ chương trình

| STT | Mã CTĐT nguồn | Tên chương trình | Mã custom / trạng thái |
|---|---|---|---|
| 1 | 1017014 | Cơ khí hàng không (HTDN, dạy và học bằng TA) K2026 | Chờ xác nhận loại bằng |
| 2 | 1017001 | Cơ khí hàng không K2020 | Chờ xác nhận loại bằng |
| 3 | 1017003 | Cơ khí hàng không K2020_Kỹ sư | PRG-AME-2020-ENG |
| 4 | 1017004 | Cơ khí hàng không K2021_Kỹ sư | PRG-AME-2021-ENG |
| 5 | 1017005 | Cơ khí hàng không K2022 | Chờ xác nhận loại bằng |
| 6 | 1017007 | Cơ khí hàng không K2022_Kỹ sư | PRG-AME-2022-ENG |
| 7 | 1017008 | Cơ khí hàng không K2023_Kỹ sư | PRG-AME-2023-ENG |
| 8 | 1017009 | Cơ khí hàng không K2024 | Chờ xác nhận loại bằng |
| 9 | 1017010 | Cơ khí hàng không K2024_Kỹ sư | PRG-AME-2024-ENG |
| 10 | 1017012 | Cơ khí hàng không K2025 | Chờ xác nhận loại bằng |
| 11 | 1017011 | Cơ khí hàng không K2025_Kỹ sư | PRG-AME-2025-ENG |
| 12 | 1017013 | Cơ khí hàng không K2026 | Chờ xác nhận loại bằng |
| 13 | 1013005 | Công nghệ chế tạo máy K2014 | Chờ xác nhận loại bằng |
| 14 | 1013008 | Công nghệ chế tạo máy K2015 | Chờ xác nhận loại bằng |
| 15 | 1013010 | Công nghệ chế tạo máy K2016 | Chờ xác nhận loại bằng |
| 16 | 1013011 | Công nghệ chế tạo máy K2017 | Chờ xác nhận loại bằng |
| 17 | 1013012 | Công nghệ chế tạo máy K2018 | Chờ xác nhận loại bằng |
| 18 | 1013013 | Công nghệ chế tạo máy K2019 | Chờ xác nhận loại bằng |
| 19 | 1013014 | Công nghệ chế tạo máy K2020 | Chờ xác nhận loại bằng |
| 20 | 1013016 | Công nghệ chế tạo máy K2020_ Kỹ sư | PRG-MFG-2020-ENG |
| 21 | 1013015 | Công nghệ chế tạo máy K2021 | Chờ xác nhận loại bằng |
| 22 | 1013019 | Công nghệ chế tạo máy K2021_ Kỹ sư | PRG-MFG-2021-ENG |
| 23 | 1013017 | Công nghệ chế tạo máy K2022 | Chờ xác nhận loại bằng |
| 24 | 1013020 | Công nghệ chế tạo máy K2022_ Kỹ sư | PRG-MFG-2022-ENG |
| 25 | 1013018 | Công nghệ chế tạo máy K2023 | Chờ xác nhận loại bằng |
| 26 | 1013021 | Công nghệ chế tạo máy K2023_ Kỹ sư | PRG-MFG-2023-ENG |
| 27 | 1013022 | Công nghệ chế tạo máy K2024 | Chờ xác nhận loại bằng |
| 28 | 1013023 | Công nghệ chế tạo máy K2024_ Kỹ sư | PRG-MFG-2024-ENG |
| 29 | 1013025 | Công nghệ chế tạo máy K2025 | Chờ xác nhận loại bằng |
| 30 | 1013024 | Công nghệ chế tạo máy K2025_ Kỹ sư | PRG-MFG-2025-ENG |
| 31 | 1013026 | Công nghệ chế tạo máy K2026 | Chờ xác nhận loại bằng |
| 32 | 1014030 | Kỹ sư tài năng KT Cơ Điện tử K2026 | PRG-MTE-2026-ENG-TALENT |
| 33 | 1014007 | Kỹ thuật Cơ Điện tử K2015 | Chờ xác nhận loại bằng |
| 34 | 1014008 | Kỹ thuật Cơ Điện tử K2016 | Chờ xác nhận loại bằng |
| 35 | 1014009 | Kỹ thuật Cơ Điện tử K2017 | Chờ xác nhận loại bằng |
| 36 | 1014010 | Kỹ thuật Cơ Điện tử K2018 | Chờ xác nhận loại bằng |
| 37 | 1014011 | Kỹ thuật Cơ Điện tử K2018CLC | Chờ xác nhận loại bằng |
| 38 | 1014012 | Kỹ thuật Cơ Điện tử K2019CLC | Chờ xác nhận loại bằng |
| 39 | 1014013 | Kỹ thuật Cơ Điện tử K2020 | Chờ xác nhận loại bằng |
| 40 | 1014017 | Kỹ thuật Cơ Điện tử K2020_kỹ sư | PRG-MTE-2020-ENG |
| 41 | 1014014 | Kỹ thuật Cơ Điện tử K2020CLC | Chờ xác nhận loại bằng |
| 42 | 1014019 | Kỹ thuật Cơ Điện tử K2020CLC_Kỹ sư | PRG-MTE-2020-ENG-CLC |
| 43 | 1014015 | Kỹ thuật Cơ Điện tử K2021 | Chờ xác nhận loại bằng |
| 44 | 1014021 | Kỹ thuật Cơ Điện tử K2021_kỹ sư | PRG-MTE-2021-ENG |
| 45 | 1014016 | Kỹ thuật Cơ Điện tử K2021CLC | Chờ xác nhận loại bằng |
| 46 | 1014022 | Kỹ thuật Cơ Điện tử K2021CLC_Kỹ sư | PRG-MTE-2021-ENG-CLC |
| 47 | 1014018 | Kỹ thuật Cơ Điện tử K2022 | Chờ xác nhận loại bằng |
| 48 | 1014023 | Kỹ thuật Cơ Điện tử K2022_Kỹ sư | PRG-MTE-2022-ENG |
| 49 | 1014020 | Kỹ thuật Cơ Điện tử K2023 | Chờ xác nhận loại bằng |
| 50 | 1014024 | Kỹ thuật Cơ Điện tử K2023_Kỹ sư | PRG-MTE-2023-ENG |
| 51 | 1014025 | Kỹ thuật Cơ Điện tử K2024 | Chờ xác nhận loại bằng |
| 52 | 1014026 | Kỹ thuật Cơ Điện tử K2024_Kỹ sư | PRG-MTE-2024-ENG |
| 53 | 1014028 | Kỹ thuật Cơ Điện tử K2025 | Chờ xác nhận loại bằng |
| 54 | 1014027 | Kỹ thuật Cơ Điện tử K2025_Kỹ sư | PRG-MTE-2025-ENG |
| 55 | 1014029 | Kỹ thuật Cơ Điện tử K2026 | Chờ xác nhận loại bằng |

## Kiểm chứng

- 44 test backend đạt, gồm kiểm tra API tạo chương trình thường/CLC cùng ngành, khóa, bằng; chuẩn hóa, đọc/sửa biến thể và từ chối mã trùng hoặc biến thể sai.
- Frontend `npm run build` đạt.
- Đối chiếu 55/55 dòng JSON với bảng nguồn.
- Migration 007 và seed 008 đã thử trên PostgreSQL 16 tạm với schema danh mục: 3 ngành/21 CTĐT, chạy lại không thay đổi ID/dữ liệu, rollback khi gặp chương trình mâu thuẫn, CHECK từ chối biến thể sai.
- Chưa chạy trên database thực tế của dự án.
