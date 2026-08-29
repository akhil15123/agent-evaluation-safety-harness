import pytest

from agent_harness.loaders import SuiteValidationError, suite_from_dict


def test_rejects_duplicate_case_ids():
    with pytest.raises(SuiteValidationError, match="Duplicate"):
        suite_from_dict({"name": "x", "cases": [{"id": "a", "prompt": "1"}, {"id": "a", "prompt": "2"}]})


def test_rejects_unknown_policy_field():
    with pytest.raises(SuiteValidationError, match="Unknown"):
        suite_from_dict({"name": "x", "policy": {"magic": True}, "cases": [{"id": "a", "prompt": "1"}]})
