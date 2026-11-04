from idps_ai.features.safe_content import symbolic_request


def test_secrets_and_header_values_do_not_enter_symbolic_content():
    first, a = symbolic_request(
        "POST",
        "/login?password=FirstSecret123&term=select",
        "Cookie: first-secret Host: private.example",
        "password=FirstSecret123&message=hello",
    )
    second, b = symbolic_request(
        "POST",
        "/login?password=DifferentSecret456&term=select",
        "Cookie: second-secret Host: other.example",
        "password=DifferentSecret456&message=world",
    )
    assert first == second
    assert a["redacted_query_fields"] == b["redacted_query_fields"] == 1
    assert a["body_redacted"] and b["body_redacted"]
    assert "FirstSecret" not in first and "private.example" not in first


def test_content_symbols_retain_attack_syntax_without_plaintext_identity():
    benign, _ = symbolic_request("GET", "/item?id=123", None, None)
    attack, _ = symbolic_request("GET", "/item?id=1%27%20UNION%20SELECT%20passwd", None, None)
    assert benign != attack
    assert "union" in attack and "select" in attack
    assert "123" not in benign


def test_header_body_values_are_structural_only():
    content, detail = symbolic_request(
        "POST",
        "/submit",
        "User-Agent: UniqueName999 Content-Type: application/json",
        '{"q":"<script>alert(1)</script>","x":"Alice"}',
    )
    assert "UniqueName" not in content and "Alice" not in content
    assert "script" in content and detail["body_nonempty"]


def test_unrecognized_method_is_not_retained_as_plaintext():
    content, _ = symbolic_request("UniqueCredentialWord", "/", None, None)
    assert "UniqueCredentialWord" not in content
    assert "method OTHER" in content
