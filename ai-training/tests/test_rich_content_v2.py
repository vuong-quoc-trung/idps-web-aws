from idps_ai.features.rich_content_v2 import rich_request_v2


def test_login_body_structure_separates_attack_attempt_from_invalid_account():
    benign, _ = rich_request_v2(
        "POST",
        "/rest/user/login",
        None,
        '{"email":"nobody+pilot@example.invalid","password":"wrong-for-lab"}',
    )
    attack, _ = rich_request_v2(
        "POST", "/rest/user/login", None, '{"email":"\u0027 or 1=1--","password":"wrong-for-lab"}'
    )
    assert benign != attack
    assert " or " in attack
    assert "nobody" not in benign and "example.invalid" not in benign
    assert "wrong-for-lab" not in benign and "wrong-for-lab" not in attack


def test_private_values_still_hidden_across_variants():
    a, _ = rich_request_v2(
        "POST", "/api", None, '{"token":"FirstSecret123","email":"alice@example.com"}'
    )
    b, _ = rich_request_v2(
        "POST", "/api", None, '{"token":"OtherSecret456","email":"bob@example.com"}'
    )
    assert a == b
    assert "FirstSecret" not in a and "alice" not in a
