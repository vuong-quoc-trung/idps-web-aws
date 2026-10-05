package com.pbl4.studentweb.common.catalog;

public enum Religion {
    KHONG("Không"),
    PHAT_GIAO("Phật giáo"),
    CONG_GIAO("Công giáo"),
    TIN_LANH("Tin Lành"),
    CAO_DAI("Cao Đài"),
    PHAT_GIAO_HOA_HAO("Phật giáo Hòa Hảo"),
    HOI_GIAO("Hồi giáo"),
    BA_LA_MON("Bà-la-môn"),
    TINH_DO_CU_SI_PHAT_HOI("Tịnh độ Cư sĩ Phật hội"),
    BUU_SON_KY_HUONG("Bửu Sơn Kỳ Hương"),
    TU_AN_HIEU_NGHIA("Tứ Ân Hiếu Nghĩa"),
    BAHA_I("Baha’i"),
    KHAC("Khác");
    private final String label;
    Religion(String label) { this.label = label; }
    public String label() { return label; }
}
