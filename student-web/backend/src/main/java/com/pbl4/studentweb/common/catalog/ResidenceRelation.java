package com.pbl4.studentweb.common.catalog;

public enum ResidenceRelation {
    CHU_HO("Chủ hộ"),
    O_CUNG_GIA_DINH("Ở cùng gia đình"),
    THUE_NHA("Thuê nhà"),
    O_NHO("Ở nhờ"),
    KY_TUC_XA("Ký túc xá"),
    KHAC("Khác");
    private final String label;
    ResidenceRelation(String label) { this.label = label; }
    public String label() { return label; }
}
