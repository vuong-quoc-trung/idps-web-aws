package com.pbl4.studentweb.common.code;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

/** Internal allocation scope, not an academic entity or relationship. */
@Entity
@Table(name = "code_counters")
@org.hibernate.annotations.Check(name = "ck_code_counter_nonnegative", constraints = "last_value >= 0")
@Getter @Setter
public class CodeCounter {
    @Id @Column(length = 80) private String scope;
    @Column(name = "last_value", nullable = false) private long lastValue;
    protected CodeCounter() {}
    public CodeCounter(String scope) { this.scope = scope; }
}
