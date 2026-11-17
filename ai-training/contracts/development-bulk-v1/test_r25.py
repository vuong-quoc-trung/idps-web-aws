"""Regression for the R25 finite lexical projection and external role fences."""

import io
import numpy as np
import pytest
from r25_features import lexical, SPECS, screened


def test_indicator_order_and_dtype():
    assert len(SPECS) == len(set(n for n,_ in SPECS)) == 32
    a=lexical("/shop?q=union%20select%20x%20from%20users")
    assert a.dtype == np.uint8 and a.shape == (32,)
    assert a[0] == a[1] == a[2] == 1
    np.testing.assert_array_equal(a,lexical("/shop?q=union%20select%20x%20from%20users"))


@pytest.mark.parametrize("key",["password","token","api_key","email","credential"])
def test_sensitive_field_never_changes_feature(key):
    np.testing.assert_array_equal(lexical("/shop?"+key+"=union%20select"),lexical("/shop"))


def test_decode_and_field_names_are_not_features():
    assert lexical("/shop?q=%2575nion%2520select")[1] == 1
    assert not lexical("/shop?union=abc")[1]
    assert "person@example.com" not in "".join(screened("/shop?q=person@example.com"))


def test_opaque_and_long_values_are_excluded():
    assert not any(lexical("/shop?q=" + "unionselect"*30))


def test_external_train_fence():
    from r25_external import source_path
    with pytest.raises(ValueError):
        source_path("csic_2010_anomalousTrafficTest.txt")
    with pytest.raises(ValueError):
        source_path("xml_test.txt")


def test_pkdd_record_state_machine():
    from r25_external import pkdd_requests
    rows=list(pkdd_requests(io.BytesIO(b"Start - Id: 1\nclass: Valid\nGET /a HTTP/1.1\nBody: hello\nEnd - Id: 1\n")))
    assert rows == [("GET","/a")]
    with pytest.raises(ValueError):
        list(pkdd_requests(io.BytesIO(b"Start - Id: 2\nclass: Attack\nGET /b HTTP/1.1\nEnd - Id: 2\n")))


def test_supervisor_uses_contract_phase_names(tmp_path):
    from r25_supervise import adapter_command
    from idps_ai.training.resource_contract import PHASES
    for phase in ("experiment","verify"):
        command=adapter_command(tmp_path,phase,30)
        assert command[command.index("--phase")+1] in PHASES


@pytest.mark.parametrize("payload",[
    b"Start - Id: 1\nclass: Valid\nGET /a HTTP/1.1\n",
    b"Start - Id: 1\nclass: Valid\nGET /a HTTP/1.1\nEnd - Id: 2\n",
    b"Start - Id: 1\nclass: Valid\nGET /a HTTP/1.1\nStart - Id: 2\n",
])
def test_pkdd_incomplete_or_conflicting_record_refused(payload):
    from r25_external import pkdd_requests
    with pytest.raises(ValueError):
        list(pkdd_requests(io.BytesIO(payload)))
