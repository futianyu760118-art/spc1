"""执行面推理对外接口（reasoning.analyze / cancel / task）集成测试。

覆盖任务书§五验收点：HMAC 鉴权、结构化结论 + evidence_refs + data_as_of/confidence、
无证据结论被拒、rule_based 未接通 503、取消联动 490、超时 504、空结果 404、审计留痕。
LLM 以 monkeypatch 替换（_invoke_reasoning_llm 为服务层单点），不依赖真实大模型。
"""

import asyncio
import time
from datetime import date, datetime

import pytest_asyncio

from tests._common_external import build_headers, generate_signature

ANALYZE = "/api/v1/external/reasoning/analyze"
CANCEL = "/api/v1/external/reasoning/tasks/{task_id}/cancel"
STATUS = "/api/v1/external/reasoning/tasks/{task_id}"

ORDER_NO = "HJY-2601"
ORDER_LINE_REF = f"control-platform://order/{ORDER_NO}/line/1"
KITTING_RESULT_REF = f"control-platform://kitting/result/{ORDER_NO}:1"


def _base_body(**overrides):
    body = {
        "prompt": f"分析订单 {ORDER_NO} 的交付风险",
        "task_type": "order_delivery_analysis",
        "context": {"businessObjectRef": f"business://order/{ORDER_NO}"},
        "constraints": {"read_only": True, "require_evidence": True},
    }
    body.update(overrides)
    return body


async def signed_post(client, path, endpoint_code, key, json_body=None):
    """POST 签名：签名串 = timestamp+app_key+endpoint_code+query_string（body 不参与，query 为空）"""
    timestamp = int(time.time())
    _, signature = generate_signature(timestamp, key["app_key"], key["app_secret"], endpoint_code, "")
    return await client.post(path, json=json_body, headers=build_headers(key["app_key"], signature, timestamp))


async def signed_get(client, path, endpoint_code, key):
    timestamp = int(time.time())
    _, signature = generate_signature(timestamp, key["app_key"], key["app_secret"], endpoint_code, "")
    return await client.get(path, headers=build_headers(key["app_key"], signature, timestamp))


def _canned_analysis(include_fabricated=True):
    conclusions = [
        {
            "matter": "关键物料尚未齐套",
            "evidence_refs": [KITTING_RESULT_REF, ORDER_LINE_REF],
            "risk": "预计影响交付3天",
            "recommendation": "建议采购负责人核实到货承诺，需人工确认",
            "confidence": "high",
        }
    ]
    if include_fabricated:
        conclusions.append({
            "matter": "无证据支撑的结论",
            "evidence_refs": ["control-platform://fabricated/ref"],
            "confidence": "high",
        })
    return {
        "summary": "存在缺料导致的延期风险",
        "conclusions": conclusions,
    }


@pytest_asyncio.fixture
async def reasoning_seeded(db):
    """订单 + 明细 + 齐套结果 + 缺料 + 质量异常（每用例先清表，保证可重复）。"""
    from sqlalchemy import delete

    from app.models.exception.quality_issue import QualityIssue
    from app.models.material.kitting import KittingResult, KittingShortage
    from app.models.order.sale_order import SaleOrder, SaleOrderLine

    for table in (KittingShortage, KittingResult, QualityIssue, SaleOrderLine, SaleOrder):
        await db.execute(delete(table))
    await db.commit()

    order = SaleOrder(
        order_no=ORDER_NO, line_no="1", customer="客户A", product_code="P-100",
        product_name="产品A", order_qty=100, completed_qty=10, status="open",
        promised_date=date(2026, 10, 30), risk_level="red",
    )
    db.add(order)
    await db.flush()
    db.add_all([
        SaleOrderLine(sale_order_id=order.id, order_no=ORDER_NO, line_no="1",
                      product_code="P-100", order_qty=100, status="open", batch_no="B-2601"),
        KittingResult(
            demand_no=ORDER_NO, demand_line_no="1", product_code="P-100",
            kit_status="SHORTAGE", kit_rate_by_item=60.0, shortage_item_count=1,
            risk_level="red", key_material_shortage=1,
            allocation_run_id="pytest-run", calculated_at=datetime.now(),
        ),
        KittingShortage(
            demand_no=ORDER_NO, demand_line_no="1", material_code="M-001",
            material_name="关键物料", required_qty=100, available_qty=40,
            future_supply_qty=0, shortage_qty=60, shortage_reason="INSUFFICIENT_STOCK",
            supplier_name="供应商甲", is_key_material=1, allocation_run_id="pytest-run",
        ),
        QualityIssue(
            issue_no="QI-R-001", status="open", workflow_status="创建",
            submit_dept="品质部", submit_date=date(2026, 10, 10), submitter="张三",
            order_no=ORDER_NO, product_code="P-100", defect_type="尺寸超差",
            description="来料尺寸超差", is_deleted=False,
        ),
    ])
    await db.commit()


@pytest_asyncio.fixture
def patch_llm(monkeypatch):
    """把 LLM 调用替换为可编排的假实现；返回 (set_impl) 供用例注入。"""
    from app.services.reasoning import service as rs

    holder = {"impl": None}

    async def fake_invoke(prompt, timeout_s):
        if holder["impl"] is None:
            raise AssertionError("测试未注入 LLM 假实现")
        # 服务层契约：返回 (分析结果, token 用量)；假实现只管结果，用量置空
        return (await holder["impl"](prompt, timeout_s), {})

    monkeypatch.setattr(rs, "_invoke_reasoning_llm", fake_invoke)

    def set_impl(impl):
        holder["impl"] = impl

    return set_impl


async def _analysis_impl(prompt, timeout_s):
    from app.services.reasoning import service as rs
    return rs.ReasoningAnalysis.model_validate(_canned_analysis())


# ═══════════════════════════════════════════
# 鉴权
# ═══════════════════════════════════════════

async def test_missing_auth_401(ext_client):
    r = await ext_client.post(ANALYZE, json=_base_body())
    assert r.status_code == 401


async def test_endpoint_not_authorized_403(ext_client, external_keys):
    r = await signed_post(ext_client, ANALYZE, "reasoning.analyze", external_keys["orders"], _base_body())
    assert r.status_code == 403


async def test_prompt_too_long_422(ext_client, external_keys):
    r = await signed_post(
        ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"],
        _base_body(prompt="长" * 2001),
    )
    assert r.status_code == 422


# ═══════════════════════════════════════════
# 参数与约束校验（信封 400）
# ═══════════════════════════════════════════

async def test_read_only_false_rejected(ext_client, external_keys):
    r = await signed_post(
        ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"],
        _base_body(constraints={"read_only": False}),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 400 and "read_only" in body["message"]


async def test_unknown_task_type_rejected(ext_client, external_keys):
    r = await signed_post(
        ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"],
        _base_body(task_type="hack_analysis"),
    )
    assert r.json()["code"] == 400


async def test_missing_anchor_rejected(ext_client, external_keys):
    r = await signed_post(
        ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"],
        _base_body(context={}),
    )
    assert r.json()["code"] == 400


# ═══════════════════════════════════════════
# 主链路
# ═══════════════════════════════════════════

async def test_happy_path_with_evidence_validation(ext_client, external_keys, reasoning_seeded, patch_llm, db):
    patch_llm(_analysis_impl)
    r = await signed_post(
        ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"],
        _base_body(task_id="happy-1", request_id="req-happy-1"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0, body
    data = body["data"]
    assert data["task_id"] == "happy-1" and data["status"] == "succeeded"
    assert data["request_id"] == "req-happy-1"
    assert data["summary"] == "存在缺料导致的延期风险"
    # 无有效证据引用的结论被拒（验收§五.4）
    assert len(data["conclusions"]) == 1
    assert data["conclusions"][0]["evidence_refs"] == [KITTING_RESULT_REF, ORDER_LINE_REF]
    assert data["dropped_conclusions"] == 1
    assert data["evidence_refs"] and KITTING_RESULT_REF in data["evidence_refs"]
    # 数据时效与置信度（验收§五.3）
    assert data["data_as_of"] is not None
    assert data["data_as_of"].endswith("+08:00")
    assert data["data_confidence"] in ("high", "medium")
    assert data["llm"]["called"] is True
    # 用量透传（执行面 run_complete.usage → Hub 用量台账；假 LLM 用量为空 → 全 0）
    assert data["usage"]["modelId"] == data["llm"]["model"] or data["usage"]["modelId"] == ""
    assert set(data["usage"].keys()) == {"modelId", "tokensIn", "cachedTokens", "tokensOut"}

    # 审计留痕：任务记录证明实际调用大模型（验收§五.2）
    from sqlalchemy import select

    from app.models.basicdata.reasoning import ReasoningTask
    record = (
        await db.execute(select(ReasoningTask).where(ReasoningTask.task_id == "happy-1"))
    ).scalar_one()
    assert record.status == "succeeded"
    assert record.llm_called == 1
    assert record.dropped_conclusion_count == 1
    assert record.evidence_json and record.tool_calls_json
    assert all(tc.get("read_only") for tc in record.tool_calls_json)


async def test_require_evidence_false_keeps_unevidenced_low(ext_client, external_keys, reasoning_seeded, patch_llm):
    patch_llm(_analysis_impl)
    r = await signed_post(
        ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"],
        _base_body(constraints={"read_only": True, "require_evidence": False}),
    )
    data = r.json()["data"]
    assert len(data["conclusions"]) == 2
    unevidenced = [c for c in data["conclusions"] if not c["evidence_refs"]]
    assert unevidenced and unevidenced[0]["confidence"] == "low"


async def test_empty_result_404_not_no_risk(ext_client, external_keys, patch_llm):
    patch_llm(_analysis_impl)
    r = await signed_post(
        ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"],
        _base_body(context={"businessObjectRef": "business://order/NOT-EXIST"}),
    )
    body = r.json()
    assert body["code"] == 404 and body["data"] is None
    assert "无可用证据" in body["message"] and "不代表无风险" in body["message"]


async def test_llm_not_configured_503(ext_client, external_keys, reasoning_seeded, monkeypatch, db):
    """provider=rule_based（未接真实大模型）必须 503，绝不伪装成推理结果（验收§五.2）。"""
    from sqlalchemy import select

    from app.models.basicdata.reasoning import ReasoningTask
    from app.services.reasoning import service as rs

    monkeypatch.setattr(rs.ai_service, "current_provider", lambda: "rule_based")
    r = await signed_post(
        ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"], _base_body(task_id="llm-off-1"),
    )
    body = r.json()
    assert body["code"] == 503 and "未接通" in body["message"]

    record = (
        await db.execute(select(ReasoningTask).where(ReasoningTask.task_id == "llm-off-1"))
    ).scalar_one()
    assert record.status == "failed" and record.llm_called == 0


async def test_timeout_504(ext_client, external_keys, reasoning_seeded, patch_llm, monkeypatch, db):
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.models.basicdata.reasoning import ReasoningTask

    monkeypatch.setattr(get_settings(), "REASONING_TIMEOUT_S", 1)

    async def slow_llm(prompt, timeout_s):
        await asyncio.sleep(30)

    patch_llm(slow_llm)
    r = await signed_post(
        ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"],
        _base_body(task_id="timeout-1"),
    )
    body = r.json()
    assert body["code"] == 504 and "超时" in body["message"]

    record = (
        await db.execute(select(ReasoningTask).where(ReasoningTask.task_id == "timeout-1"))
    ).scalar_one()
    assert record.status == "timeout"


async def test_cancel_inflight_task_490(ext_client, external_keys, reasoning_seeded, patch_llm, db):
    from app.services.reasoning import service as rs

    async def slow_llm(prompt, timeout_s):
        await asyncio.sleep(30)

    patch_llm(slow_llm)
    analyze_future = asyncio.create_task(
        signed_post(ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"],
                    _base_body(task_id="cancel-1"))
    )
    for _ in range(100):
        await asyncio.sleep(0.05)
        if "cancel-1" in rs._running_tasks:
            break
    assert "cancel-1" in rs._running_tasks, "任务未进入运行态，无法验证取消"

    cancel_r = await signed_post(
        ext_client, CANCEL.format(task_id="cancel-1"), "reasoning.cancel", external_keys["reasoning"],
    )
    assert cancel_r.json()["data"]["status"] == "cancelling"

    body = await analyze_future
    assert body.json()["code"] == 490

    from sqlalchemy import select

    from app.models.basicdata.reasoning import ReasoningTask
    record = (
        await db.execute(select(ReasoningTask).where(ReasoningTask.task_id == "cancel-1"))
    ).scalar_one()
    assert record.status == "cancelled" and record.error_code == 490


# ═══════════════════════════════════════════
# 状态接口与幂等取消
# ═══════════════════════════════════════════

async def test_status_and_idempotent_cancel(ext_client, external_keys, reasoning_seeded, patch_llm):
    patch_llm(_analysis_impl)
    r = await signed_post(
        ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"],
        _base_body(task_id="status-1"),
    )
    assert r.json()["code"] == 0

    status_r = await signed_get(
        ext_client, STATUS.format(task_id="status-1"), "reasoning.task", external_keys["reasoning"],
    )
    view = status_r.json()["data"]
    assert view["status"] == "succeeded"
    assert view["llm_called"] is True
    assert view["summary"] == "存在缺料导致的延期风险"

    # 已结束任务取消 → 幂等返回终态
    cancel_r = await signed_post(
        ext_client, CANCEL.format(task_id="status-1"), "reasoning.cancel", external_keys["reasoning"],
    )
    assert cancel_r.json()["data"]["status"] == "succeeded"


async def test_status_unknown_task_404(ext_client, external_keys):
    r = await signed_get(
        ext_client, STATUS.format(task_id="nope"), "reasoning.task", external_keys["reasoning"],
    )
    assert r.json()["code"] == 404


# ═══════════════════════════════════════════
# 幂等回放（同 task_id 重试不重复执行、不 500）
# ═══════════════════════════════════════════

async def test_duplicate_task_id_replays_succeeded(ext_client, external_keys, reasoning_seeded, patch_llm, db):
    from sqlalchemy import func, select

    from app.models.basicdata.reasoning import ReasoningTask

    patch_llm(_analysis_impl)
    first = await signed_post(
        ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"],
        _base_body(task_id="dup-1", request_id="req-1"),
    )
    assert first.json()["code"] == 0
    first_data = first.json()["data"]
    assert first_data["idempotent_replay"] is False

    second = await signed_post(
        ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"],
        _base_body(task_id="dup-1", request_id="req-2"),
    )
    body = second.json()
    assert body["code"] == 0
    assert body["data"]["idempotent_replay"] is True
    assert body["data"]["summary"] == first_data["summary"]
    assert body["data"]["request_id"] == "req-1"

    count = (
        await db.execute(
            select(func.count()).select_from(ReasoningTask).where(ReasoningTask.task_id == "dup-1")
        )
    ).scalar_one()
    assert count == 1


async def test_duplicate_task_id_replays_failure(ext_client, external_keys, reasoning_seeded, monkeypatch, db):
    from sqlalchemy import func, select

    from app.models.basicdata.reasoning import ReasoningTask
    from app.services.reasoning import service as rs

    monkeypatch.setattr(rs.ai_service, "current_provider", lambda: "rule_based")
    first = await signed_post(
        ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"],
        _base_body(task_id="dup-fail-1"),
    )
    assert first.json()["code"] == 503

    second = await signed_post(
        ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"],
        _base_body(task_id="dup-fail-1"),
    )
    assert second.json()["code"] == 503

    count = (
        await db.execute(
            select(func.count()).select_from(ReasoningTask).where(ReasoningTask.task_id == "dup-fail-1")
        )
    ).scalar_one()
    assert count == 1


async def test_duplicate_running_task_id_409(ext_client, external_keys, db):
    from app.models.basicdata.reasoning import ReasoningTask

    db.add(ReasoningTask(
        task_id="running-1", task_type="order_delivery_analysis", prompt="执行中", status="running",
    ))
    await db.commit()

    r = await signed_post(
        ext_client, ANALYZE, "reasoning.analyze", external_keys["reasoning"],
        _base_body(task_id="running-1"),
    )
    body = r.json()
    assert body["code"] == 409
    assert "正在执行" in body["message"]
