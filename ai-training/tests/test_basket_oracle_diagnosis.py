"""Non-mutating Oracle diagnosis/classification fixtures, no network or model fit."""

import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "basket_diagnostic", Path(__file__).parents[1] / "scripts/diagnose-basket-oracle.py"
)
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


def state():
    return {
        **{
            k: True
            for k in [
                "user_exists",
                "basket_exists",
                "basket_owned_by_authenticated_user",
                "product_exists",
                "quantity_record_exists",
                "stock_at_least_requested",
                "limit_allows_requested",
            ]
        },
        "existing_pair_rows": 1,
        "existing_pair_quantities": [2],
        "owned_basket_total_items": 3,
        "indexes": [{"unique": True, "columns": ["BasketId", "ProductId"]}],
    }


def test_known_unique_conflict_requires_actual_error_and_preconditions():
    before = state()
    r = d.classify(500, {"exception_class": "SequelizeUniqueConstraintError"}, before, dict(before))
    assert r["verified"] and r["root_cause"] == "TEST_FIXTURE_ERROR" and r["state_unchanged"]
    assert not d.classify(500, {"exception_class": "TypeError"}, before, dict(before))["verified"]
    assert not d.classify(
        200, {"exception_class": "SequelizeUniqueConstraintError"}, before, dict(before)
    )["verified"]


def test_missing_state_or_side_effects_prevent_causal_claim():
    before = state()
    for key in ["basket_owned_by_authenticated_user", "product_exists", "stock_at_least_requested"]:
        bad = dict(before)
        bad[key] = False
        assert not d.classify(
            500, {"exception_class": "SequelizeUniqueConstraintError"}, bad, dict(bad)
        )["verified"]
    changed = dict(before, existing_pair_quantities=[1])
    assert not d.classify(
        500, {"exception_class": "SequelizeUniqueConstraintError"}, before, changed
    )["verified"]
    assert not d.classify(
        500, {"exception_class": "SequelizeUniqueConstraintError"}, dict(before, indexes=[]), before
    )["verified"]


def test_sanitizer_keeps_only_error_category_and_known_locations():
    secret = "private-test-token@example.invalid"
    raw = json.dumps(
        {
            "error": {
                "name": "SequelizeUniqueConstraintError",
                "message": secret,
                "sql": secret,
                "parent": {"code": "SQLITE_CONSTRAINT", "sql": secret},
                "stack": f"Error: {secret}\n at /juice-shop/build/routes/basketItems.js:96:22\n at /secret/location.js:10:1",
                "errors": [
                    {"path": "BasketId", "value": secret},
                    {"path": "ProductId", "value": secret},
                    {"path": secret, "value": secret},
                ],
            }
        }
    ).encode()
    safe = d.safe_error(raw)
    assert secret not in str(safe) and "/secret/" not in str(safe)
    assert safe["exception_class"] == "SequelizeUniqueConstraintError"
    assert safe["database_category"] == "SQLITE_CONSTRAINT"
    assert safe["unique_basket_product_fields"] == ["BasketId", "ProductId"]
    assert safe["stack_locations"] == [{"file": "basketItems.js", "line": 96, "column": 22}]


def test_bad_or_arbitrary_error_is_unknown_not_success():
    assert d.safe_error(b"not-json")["exception_class"] == "UNKNOWN"
    assert (
        d.safe_error(b'{"error":{"name":"arbitrary-secret","message":"private"}}')[
            "exception_class"
        ]
        == "UNKNOWN"
    )


def test_inline_SQL_witness_uses_pinned_node_readonly_and_valid_JS_escapes():
    code = next(c for c in d.db_state.__code__.co_consts if isinstance(c, str) and "let s=" in c)
    assert "split('\n')" not in code
    assert "split('\\n')" in code
    assert "sql.OPEN_READONLY" in code
    assert "app_listener3000_in_namespace" in code
    assert "/nodejs/bin/node" in str(d.db_state.__code__.co_consts)
    assert not any(x in code.upper() for x in ["INSERT INTO", "UPDATE BASKET", "DELETE FROM"])
