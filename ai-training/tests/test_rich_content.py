from idps_ai.features.rich_content import rich_request


def test_sensitive_values_and_identity_not_persisted():
    a, da = rich_request(
        "POST",
        "/login?password=FirstSecret123&q=hello",
        "Authorization: Bearer FirstSecret123 User-Agent: AgentName999 Host: alice.example",
        "password=FirstSecret123&message=Alice",
    )
    b, db = rich_request(
        "POST",
        "/login?password=OtherSecret456&q=hello",
        "Authorization: Bearer OtherSecret456 User-Agent: OtherName888 Host: bob.example",
        "password=OtherSecret456&message=Bob",
    )
    assert a == b
    assert da["redacted_query_fields"] == db["redacted_query_fields"] == 1
    assert da["body_redacted"] and db["body_redacted"]
    assert all(secret not in a for secret in ("FirstSecret", "alice.example", "Alice"))


def test_rich_syntax_retains_security_difference_without_raw_words():
    normal, _ = rich_request("GET", "/item?id=123", None, None)
    attack, _ = rich_request("GET", "/item?id=1%27%20UNION%20SELECT%20foo", None, None)
    scanner, _ = rich_request("GET", "/item", "User-Agent: sqlmap/1.7", None)
    assert normal != attack
    assert "union" in attack and "select" in attack
    assert "123" not in normal and "foo" not in attack
    assert "sqlmap" in scanner


def test_unrecognized_method_withheld():
    content, _ = rich_request("UnrecognizedSecret", "/", None, None)
    assert "UnrecognizedSecret" not in content
    assert "method OTHER" in content
