# Bổ sung danh mục CNTT, Giao thông và Năng lượng, Nhiệt

Nguồn: hai file bảng người dùng gửi và bảng 28 dòng Kỹ thuật nhiệt trong hội thoại. Mã custom là quy ước PBL4.

| Khoa | Ngành custom | CTĐT nguồn | Seed ENGINEER | Chờ loại bằng |
|---|---|---:|---:|---:|
| FAC-IT | MAJ-IT | 91 | 31 | 60 |
| FAC-TEE | MAJ-MEC, MAJ-ISE, MAJ-AUTO, MAJ-NAV | 67 | 26 | 41 |
| FAC-TEEN | MAJ-THERM | 28 | 9 | 19 |

## Quyết định ánh xạ

- 186 dòng nguồn được lưu đầy đủ trong ba file JSON; 66 dòng có tên ghi rõ Kỹ sư được seed. 120 dòng còn lại chưa xác định loại bằng, không mặc định Cử nhân.
- Giữ FAC-TEE và FAC-TEEN riêng. Không tự chuyển ngành giữa các khoa.
- Mã nguồn 7520103 xuất hiện ở cả Khoa Cơ khí (AME, đợt trước) và khoa Giao thông/Năng lượng (MEC). Không dùng mã nguồn làm khóa toàn cục; không gộp hai bản ghi.
- Tại FAC-TEE, dùng tên ngành Kỹ thuật cơ khí từ những dòng có tên ngành rõ ràng; Cơ khí động lực và phương tiện đường sắt vẫn là CTĐT của ngành này.
- Tên ngành Kỹ thuật hệ thống công nghiệp và Kỹ thuật ô tô tạm lấy từ tên CTĐT vì cột tên ngành trống. Kỹ thuật tàu thủy chuẩn hóa dấu từ “tàu thuỷ” của nguồn.
- CNTT chỉ có một mã ngành nguồn 7480201: CNPM, HTTT, KHDL/TTNT, ngoại ngữ Nhật… là các CTĐT/biến thể, không tự tạo ngành mới.
- Quản lý Năng lượng thuộc ngành THERM theo mã nguồn 7520115, dùng biến thể EM để không trùng Kỹ thuật nhiệt cùng khóa/bằng.
- Các giá trị 154.5, 153.5, 152.5 được giữ nguyên trong JSON. Schema hiện tại dùng Integer cho tín chỉ, vì vậy cần đổi sang kiểu thập phân trước khi nhập các dòng đó sau khi xác nhận bằng. Không làm tròn hoặc cắt phần lẻ.
- Giữ ngôn ngữ nguồn Tiếng Việt ngay cả khi tên có Anh/Nhật; không suy ngôn ngữ từ tên chương trình.
- Ngôn ngữ, tháng đào tạo, mã nguồn, chuyên ngành và khung CTĐT được lưu trong JSON; chưa thêm vào schema/API. Tín chỉ bắt buộc/tự chọn chưa biết giữ NULL khi insert.
- File Giao thông thiếu STT dòng đầu: gán STT=1 theo vị trí, giữ nguyên các trường dữ liệu còn lại.

## Quy ước biến thể (tối đa 6 ký tự)

`PRG-{shortCode ngành}-{cohort}-ENG[-variantCode]` cho các dòng đã rõ ENGINEER.

| Mã | Ý nghĩa trong danh mục này |
|---|---|
| SE / IS / SEC / CE / NET / DAI | CNPM / HTTT / ATTT / KTMT / Mạng / KHDL và TTNT |
| ANTT / HTN | Giữ nhãn ANTT / HTN nguồn, không tự diễn giải |
| DSE, DIS, DSEC, DCE, DDAI | Đặc thù (hoặc ĐT) + hướng tương ứng |
| CSE, CIS, CSEC, CCE, CNET, CDAI | CLC + hướng tương ứng (nguồn có Đặc thù/ĐT) |
| DT / CLC | Đặc thù / CLC chưa ghi hướng riêng |
| JP / CLCJP / CLCEN | Nhật / CLC Nhật / CLC Anh |
| TALENT | Kỹ sư tài năng |
| ENV / EM / RAIL | Năng lượng & Môi trường / Quản lý Năng lượng / đường sắt tốc độ cao |

Ví dụ: PRG-IT-2020-ENG-DSE và PRG-IT-2020-ENG-CSE cùng tồn tại; PRG-THERM-2025-ENG và PRG-THERM-2025-ENG-EM cùng tồn tại.

## Chạy trong DBeaver

Sau 006 (khoa) và 007 (variant_code), chạy toàn bộ từng file, gồm BEGIN và COMMIT:

1. [009_seed_it_catalog.sql](sql/009_seed_it_catalog.sql)
2. [010_seed_transport_energy_catalog.sql](sql/010_seed_transport_energy_catalog.sql)
3. [011_seed_thermal_catalog.sql](sql/011_seed_thermal_catalog.sql)

008 của Khoa Cơ khí được giữ nguyên. Các seed mới chạy lại không tạo trùng, không thay đổi ID/FK/dữ liệu cũ; gặp dữ liệu khác ánh xạ thì dừng transaction để đối chiếu. Không tự cập nhật hoặc đổi mã danh mục cũ.
Nếu gặp ERROR trong transaction, chạy ROLLBACK trước khi thử lại. Thông báo NOTICE “constraint ... does not exist, skipping” ở 007 là bình thường với DROP CONSTRAINT IF EXISTS.

## Bảng đối chiếu

### FAC-IT

| Mã ngành nguồn | Tên ngành | Mã custom |
|---|---|---|
| 7480201 | Công nghệ thông tin | MAJ-IT |

| STT | Mã CTĐT nguồn | Tên | Tín chỉ | Biến thể | Mã seed / trạng thái |
|---|---|---|---:|---|---|
| 1 | 1024045 | An toàn thông tin trên không gian số K2026 | 150 | SEC | Chờ loại bằng |
| 2 | 1024043 | Công nghệ thông tin (ngoại ngữ Nhật) K2026 | 150 | JP | Chờ loại bằng |
| 3 | 1021037 | Công nghệ Thông tin K2014_ANTT | 153 | ANTT | Chờ loại bằng |
| 4 | 1021035 | Công nghệ Thông tin K2014_HTN | 153 | HTN | Chờ loại bằng |
| 5 | 1021034 | Công nghệ Thông tin K2014_HTTT | 153 | IS | Chờ loại bằng |
| 6 | 1021013 | Công nghệ Thông tin K2014CLC | 158 | CLC | Chờ loại bằng |
| 7 | 1021041 | Công nghệ Thông tin K2015_MANG | 153 | NET | Chờ loại bằng |
| 8 | 1021017 | Công nghệ Thông tin K2015CLC- Anh | 154.5 | CLCEN | Chờ loại bằng |
| 9 | 1021049 | Công nghệ Thông tin K2016_CNPM | 153 | SE | Chờ loại bằng |
| 10 | 1021047 | Công nghệ Thông tin K2016_HTTT | 153 | IS | Chờ loại bằng |
| 11 | 1021024 | Công nghệ Thông tin K2016CLC- Anh | 153.5 | CLCEN | Chờ loại bằng |
| 12 | 1021025 | Công nghệ Thông tin K2016CLC- Nhật | 151 | CLCJP | Chờ loại bằng |
| 13 | 1021058 | Công nghệ Thông tin K2017_CNPM | 153 | SE | Chờ loại bằng |
| 14 | 1021057 | Công nghệ Thông tin K2017_HTTT | 153 | IS | Chờ loại bằng |
| 15 | 1021031 | Công nghệ Thông tin K2017CLC- Anh | 153.5 | CLCEN | Chờ loại bằng |
| 16 | 1021032 | Công nghệ Thông tin K2017CLC- Nhật | 151 | CLCJP | Chờ loại bằng |
| 17 | 1021072 | Công nghệ Thông tin K2018 _ATTT | 153 | SEC | Chờ loại bằng |
| 18 | 1021071 | Công nghệ Thông tin K2018 _CNPM | 153 | SE | Chờ loại bằng |
| 19 | 1021073 | Công nghệ Thông tin K2018CLC Đặc thù_CNPM | 120 | CSE | Chờ loại bằng |
| 20 | 1021074 | Công nghệ Thông tin K2018CLC Đặc thù_HTTT | 120 | CIS | Chờ loại bằng |
| 21 | 1021075 | Công nghệ Thông tin K2018CLC Đặc thù_MẠNG | 120 | CNET | Chờ loại bằng |
| 22 | 1021039 | Công nghệ Thông tin K2018CLC Nhật | 121 | CLCJP | Chờ loại bằng |
| 23 | 1021061 | Công nghệ Thông tin K2019CLC Đặc thù_ATTT | 150 | CSEC | Chờ loại bằng |
| 24 | 1021063 | Công nghệ Thông tin K2019CLC Đặc thù_CNPM | 150 | CSE | Chờ loại bằng |
| 25 | 1021065 | Công nghệ Thông tin K2019CLC Đặc thù_HTTT | 150 | CIS | Chờ loại bằng |
| 26 | 1021066 | Công nghệ Thông tin K2019CLC Đặc thù_KHDL&TTNT | 150 | CDAI | Chờ loại bằng |
| 27 | 1021051 | Công nghệ Thông tin K2019CLC Nhật | 150 | CLCJP | Chờ loại bằng |
| 28 | 1021088 | Công nghệ Thông tin K2020 Đặc thù _ Kỹ sư _CNPM | 180 | DSE | PRG-IT-2020-ENG-DSE |
| 29 | 1021089 | Công nghệ Thông tin K2020 Đặc thù _ Kỹ sư _HTTT | 180 | DIS | PRG-IT-2020-ENG-DIS |
| 30 | 1021086 | Công nghệ Thông tin K2020 Đặc thù _CNPM | 130 | DSE | Chờ loại bằng |
| 31 | 1021087 | Công nghệ Thông tin K2020 Đặc thù _HTTT | 130 | DIS | Chờ loại bằng |
| 32 | 1021092 | Công nghệ Thông tin K2020CLC Đặc thù_ ATTT | 130 | CSEC | Chờ loại bằng |
| 33 | 1021090 | Công nghệ Thông tin K2020CLC Đặc thù_ CNPM | 130 | CSE | Chờ loại bằng |
| 34 | 1021091 | Công nghệ Thông tin K2020CLC Đặc thù_ HTTT | 130 | CIS | Chờ loại bằng |
| 35 | 1021095 | Công nghệ Thông tin K2020CLC Đặc thù_Kỹ sư_ATTT | 180 | CSEC | PRG-IT-2020-ENG-CSEC |
| 36 | 1021093 | Công nghệ Thông tin K2020CLC Đặc thù_Kỹ sư_CNPM | 180 | CSE | PRG-IT-2020-ENG-CSE |
| 37 | 1021094 | Công nghệ Thông tin K2020CLC Đặc thù_Kỹ sư_HTTT | 180 | CIS | PRG-IT-2020-ENG-CIS |
| 38 | 1021055 | Công nghệ Thông tin K2020CLC ĐT - KHDL_TTNT | 130 | CDAI | Chờ loại bằng |
| 39 | 1021078 | Công nghệ Thông tin K2020CLC ĐT- KHDL_TTNT _ Kỹ Sư | 180 | CDAI | PRG-IT-2020-ENG-CDAI |
| 40 | 1021056 | Công nghệ Thông tin K2020CLC Nhật | 130 | CLCJP | Chờ loại bằng |
| 41 | 1021076 | Công nghệ Thông tin K2020CLC Nhật _ Kỹ sư | 180 | CLCJP | PRG-IT-2020-ENG-CLCJP |
| 42 | 1024018 | Công nghệ Thông tin K2021 Đặc thù _ Kỹ sư_CNPM | 180 | DSE | PRG-IT-2021-ENG-DSE |
| 43 | 1024010 | Công nghệ Thông tin K2021 Đặc thù_CNPM | 130 | DSE | Chờ loại bằng |
| 44 | 1021069 | Công nghệ Thông tin K2021CLC Đặc thù - KHDL_TTNT | 130 | CDAI | Chờ loại bằng |
| 45 | 1024015 | Công nghệ Thông tin K2021CLC Đặc thù_ATTT | 130 | CSEC | Chờ loại bằng |
| 46 | 1024014 | Công nghệ Thông tin K2021CLC Đặc thù_CNPM | 130 | CSE | Chờ loại bằng |
| 47 | 1024016 | Công nghệ Thông tin K2021CLC Đặc thù_HTTT | 130 | CIS | Chờ loại bằng |
| 48 | 1024017 | Công nghệ Thông tin K2021CLC Đặc thù_KTMT | 130 | CCE | Chờ loại bằng |
| 49 | 1024019 | Công nghệ Thông tin K2021CLC Đặc thù_Kỹ sư_CNPM | 180 | CSE | PRG-IT-2021-ENG-CSE |
| 50 | 1021098 | Công nghệ Thông tin K2021CLC ĐT- KHDL_TTNT _ Kỹ Sư | 180 | CDAI | PRG-IT-2021-ENG-CDAI |
| 51 | 1021070 | Công nghệ Thông tin K2021CLC Nhật | 130 | CLCJP | Chờ loại bằng |
| 52 | 1021079 | Công nghệ Thông tin K2022 Đặc thù | 130 | DT | Chờ loại bằng |
| 53 | 1024001 | Công nghệ Thông tin K2022 Đặc thù _ Kỹ sư | 180 | DT | PRG-IT-2022-ENG-DT |
| 54 | 1024028 | Công nghệ Thông tin K2022 Đặc thù _ Kỹ sư_ATTT | 180 | DSEC | PRG-IT-2022-ENG-DSEC |
| 55 | 1024027 | Công nghệ Thông tin K2022 Đặc thù _ Kỹ sư_CNPM | 180 | DSE | PRG-IT-2022-ENG-DSE |
| 56 | 1024029 | Công nghệ Thông tin K2022 Đặc thù _ Kỹ sư_HTTT | 180 | DIS | PRG-IT-2022-ENG-DIS |
| 57 | 1024030 | Công nghệ Thông tin K2022 Đặc thù _ Kỹ sư_KTMT | 180 | DCE | PRG-IT-2022-ENG-DCE |
| 58 | 1024024 | Công nghệ Thông tin K2022 Đặc thù_ATTT | 130 | DSEC | Chờ loại bằng |
| 59 | 1024023 | Công nghệ Thông tin K2022 Đặc thù_CNPM | 130 | DSE | Chờ loại bằng |
| 60 | 1024025 | Công nghệ Thông tin K2022 Đặc thù_HTTT | 130 | DIS | Chờ loại bằng |
| 61 | 1024026 | Công nghệ Thông tin K2022 Đặc thù_KTMT | 130 | DCE | Chờ loại bằng |
| 62 | 1021080 | Công nghệ Thông tin K2022 ĐT - KHDL_TTNT | 130 | DDAI | Chờ loại bằng |
| 63 | 1024002 | Công nghệ Thông tin K2022 ĐT - KHDL_TTNT _ Kỹ Sư | 180 | DDAI | PRG-IT-2022-ENG-DDAI |
| 64 | 1021081 | Công nghệ Thông tin K2022 Nhật | 130 | JP | Chờ loại bằng |
| 65 | 1024003 | Công nghệ Thông tin K2022 Nhật _ Kỹ sư | 180 | JP | PRG-IT-2022-ENG-JP |
| 66 | 1021083 | Công nghệ Thông tin K2023 Đặc thù | 130 | DT | Chờ loại bằng |
| 67 | 1024004 | Công nghệ Thông tin K2023 Đặc thù _ Kỹ sư | 180 | DT | PRG-IT-2023-ENG-DT |
| 68 | 1024039 | Công nghệ Thông tin K2023 Đặc thù _ Kỹ sư_ATTT | 180 | DSEC | PRG-IT-2023-ENG-DSEC |
| 69 | 1024038 | Công nghệ Thông tin K2023 Đặc thù _ Kỹ sư_CNPM | 180 | DSE | PRG-IT-2023-ENG-DSE |
| 70 | 1024040 | Công nghệ Thông tin K2023 Đặc thù _ Kỹ sư_HTTT | 180 | DIS | PRG-IT-2023-ENG-DIS |
| 71 | 1024041 | Công nghệ Thông tin K2023 Đặc thù _ Kỹ sư_KTMT | 180 | DCE | PRG-IT-2023-ENG-DCE |
| 72 | 1024035 | Công nghệ Thông tin K2023 Đặc thù_ATTT | 130 | DSEC | Chờ loại bằng |
| 73 | 1024034 | Công nghệ Thông tin K2023 Đặc thù_CNPM | 130 | DSE | Chờ loại bằng |
| 74 | 1024036 | Công nghệ Thông tin K2023 Đặc thù_HTTT | 130 | DIS | Chờ loại bằng |
| 75 | 1024037 | Công nghệ Thông tin K2023 Đặc thù_KTMT | 130 | DCE | Chờ loại bằng |
| 76 | 1021085 | Công nghệ Thông tin K2023 Nhật | 130 | JP | Chờ loại bằng |
| 77 | 1024006 | Công nghệ Thông tin K2023 Nhật _ Kỹ sư | 180 | JP | PRG-IT-2023-ENG-JP |
| 78 | 1024007 | Công nghệ Thông tin K2024 Đặc thù | 130 | DT | Chờ loại bằng |
| 79 | 1024020 | Công nghệ Thông tin K2024 Đặc thù _ Kỹ sư | 180 | DT | PRG-IT-2024-ENG-DT |
| 80 | 1024009 | Công nghệ Thông tin K2024 Nhật | 130 | JP | Chờ loại bằng |
| 81 | 1024022 | Công nghệ Thông tin K2024 Nhật _ Kỹ sư | 180 | JP | PRG-IT-2024-ENG-JP |
| 82 | 1024031 | Công nghệ Thông tin K2025 Đặc thù _ Kỹ sư | 180 | DT | PRG-IT-2025-ENG-DT |
| 83 | 1024033 | Công nghệ Thông tin K2025 Nhật _ Kỹ sư | 180 | JP | PRG-IT-2025-ENG-JP |
| 84 | 1024042 | Công nghệ thông tin K2026 | 150 | — | Chờ loại bằng |
| 85 | 1021084 | Khoa học dữ liệu và Trí tuệ nhân tạo K2023 | 130 | DAI | Chờ loại bằng |
| 86 | 1024005 | Khoa học dữ liệu và Trí tuệ nhân tạo K2023 _ Kỹ Sư | 180 | DAI | PRG-IT-2023-ENG-DAI |
| 87 | 1024008 | Khoa học dữ liệu và Trí tuệ nhân tạo K2024 | 130 | DAI | Chờ loại bằng |
| 88 | 1024021 | Khoa học dữ liệu và Trí tuệ nhân tạo K2024_ Kỹ Sư | 180 | DAI | PRG-IT-2024-ENG-DAI |
| 89 | 1024032 | Khoa học dữ liệu và Trí tuệ nhân tạo K2025_ Kỹ Sư | 180 | DAI | PRG-IT-2025-ENG-DAI |
| 90 | 1024044 | Khoa học dữ liệu và Trí tuệ nhân tạo K2026 | 150 | DAI | Chờ loại bằng |
| 91 | 1024046 | Kỹ sư tài năng Công nghệ thông tin K2026 | 150 | TALENT | PRG-IT-2026-ENG-TALENT |

### FAC-TEE

| Mã ngành nguồn | Tên ngành | Mã custom |
|---|---|---|
| 7520103 | Kỹ thuật cơ khí | MAJ-MEC |
| 7520118 | Kỹ thuật hệ thống công nghiệp | MAJ-ISE |
| 7520130 | Kỹ thuật ô tô | MAJ-AUTO |
| 7520122 | Kỹ thuật tàu thủy | MAJ-NAV |

| STT | Mã CTĐT nguồn | Tên | Tín chỉ | Biến thể | Mã seed / trạng thái |
|---|---|---|---:|---|---|
| 1 | 1033030 | Cơ khí động lực K2026 | 150 | — | Chờ loại bằng |
| 2 | 1033015 | Cơ khí động lực K2020 | 130 | — | Chờ loại bằng |
| 3 | 1033018 | Cơ khí động lực K2020_ Kỹ sư | 180 | — | PRG-MEC-2020-ENG |
| 4 | 1033014 | Cơ khí động lực K2020CLC | 131 | CLC | Chờ loại bằng |
| 5 | 1033020 | Cơ khí động lực K2020CLC_Kỹ sư | 181 | CLC | PRG-MEC-2020-ENG-CLC |
| 6 | 1033016 | Cơ khí động lực K2021 | 130 | — | Chờ loại bằng |
| 7 | 1033022 | Cơ khí động lực K2021_ Kỹ sư | 180 | — | PRG-MEC-2021-ENG |
| 8 | 1033017 | Cơ khí động lực K2021CLC | 130 | CLC | Chờ loại bằng |
| 9 | 1033023 | Cơ khí động lực K2021CLC_Kỹ sư | 180 | CLC | PRG-MEC-2021-ENG-CLC |
| 10 | 1033019 | Cơ khí động lực K2022 | 130 | — | Chờ loại bằng |
| 11 | 1033024 | Cơ khí động lực K2022_Kỹ sư | 180 | — | PRG-MEC-2022-ENG |
| 12 | 1033021 | Cơ khí động lực K2023 | 130 | — | Chờ loại bằng |
| 13 | 1033025 | Cơ khí động lực K2023_Kỹ sư | 180 | — | PRG-MEC-2023-ENG |
| 14 | 1033026 | Cơ khí động lực K2024 | 130 | — | Chờ loại bằng |
| 15 | 1033027 | Cơ khí động lực K2024_Kỹ sư | 180 | — | PRG-MEC-2024-ENG |
| 16 | 1033029 | Cơ khí động lực K2025 | 130 | — | Chờ loại bằng |
| 17 | 1033028 | Cơ khí động lực K2025_Kỹ sư | 180 | — | PRG-MEC-2025-ENG |
| 18 | 1033031 | KT phương tiện đường sắt tốc độ cao K2026 | 180 | RAIL | Chờ loại bằng |
| 19 | 1036012 | Kỹ sư tài năng Kỹ thuật ô tô K2026 | 180 | TALENT | PRG-AUTO-2026-ENG-TALENT |
| 20 | 1033005 | Kỹ thuật cơ khí K2014 | 154 | — | Chờ loại bằng |
| 21 | 1033006 | Kỹ thuật cơ khí K2015 | 153 | — | Chờ loại bằng |
| 22 | 1033008 | Kỹ thuật cơ khí K2016 | 153 | — | Chờ loại bằng |
| 23 | 1033010 | Kỹ thuật cơ khí K2017 | 153 | — | Chờ loại bằng |
| 24 | 1033011 | Kỹ thuật cơ khí K2018 | 153 | — | Chờ loại bằng |
| 25 | 1033012 | Kỹ thuật cơ khí K2018CLC | 120 | CLC | Chờ loại bằng |
| 26 | 1033013 | Kỹ thuật cơ khí K2019CLC | 150 | CLC | Chờ loại bằng |
| 27 | 1035002 | Kỹ thuật hệ thống công nghiệp K2020 | 130 | — | Chờ loại bằng |
| 28 | 1035004 | Kỹ thuật hệ thống công nghiệp K2020_Kỹ sư | 180 | — | PRG-ISE-2020-ENG |
| 29 | 1035003 | Kỹ thuật hệ thống công nghiệp K2021 | 130 | — | Chờ loại bằng |
| 30 | 1035007 | Kỹ thuật hệ thống công nghiệp K2021_Kỹ sư | 180 | — | PRG-ISE-2021-ENG |
| 31 | 1035005 | Kỹ thuật hệ thống công nghiệp K2022 | 130 | — | Chờ loại bằng |
| 32 | 1035008 | Kỹ thuật hệ thống công nghiệp K2022_Kỹ sư | 180 | — | PRG-ISE-2022-ENG |
| 33 | 1035006 | Kỹ thuật hệ thống công nghiệp K2023 | 130 | — | Chờ loại bằng |
| 34 | 1035009 | Kỹ thuật hệ thống công nghiệp K2023_Kỹ sư | 180 | — | PRG-ISE-2023-ENG |
| 35 | 1035010 | Kỹ thuật hệ thống công nghiệp K2024 | 130 | — | Chờ loại bằng |
| 36 | 1035011 | Kỹ thuật hệ thống công nghiệp K2024_Kỹ sư | 180 | — | PRG-ISE-2024-ENG |
| 37 | 1035013 | Kỹ thuật hệ thống công nghiệp K2025 | 130 | — | Chờ loại bằng |
| 38 | 1035012 | Kỹ thuật hệ thống công nghiệp K2025_Kỹ sư | 180 | — | PRG-ISE-2025-ENG |
| 39 | 1035014 | Kỹ thuật hệ thống công nghiệp K2026 | 150 | — | Chờ loại bằng |
| 40 | 1036001 | Kỹ thuật ô tô K2021 | 130 | — | Chờ loại bằng |
| 41 | 1036002 | Kỹ thuật ô tô K2021_Kỹ sư | 180 | — | PRG-AUTO-2021-ENG |
| 42 | 1036003 | Kỹ thuật ô tô K2022 | 130 | — | Chờ loại bằng |
| 43 | 1036005 | Kỹ thuật ô tô K2022_Kỹ sư | 180 | — | PRG-AUTO-2022-ENG |
| 44 | 1036004 | Kỹ thuật ô tô K2023 | 130 | — | Chờ loại bằng |
| 45 | 1036006 | Kỹ thuật ô tô K2023_Kỹ sư | 180 | — | PRG-AUTO-2023-ENG |
| 46 | 1036007 | Kỹ thuật ô tô K2024 | 130 | — | Chờ loại bằng |
| 47 | 1036008 | Kỹ thuật ô tô K2024_Kỹ sư | 180 | — | PRG-AUTO-2024-ENG |
| 48 | 1036010 | Kỹ thuật ô tô K2025 | 130 | — | Chờ loại bằng |
| 49 | 1036009 | Kỹ thuật ô tô K2025_Kỹ sư | 180 | — | PRG-AUTO-2025-ENG |
| 50 | 1036011 | Kỹ thuật ô tô K2026 | 150 | — | Chờ loại bằng |
| 51 | 1032003 | Kỹ thuật Tàu thủy K2014 | 151 | — | Chờ loại bằng |
| 52 | 1032006 | Kỹ thuật Tàu thủy K2017 | 154 | — | Chờ loại bằng |
| 53 | 1032007 | Kỹ thuật Tàu thủy K2018 | 154 | — | Chờ loại bằng |
| 54 | 1032008 | Kỹ thuật Tàu thủy K2019 | 155 | — | Chờ loại bằng |
| 55 | 1032009 | Kỹ thuật Tàu thủy K2020 | 130 | — | Chờ loại bằng |
| 56 | 1032011 | Kỹ thuật Tàu thủy K2020_Kỹ sư | 180 | — | PRG-NAV-2020-ENG |
| 57 | 1032010 | Kỹ thuật Tàu thủy K2021 | 130 | — | Chờ loại bằng |
| 58 | 1032014 | Kỹ thuật Tàu thủy K2021_Kỹ sư | 180 | — | PRG-NAV-2021-ENG |
| 59 | 1032012 | Kỹ thuật Tàu thủy K2022 | 130 | — | Chờ loại bằng |
| 60 | 1032015 | Kỹ thuật Tàu thủy K2022_Kỹ sư | 180 | — | PRG-NAV-2022-ENG |
| 61 | 1032013 | Kỹ thuật Tàu thủy K2023 | 130 | — | Chờ loại bằng |
| 62 | 1032016 | Kỹ thuật Tàu thủy K2023_Kỹ sư | 180 | — | PRG-NAV-2023-ENG |
| 63 | 1032017 | Kỹ thuật Tàu thủy K2024 | 130 | — | Chờ loại bằng |
| 64 | 1032018 | Kỹ thuật Tàu thủy K2024_Kỹ sư | 180 | — | PRG-NAV-2024-ENG |
| 65 | 1032020 | Kỹ thuật Tàu thủy K2025 | 130 | — | Chờ loại bằng |
| 66 | 1032019 | Kỹ thuật Tàu thủy K2025_Kỹ sư | 180 | — | PRG-NAV-2025-ENG |
| 67 | 1032021 | Kỹ thuật Tàu thủy K2026 | 150 | — | Chờ loại bằng |

### FAC-TEEN

| Mã ngành nguồn | Tên ngành | Mã custom |
|---|---|---|
| 7520115 | Kỹ thuật nhiệt | MAJ-THERM |

| STT | Mã CTĐT nguồn | Tên | Tín chỉ | Biến thể | Mã seed / trạng thái |
|---|---|---|---:|---|---|
| 1 | 1043011 | KT Năng lượng & Môi trường K2015 | 153 | ENV | Chờ loại bằng |
| 2 | 1043017 | KT Năng lượng & Môi trường K2017 | 151 | ENV | Chờ loại bằng |
| 3 | 1043019 | KT Năng lượng & Môi trường K2018 | 151 | ENV | Chờ loại bằng |
| 4 | 1043008 | Kỹ thuật Năng lượng & Môi trường K2014 | 153 | ENV | Chờ loại bằng |
| 5 | 1043018 | Kỹ thuật nhiệt K2019CLC | 150 | CLC | Chờ loại bằng |
| 6 | 1043021 | Kỹ thuật nhiệt K2020 | 130 | — | Chờ loại bằng |
| 7 | 1043024 | Kỹ thuật nhiệt K2020_Kỹ sư | 180 | — | PRG-THERM-2020-ENG |
| 8 | 1043020 | Kỹ thuật nhiệt K2020CLC | 130 | CLC | Chờ loại bằng |
| 9 | 1043026 | Kỹ thuật nhiệt K2020CLC_Kỹ sư | 180 | CLC | PRG-THERM-2020-ENG-CLC |
| 10 | 1043022 | Kỹ thuật nhiệt K2021 | 130 | — | Chờ loại bằng |
| 11 | 1043028 | Kỹ thuật nhiệt K2021_Kỹ sư | 180 | — | PRG-THERM-2021-ENG |
| 12 | 1043023 | Kỹ thuật nhiệt K2021CLC | 130 | CLC | Chờ loại bằng |
| 13 | 1043029 | Kỹ thuật nhiệt K2021CLC_Kỹ sư | 180 | CLC | PRG-THERM-2021-ENG-CLC |
| 14 | 1043025 | Kỹ thuật nhiệt K2022 | 130 | — | Chờ loại bằng |
| 15 | 1043030 | Kỹ thuật nhiệt K2022_Kỹ sư | 180 | — | PRG-THERM-2022-ENG |
| 16 | 1043027 | Kỹ thuật nhiệt K2023 | 130 | — | Chờ loại bằng |
| 17 | 1043031 | Kỹ thuật nhiệt K2023_Kỹ sư | 180 | — | PRG-THERM-2023-ENG |
| 18 | 1043032 | Kỹ thuật nhiệt K2024 | 130 | — | Chờ loại bằng |
| 19 | 1043033 | Kỹ thuật nhiệt K2024_Kỹ sư | 180 | — | PRG-THERM-2024-ENG |
| 20 | 1043036 | Kỹ thuật nhiệt K2025 | 130 | — | Chờ loại bằng |
| 21 | 1043034 | Kỹ thuật nhiệt K2025_Kỹ sư | 180 | — | PRG-THERM-2025-ENG |
| 22 | 1043037 | Kỹ thuật nhiệt K2026 | 155 | — | Chờ loại bằng |
| 23 | 1043010 | Kỹ thuật nhiệt K2015 | 152.5 | — | Chờ loại bằng |
| 24 | 1043012 | Kỹ thuật nhiệt K2016 | 152.5 | — | Chờ loại bằng |
| 25 | 1043013 | Kỹ thuật nhiệt K2017 | 152.5 | — | Chờ loại bằng |
| 26 | 1043016 | Kỹ thuật nhiệt K2018CLC | 120 | CLC | Chờ loại bằng |
| 27 | 1043035 | Quản lý Năng lượng K2025_Kỹ sư | 154 | EM | PRG-THERM-2025-ENG-EM |
| 28 | 1046002 | Quản lý năng lượng K2026 | 154 | EM | Chờ loại bằng |


## Kiểm chứng

- Đã kiểm tra trên PostgreSQL 16 tạm: kết hợp seed 008–011 có 9 ngành, 87 CTĐT; riêng đợt này thêm 6 ngành, 66 CTĐT.
- Đối chiếu đủ 66 bản ghi được seed với JSON: mã, tên, ngành/khoa, khóa, bằng, biến thể, tín chỉ và học kỳ.
- Chạy lại seed không đổi ID/dữ liệu, không tạo trùng; cả ba script đều rollback khi gặp chương trình xung đột.
- Hai file đính kèm được đối chiếu đủ 158 dòng, tất cả trường nguồn. 28 dòng nhiệt được chép từ bảng trong hội thoại, giữ nguyên tín chỉ lẻ.
- Chưa chạy vào database thực tế của người dùng. Đợt này chỉ thêm dữ liệu và tài liệu, không thay đổi Java/TypeScript.

## Lớp mẫu ngành CNTT

Chạy toàn bộ [013_seed_it_classes.sql](sql/013_seed_it_classes.sql) khi backend dừng,
sau 005–007 và 009. Script tạo 6 lớp thuộc FAC-IT → MAJ-IT:

| Khóa | Mã lớp | Chương trình kỹ sư |
|---|---|---|
| 2024 | CLS-IT-2024-01 | PRG-IT-2024-ENG-DT |
| 2024 | CLS-IT-2024-02 | PRG-IT-2024-ENG-JP |
| 2024 | CLS-IT-2024-03 | PRG-IT-2024-ENG-DAI |
| 2025 | CLS-IT-2025-01 | PRG-IT-2025-ENG-DT |
| 2025 | CLS-IT-2025-02 | PRG-IT-2025-ENG-JP |
| 2025 | CLS-IT-2025-03 | PRG-IT-2025-ENG-DAI |

Đây là lớp quản lý sinh viên; academic_year chưa gán vì không có năm học cụ thể.
Script giữ ID/FK/trạng thái lớp đã tồn tại, chạy lại không thêm trùng, gặp mã lớp
đã thuộc lớp khác thì rollback. Counter lớp của mỗi khóa được nâng tối thiểu lên 3,
không giảm counter cũ; API tiếp tục cấp số 04 hoặc cao hơn. Chưa áp dụng vào DB người dùng.
