"""执行面推理服务纯函数单测：锚点解析、结论证据校验、提示词组装。"""

import pytest

from app.services.reasoning import service as rs


# ═══════════════════════════════════════════
# parse_business_object_ref
# ═══════════════════════════════════════════

def test_parse_order_anchor():
    anchor = rs.parse_business_object_ref("business://order/HJY20260903-261")
    assert anchor.type == "order"
    assert anchor.key == "HJY20260903-261"


def test_parse_product_and_batch_anchor():
    assert rs.parse_business_object_ref("business://product/P-100").key == "P-100"
    assert rs.parse_business_object_ref("business://batch/B-2609").type == "batch"


@pytest.mark.parametrize("bad_ref", [
    None, "", "order/HJY-1", "business://", "business://order", "business://unknown/X-1",
])
def test_parse_invalid_refs_rejected(bad_ref):
    with pytest.raises(rs.InvalidRequestError):
        rs.parse_business_object_ref(bad_ref)


# ═══════════════════════════════════════════
# validate_conclusions
# ═══════════════════════════════════════════

_EVIDENCE = [{"ref": "control-platform://order/SO-1/line/1"}, {"ref": "control-platform://kitting/result/SO-1:1"}]


def _conclusion(matter, refs, confidence="high"):
    return rs.ReasoningConclusion(matter=matter, evidence_refs=refs, confidence=confidence)


def test_validate_keeps_referenced_conclusions():
    analysis = rs.ReasoningAnalysis(
        summary="s", conclusions=[_conclusion("缺料", [_EVIDENCE[0]["ref"]])],
    )
    kept, dropped = rs.validate_conclusions(analysis, _EVIDENCE, require_evidence=True, max_conclusions=20)
    assert len(kept) == 1 and dropped == 0
    assert kept[0].evidence_refs == [_EVIDENCE[0]["ref"]]


def test_validate_rejects_conclusion_without_evidence():
    analysis = rs.ReasoningAnalysis(
        summary="s",
        conclusions=[
            _conclusion("有证据", [_EVIDENCE[0]["ref"]]),
            _conclusion("无证据", []),
            _conclusion("伪造证据", ["control-platform://fabricated/ref"]),
        ],
    )
    kept, dropped = rs.validate_conclusions(analysis, _EVIDENCE, require_evidence=True, max_conclusions=20)
    assert len(kept) == 1 and dropped == 2


def test_validate_filters_partial_refs():
    analysis = rs.ReasoningAnalysis(
        summary="s",
        conclusions=[_conclusion("混合", [_EVIDENCE[0]["ref"], "control-platform://fabricated/ref"])],
    )
    kept, dropped = rs.validate_conclusions(analysis, _EVIDENCE, require_evidence=True, max_conclusions=20)
    assert len(kept) == 1 and dropped == 0
    assert kept[0].evidence_refs == [_EVIDENCE[0]["ref"]]


def test_validate_without_require_evidence_marks_low():
    analysis = rs.ReasoningAnalysis(summary="s", conclusions=[_conclusion("无证据", [])])
    kept, dropped = rs.validate_conclusions(analysis, _EVIDENCE, require_evidence=False, max_conclusions=20)
    assert len(kept) == 1 and dropped == 0
    assert kept[0].confidence == "low" and kept[0].evidence_refs == []


def test_validate_caps_conclusion_count():
    conclusions = [_conclusion(f"结论{i}", [_EVIDENCE[0]["ref"]]) for i in range(5)]
    kept, dropped = rs.validate_conclusions(
        rs.ReasoningAnalysis(summary="s", conclusions=conclusions),
        _EVIDENCE, require_evidence=True, max_conclusions=3,
    )
    assert len(kept) == 3 and dropped == 2


# ═══════════════════════════════════════════
# build_analysis_prompt
# ═══════════════════════════════════════════

def test_build_prompt_contains_refs_and_constraints():
    evidence = [{
        "ref": "control-platform://order/SO-1/line/1", "source": "orders",
        "title": "销售订单行 SO-1:1", "summary": "状态 open",
        "data": {"order_no": "SO-1", "status": "open"},
    }]
    prompt = rs.build_analysis_prompt("分析订单风险", "order_delivery_analysis", evidence)
    assert "business" in prompt or "只读" in prompt
    assert "control-platform://order/SO-1/line/1" in prompt
    assert "分析订单风险" in prompt
    assert "需人工确认" in prompt
    assert "evidence_refs" in prompt
