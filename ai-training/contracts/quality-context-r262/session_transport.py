"""Guest Oracle: existing HttpOnly sessions need not receive a new Set-Cookie.

The transport tracks the HttpOnly attribute only from a real server Set-Cookie.
No cookie or token is fabricated. Subsequent login still needs valid CSRF and
the independent JDBC/session-rotation Oracle. Values never leave the guest.
"""


def install(pilot):
    original = pilot.semantic_oracle

    def semantic(rule, expected, response, before, after):
        valid, basis = original(rule, expected, response, before, after)
        if valid or rule != "csrf":
            return valid, basis
        check = response.get("csrf_check", {})
        continued = (
            expected == response.get("status") == 200
            and response.get("continued_http_only_session") is True
            and all(
                check.get(k) is True for k in ("json_type", "header_declaration", "masked_uuid")
            )
        )
        return continued, "CSRF_SEMANTIC_EXISTING_HTTPONLY_SESSION" if continued else basis

    pilot.semantic_oracle = semantic
