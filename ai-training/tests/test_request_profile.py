import json

import pytest


def test_request_profile_preserves_unknown_parameter_structure_but_not_secrets():
    from idps_ai.features.request_view import project_request

    a = project_request(
        "/shop?discount=1%27%20OR%2017%3D17--&pwd=canary-password&api_key=canary-key", "GET"
    )
    b = project_request(
        "/shop?entirelyDifferentKey=1%27%20OR%2017%3D17--&pwd=other-password", "GET"
    )
    assert a["numbers"] == b["numbers"]
    assert a["numbers"]["sql_line_comment_count"] == 1
    assert a["numbers"]["parameter_count"] == 1
    assert a["availability"]["dropped_fields"] == 2
    assert "canary" not in json.dumps(a)
    assert not any(
        n.startswith(("role_", "ua_", "status_", "flow_", "ip_", "user_")) for n in a["numbers"]
    )


def test_request_profile_blocks_encoded_sensitive_keys_and_has_no_fake_clock():
    from idps_ai.features.request_view import project_request, validate_view

    a = project_request("/api?%2570%2577%2564=canary&term=hello&term=world", "GET")
    assert a["numbers"]["parameter_count"] == 2
    assert a["numbers"]["duplicate_parameter_count"] == 1
    assert "timestamp" not in a
    validate_view(a)
    with pytest.raises(ValueError):
        project_request("/" * 8193, "GET")
    assert project_request("/api?pwd=canary")["numbers"]["query_lexical_available"] == 0
    a["implementation_sha256"] = "changed"
    with pytest.raises(ValueError, match="implementation"):
        validate_view(a)
