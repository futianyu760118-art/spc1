"""品质异常 AI 分析服务 — 取数 + 构造 prompt + 调用 ai_service.structured_output"""

import json
import logging
from datetime import datetime
from typing import List

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exception.quality_issue import QualityIssue
from app.schemas.exception.quality_analysis import QualityAnalysisReportOut
from app.services.ai import ai_service, ChatOptions, NotSupportedError

logger = logging.getLogger(__name__)

TOP_N = 5          # 高频缺陷类型取 Top N
SAMPLE_K = 3       # 每个高频类型取最近 K 条已关闭记录作为历史样本
TEXT_TRUNCATE = 200  # 历史样本中文本字段截断长度，避免 prompt 过大导致 completion 被截断


async def _collect_stats(db: AsyncSession, conditions: list) -> dict:
    """复用 /statistics 的核心逻辑，返回汇总指标。"""
    summary_q = select(
        func.count(QualityIssue.id),
        func.coalesce(func.sum(QualityIssue.defect_qty), 0),
        func.coalesce(func.sum(QualityIssue.sample_qty), 0),
    )
    if conditions:
        summary_q = summary_q.where(*conditions)
    total, total_defect_qty, total_sample_qty = (await db.execute(summary_q)).one()

    async def grouped_counts(column):
        q = select(column, func.count(QualityIssue.id)).where(column.isnot(None), column != "")
        if conditions:
            q = q.where(*conditions)
        q = q.group_by(column).order_by(func.count(QualityIssue.id).desc())
        result = await db.execute(q)
        return {str(key): count for key, count in result.all()}

    by_status = await grouped_counts(QualityIssue.status)
    by_defect_type = await grouped_counts(QualityIssue.defect_type)
    by_dept = await grouped_counts(QualityIssue.submit_dept)
    by_person = await grouped_counts(QualityIssue.responsible_person)
    avg_defect_rate = round((float(total_defect_qty or 0) / float(total_sample_qty or 0)) * 100, 2) if total_sample_qty else 0

    return {
        "total": total or 0,
        "byStatus": by_status,
        "byDefectType": by_defect_type,
        "byDept": by_dept,
        "byPerson": by_person,
        "totalDefectQty": total_defect_qty or 0,
        "totalSampleQty": total_sample_qty or 0,
        "avgDefectRate": f"{avg_defect_rate:.2f}",
    }


async def _collect_high_freq_with_samples(db: AsyncSession, conditions: list) -> list:
    """取 Top N 高频 defect_type + 每类最近 K 条已关闭记录的历史样本。"""
    base_q = (
        select(QualityIssue.defect_type, func.count(QualityIssue.id).label("cnt"))
        .where(QualityIssue.defect_type.isnot(None), QualityIssue.defect_type != "")
    )
    if conditions:
        base_q = base_q.where(*conditions)
    base_q = base_q.group_by(QualityIssue.defect_type).order_by(func.count(QualityIssue.id).desc()).limit(TOP_N)
    rows = (await db.execute(base_q)).all()

    high_freq = []
    grand_total = sum(c for _, c in rows) or 1
    for defect_type, count in rows:
        proportion = f"{(count / grand_total * 100):.1f}%"

        sample_q = (
            select(
                QualityIssue.root_cause,
                QualityIssue.improvement_countermeasures,
                QualityIssue.temporary_countermeasure,
                QualityIssue.preliminary_analysis,
                QualityIssue.responsible_person,
                QualityIssue.submit_date,
                QualityIssue.product_code,
                QualityIssue.process,
            )
            .where(QualityIssue.defect_type == defect_type, QualityIssue.status == "closed")
            .order_by(QualityIssue.submit_date.desc())
            .limit(SAMPLE_K)
        )
        sample_rows = (await db.execute(sample_q)).all()
        samples = []
        for r in sample_rows:
            samples.append({
                "root_cause": (r.root_cause or "")[:TEXT_TRUNCATE],
                "improvement_countermeasures": (r.improvement_countermeasures or "")[:TEXT_TRUNCATE],
                "temporary_countermeasure": (r.temporary_countermeasure or "")[:TEXT_TRUNCATE],
                "preliminary_analysis": (r.preliminary_analysis or "")[:TEXT_TRUNCATE],
                "responsible_person": r.responsible_person or "",
                "submit_date": str(r.submit_date) if r.submit_date else "",
                "product_code": r.product_code or "",
                "process": r.process or "",
            })

        high_freq.append({
            "defect_type": defect_type,
            "count": count,
            "proportion": proportion,
            "sample_count": len(samples),
            "history_samples": samples,
        })
    return high_freq


def _build_prompt(input_payload: dict) -> str:
    """构造 user prompt，要求 LLM 输出符合 schema 的 JSON。"""
    return (
        "你是资深品质工程分析专家。请基于以下品质异常统计数据与历史样本，"
        "生成一份结构化分析报告。\n\n"
        "【输出要求】\n"
        "- 必须输出纯 JSON，第一个字符是 '{'，最后一个字符是 '}'，"
        "不要使用 markdown 代码块，不要包含任何说明文字或前后缀。\n"
        f"- summary: 1-2 段整体概述，说明当前筛选范围内品质异常的关键特征\n"
        f"- high_freq_findings: 针对 Top {TOP_N} 高频缺陷类型，每条给出 defect_type/count/proportion/note"
        f"（note 描述该类型的共性特征）\n"
        "- root_causes: 列出推断的主要根因（结合历史样本的 root_cause 字段）\n"
        "- strategies: 针对高频异常的解决策略（结合历史 improvement_countermeasures/temporary_countermeasure）\n"
        "- action_items: 具体可执行的行动项，每条带 title/owner_suggestion/priority(高中低)/due_suggestion\n"
        "- prevention: 如何避免高频异常再次出现的预防措施\n\n"
        "【输入数据】\n"
        f"{json.dumps(input_payload, ensure_ascii=False, default=str)}"
    )


async def generate_quality_analysis(
    db: AsyncSession,
    conditions: list,
    filter_summary: dict,
) -> QualityAnalysisReportOut:
    """
    对当前筛选范围的品质异常做 AI 结构化分析。

    conditions: _build_quality_conditions 产出的过滤条件列表
    filter_summary: 用于回填 data_scope 的过滤条件摘要（kwargs）
    """
    stats = await _collect_stats(db, conditions)
    high_freq = await _collect_high_freq_with_samples(db, conditions)

    input_payload = {
        "scope": {
            "total": stats["total"],
            "filters": filter_summary,
        },
        "summary_stats": stats,
        "high_freq_findings": high_freq,
        "top_n": TOP_N,
        "sample_k": SAMPLE_K,
    }

    prompt = _build_prompt(input_payload)
    options = ChatOptions(temperature=0.3, max_tokens=6144, timeout=60)

    try:
        report = await ai_service.structured_output(
            prompt,
            QualityAnalysisReportOut,
            options,
        )
    except NotSupportedError:
        raise HTTPException(
            status_code=400,
            detail=(
                "AI 服务未配置（当前 provider=rule_based 仅回显，无法生成真实分析）。"
                "请在后端 .env.local 设置 AI_DEFAULT_PROVIDER=openai 或 dashscope，"
                "并配置对应的 API key 与 base_url 后重启服务再重试。"
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("品质异常 AI 分析失败")
        raise HTTPException(status_code=502, detail=f"AI 分析失败: {e}")

    if not isinstance(report, QualityAnalysisReportOut):
        report = QualityAnalysisReportOut.model_validate(report)

    report.provider = ai_service.current_provider()
    report.generated_at = datetime.utcnow()
    report.data_scope = {
        "total": stats["total"],
        "filters": filter_summary,
        "top_n": TOP_N,
        "sample_k": SAMPLE_K,
    }
    return report