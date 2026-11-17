import numpy as np
import pytest
from r26_features import FULL_WIDTH, URI_WIDTH, content_extension, histogram, project, uri_tokens


def test_content_missing_and_observed_empty_differ():
    missing, meta = content_extension()
    empty, observed = content_extension("", "")
    assert not missing.any() and meta["body_state"] == "missing"
    assert empty[-15] == empty[-2] == empty[-1] == 1
    assert observed["body_state"] == "observed"


@pytest.mark.parametrize(
    "body", ['{"password":"union select"}', "token=abc", "csrf=abc", "username=x&message=abc"]
)
def test_secret_body_withheld(body):
    values, state = content_extension(None, body)
    assert not values.any()
    assert state["body_state"] == "privacy_withheld"


def test_secret_query_and_header_values_excluded():
    a = uri_tokens("/api?password=union%20select&email=user@example.com&q=hi")
    b = uri_tokens("/api?q=hi")
    assert a == b
    first, _ = content_extension("Host: host1\nAuthorization: Bearer secret\nCookie: name=1", None)
    second, _ = content_extension("Host: host2\nAuthorization: Bearer other\nCookie: name=2", None)
    np.testing.assert_array_equal(first, second)


def test_dtype_ordering_and_same_request_views():
    a, _ = project("/shop?q=hello", "POST")
    b, _ = project("/shop?q=hello", "POST", "Content-Type: application/json", '{"x":1}')
    assert a.shape == b.shape == (FULL_WIDTH,)
    assert a.dtype == b.dtype == np.float32
    np.testing.assert_array_equal(a[:URI_WIDTH], b[:URI_WIDTH])
    assert not a[URI_WIDTH:].any()
    assert b[URI_WIDTH:].any()


def test_finite_alphabet_and_saturation():
    tokens = uri_tokens("/a?q=veryprivateperson12345")
    assert "veryprivateperson12345" not in tokens
    a = histogram(["w"] * 1024, 0)
    assert a.shape == (64,) and a.min() >= 0 and a.max() <= 1
    np.testing.assert_array_equal(a, histogram(["w"] * 1024, 0))


def test_invalid_content_type_refused():
    with pytest.raises(ValueError):
        content_extension({"a": "b"}, "")


def test_json_header_values_cannot_forge_observed_header_names():
    baseline, _ = content_extension('{"Host":"example"}', None)
    spoof, _ = content_extension('{"Host":"\\"Content-Type\\":\\"fake\\""}', None)
    np.testing.assert_array_equal(baseline, spoof)
    malformed, state = content_extension('{"Host":', None)
    assert not malformed.any() and state["headers_state"] == "malformed"


def test_recalibrating_already_calibrated_graph_preserves_ssa_and_values(tmp_path):
    import onnx
    from onnx import TensorProto, helper, numpy_helper
    from r20_calibration import apply
    from r26_calibration import append_sigmoid

    from idps_ai.export.onnx import cpu_session

    graph = helper.make_model(
        helper.make_graph(
            [
                helper.make_node("Sigmoid", ["input"], ["probabilities"]),
                helper.make_node("Squeeze", ["probabilities", "axis"], ["score"]),
            ],
            "test",
            [helper.make_tensor_value_info("input", TensorProto.FLOAT, [None, 1])],
            [
                helper.make_tensor_value_info("score", TensorProto.FLOAT, [None]),
                helper.make_tensor_value_info("probabilities", TensorProto.FLOAT, [None, 1]),
            ],
            [numpy_helper.from_array(np.array([1], np.int64), "axis")],
        ),
        opset_imports=[helper.make_opsetid("", 18)],
        ir_version=9,
    )
    calibration = {"kind": "platt", "slope": 0.8, "intercept": 0.1}
    first = append_sigmoid(calibration, graph)
    second = append_sigmoid(calibration, first)
    onnx.checker.check_model(second, full_check=True)
    path = tmp_path / "calibrated.onnx"
    onnx.save(second, path)
    x = np.array([[-2.0], [0.0], [2.0]], np.float32)
    expected = apply(calibration, apply(calibration, 1 / (1 + np.exp(-x[:, 0]))))
    actual = cpu_session(path, 1).run(["score"], {"input": x})[0]
    np.testing.assert_allclose(actual, expected, atol=1e-6)


def test_mixed_vector_keeps_both_publisher_labels_and_original_count():
    from r26_learning import cells

    x = np.array([[0], [0], [0], [1], [1], [1]], np.float32)
    y = np.array([0, 0, 1, 0, 1, 1], np.int8)
    vectors, labels, mass, report = cells(x, y, 1)
    assert report["originals"] == 6 and report["unique_vectors"] == 2
    assert report["mixed_vectors"] == 2 and report["minority_mass"] == 2
    assert len(vectors) == 4
    for cls in (0, 1):
        np.testing.assert_allclose(mass[labels == cls].sum(), 0.5)


def test_missing_content_views_conserve_source_class_mass_and_originals():
    from r26_learning import make_training

    x = np.zeros((2, FULL_WIDTH), np.float32)
    x[1, 0], x[:, -1] = 1, 1
    y = np.array([0, 1], np.int8)
    a, labels, weights, reports = make_training([(x, y, None)], FULL_WIDTH)
    assert reports[0]["originals"] == 2 and len(a) == 4
    np.testing.assert_array_equal(a[:2, :URI_WIDTH], a[2:, :URI_WIDTH])
    assert not a[2:, URI_WIDTH:].any()
    for cls in (0, 1):
        np.testing.assert_allclose(weights[labels == cls].sum(), weights.sum() / 2)


def test_raw_source_envelope_has_explicit_unknown_body_and_refuses_bad_headers():
    from r26_notes import parse_request

    assert parse_request("POST /login HTTP/1.1\nHost: example")[3] is None
    assert parse_request("POST /login HTTP/1.1\nHost: example\n\n")[3] == ""
    with pytest.raises(ValueError):
        parse_request("GET / HTTP/1.1\nmalformed")
