"""异常与质量中心 — CSV导入服务"""

import csv
import re
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exception.issue_log import IssueLog
from app.models.exception.change_log import ChangeLog


def _parse_date(val: str) -> date | None:
    """解析 CSV 中的日期字符串，支持 '4月3日' / '2025-04-03' 等格式"""
    if not val or not val.strip():
        return None
    val = val.strip()
    # Try YYYY-MM-DD
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', val)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # Try '4月3日' or '4月3号'
    m = re.match(r'^(\d{1,2})月(\d{1,2})[日号]$', val)
    if m:
        return date(2025, int(m.group(1)), int(m.group(2)))
    return None


async def import_issue_log_csv(file_path: str, db: AsyncSession) -> dict:
    """导入0.1问题日志.csv"""
    created, skipped = 0, 0
    with open(file_path, encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        # Skip header rows (原则/价值观/列头)
        for row in reader:
            if row and row[0].strip() == '序号':
                break
        for row in reader:
            if not row or not row[0].strip():
                continue
            try:
                seq_no = int(row[0].strip()) if row[0].strip() else None
            except ValueError:
                continue
            recorder = row[1].strip() if len(row) > 1 else None
            record_date = _parse_date(row[2]) if len(row) > 2 else None
            description = row[3].strip() if len(row) > 3 else None
            impact = row[4].strip() if len(row) > 4 else None
            interaction = row[5].strip() if len(row) > 5 else None

            if not description:
                skipped += 1
                continue

            log = IssueLog(
                seq_no=seq_no,
                recorder=recorder,
                record_date=record_date,
                description=description,
                impact=impact,
                interaction=interaction,
            )
            db.add(log)
            created += 1

    await db.flush()
    return {"created": created, "skipped": skipped}


async def import_change_log_csv(file_path: str, db: AsyncSession) -> dict:
    """导入0.1.1变更日志.csv"""
    created, skipped = 0, 0
    with open(file_path, encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        # Skip header rows (原则/价值观/标题/列头)
        for row in reader:
            if row and row[0].strip() == '序号':
                break
        for row in reader:
            if not row or not row[0].strip():
                continue
            try:
                seq_no = int(row[0].strip()) if row[0].strip() else None
            except ValueError:
                continue
            modifier = row[1].strip() if len(row) > 1 else None
            change_date = _parse_date(row[2]) if len(row) > 2 else None
            change_content = row[3].strip() if len(row) > 3 else None
            impact = row[4].strip() if len(row) > 4 else None
            interaction = row[5].strip() if len(row) > 5 else None

            if not change_content:
                skipped += 1
                continue

            log = ChangeLog(
                seq_no=seq_no,
                modifier=modifier,
                change_date=change_date,
                change_content=change_content,
                impact=impact,
                interaction=interaction,
            )
            db.add(log)
            created += 1

    await db.flush()
    return {"created": created, "skipped": skipped}


