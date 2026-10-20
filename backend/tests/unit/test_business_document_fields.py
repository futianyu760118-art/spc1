"""共享台账自定义字段校验纯函数测试。"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.common.business_document_fields import (
    WIDGETS,
    generate_field_key,
    normalize_options,
    validate_custom_fields,
)


def config(key, widget, **kwargs):
    return SimpleNamespace(
        field_key=key,
        label=kwargs.get("label", key),
        widget=widget,
        required=kwargs.get("required", False),
        options=kwargs.get("options"),
    )


def assert_400(func, *args, **kwargs):
    with pytest.raises(HTTPException) as exc_info:
        func(*args, **kwargs)
    assert exc_info.value.status_code == 400


def test_required_field_missing_rejected():
    assert_400(validate_custom_fields, [config("name", "text", required=True)], {})


def test_optional_empty_text_dropped():
    assert validate_custom_fields([config("name", "text")], {"name": "  "}) == {}


def test_number_rejects_bool():
    assert_400(validate_custom_fields, [config("qty", "number")], {"qty": True})


def test_number_accepts_zero():
    assert validate_custom_fields([config("qty", "number")], {"qty": 0}) == {"qty": 0}


def test_number_accepts_float():
    assert validate_custom_fields([config("qty", "number")], {"qty": 1.5}) == {"qty": 1.5}


def test_number_rejects_non_numeric_string():
    assert_400(validate_custom_fields, [config("qty", "number")], {"qty": "1.5"})


def test_number_rejects_non_finite_float():
    assert_400(validate_custom_fields, [config("qty", "number")], {"qty": float("inf")})
    assert_400(validate_custom_fields, [config("qty", "number")], {"qty": float("nan")})


def test_date_must_be_iso():
    assert_400(validate_custom_fields, [config("due", "date")], {"due": "2026/10/19"})


def test_date_rejects_non_canonical_iso():
    assert_400(validate_custom_fields, [config("due", "date")], {"due": "20261019"})


def test_date_returns_normalized_value():
    assert validate_custom_fields([config("due", "date")], {"due": " 2026-10-19 "}) == {
        "due": "2026-10-19"
    }


def test_boolean_false_preserved():
    assert validate_custom_fields([config("flag", "boolean")], {"flag": False}) == {"flag": False}


def test_blank_strings_become_none():
    configs = [
        config("due", "date"),
        config("level", "select", options=["A"]),
        config("qty", "number"),
    ]
    assert validate_custom_fields(configs, {"due": "  ", "level": "", "qty": " "}) == {}


def test_select_value_must_be_in_options():
    cfg = config("level", "select", options=["A", "B"])
    assert validate_custom_fields([cfg], {"level": "A"}) == {"level": "A"}
    assert_400(validate_custom_fields, [cfg], {"level": "C"})


def test_unknown_key_rejected():
    assert_400(validate_custom_fields, [config("name", "text")], {"unknown": "x"})


def test_values_must_be_mapping():
    assert_400(validate_custom_fields, [config("name", "text")], ["name"])


def test_current_values_must_be_mapping():
    assert_400(validate_custom_fields, [config("name", "text")], {}, ["name"])


def test_merge_current_values_for_required():
    cfg = config("name", "text", required=True)
    assert validate_custom_fields([cfg], None, {"name": "old"}) == {"name": "old"}


def test_partial_update_keeps_current_required_value():
    configs = [config("name", "text", required=True), config("memo", "text")]
    assert validate_custom_fields(configs, {"memo": "new"}, {"name": "old"}) == {
        "name": "old",
        "memo": "new",
    }


def test_explicit_none_clears_optional_field():
    cfg = config("memo", "text")
    assert validate_custom_fields([cfg], {"memo": None}, {"memo": "old"}) == {}


def test_required_field_explicit_none_rejected():
    cfg = config("name", "text", required=True)
    assert_400(validate_custom_fields, [cfg], {"name": None}, {"name": "old"})


def test_configs_generator_supported():
    configs = (cfg for cfg in [config("name", "text")])
    assert validate_custom_fields(configs, {"name": "value"}) == {"name": "value"}


def test_normalize_options():
    assert normalize_options("select", [" A ", "", "B"]) == ["A", "B"]
    assert_400(normalize_options, "select", [])
    assert normalize_options("text", ["A"]) is None


def test_normalize_options_deduplicates():
    assert normalize_options("select", ["A", "A", " B "]) == ["A", "B"]


def test_widgets_and_generated_field_key():
    assert WIDGETS == {"text", "textarea", "number", "date", "select", "boolean"}
    key = generate_field_key()
    assert key.startswith("field_")
    assert len(key) == 14
