"""完整性校验纯函数测试（直接注入缓存，不连 DB）。"""

from types import SimpleNamespace

import pytest

from app.services.assistant import completeness_rules as rules


@pytest.fixture(autouse=True)
def _restore_cache():
    """隔离进程级缓存，避免污染后续测试文件。"""
    snapshot = dict(rules._cache)
    disabled = rules._disabled_logged
    yield
    rules._cache.clear()
    rules._cache.update(snapshot)
    rules._disabled_logged = disabled


def _set_cache(rules_by_biz):
    rules._cache["rules"] = rules_by_biz
    rules._cache["loaded"] = True
    rules._cache["ts"] = float("inf")


async def test_missing_only_when_value_present_but_empty():
    _set_cache({"order": [("promised_date", "合同交期"), ("shipping_plan", "出货计划")]})
    missing = rules.check_completeness(
        biz_type="order", biz_no="PO1",
        values={"promised_date": None, "shipping_plan": "2026-10-30"},
    )
    assert missing == [("promised_date", "合同交期")]


async def test_unknown_field_not_counted():
    _set_cache({"order": [("promised_date", "合同交期")]})
    assert rules.check_completeness(biz_type="order", biz_no="PO1", values={}) == []


async def test_blank_string_counts_missing():
    _set_cache({"order": [("customer", "客户")]})
    assert rules.check_completeness(
        biz_type="order", biz_no="PO1", values={"customer": "   "}
    ) == [("customer", "客户")]


async def test_sorted_by_field_key():
    _set_cache({"order": [("shipping_plan", "出货计划"), ("promised_date", "合同交期")]})
    missing = rules.check_completeness(
        biz_type="order", biz_no="PO1",
        values={"shipping_plan": None, "promised_date": None},
    )
    assert [k for k, _ in missing] == ["promised_date", "shipping_plan"]


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows=None, error=None):
        self._rows = rows or []
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, *args):
        if self._error:
            raise self._error
        return _FakeResult(self._rows)


async def test_refresh_rules_rejects_unknown_field(monkeypatch):
    row = SimpleNamespace(biz_type="order", field_key="unknown_field", label="未知")
    monkeypatch.setattr(rules, "AsyncSessionLocal", lambda: _FakeSession(rows=[row]))
    await rules.refresh_rules(force=True)
    assert rules._cache["rules"] == {}


async def test_refresh_rules_failure_keeps_previous_snapshot(monkeypatch):
    rules._cache["rules"] = {"order": [("promised_date", "合同交期")]}
    rules._cache["loaded"] = True
    monkeypatch.setattr(
        rules, "AsyncSessionLocal", lambda: _FakeSession(error=RuntimeError("db down"))
    )
    await rules.refresh_rules(force=True)
    assert rules._cache["rules"] == {"order": [("promised_date", "合同交期")]}
