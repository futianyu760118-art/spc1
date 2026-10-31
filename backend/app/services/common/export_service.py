"""通用导出服务 — 支持 Excel (.xlsx) 和 CSV 两种格式"""

import io
import csv
from typing import Any

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment


class ExportColumn:
    """导出列定义"""

    def __init__(self, key: str, label: str, width: int = 14):
        self.key = key
        self.label = label
        self.width = width


class GenericExportService:
    """通用导出服务，接收列定义 + 行数据，输出 xlsx 或 csv BytesIO"""

    def __init__(self, columns: list[ExportColumn], rows: list[dict[str, Any]], sheet_name: str = "Sheet1"):
        self.columns = columns
        self.rows = rows
        self.sheet_name = sheet_name

    # ---- Excel ----

    def to_xlsx(self) -> io.BytesIO:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = self.sheet_name

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        center = Alignment(horizontal="center")

        for col_idx, col_def in enumerate(self.columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=col_def.label)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center
            ws.column_dimensions[cell.column_letter].width = col_def.width

        for row_idx, row in enumerate(self.rows, start=2):
            for col_idx, col_def in enumerate(self.columns, start=1):
                value = row.get(col_def.key)
                if value is None:
                    value = ""
                ws.cell(row=row_idx, column=col_idx, value=str(value))

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output

    # ---- CSV (UTF-8 BOM) ----

    def to_csv(self) -> io.BytesIO:
        output = io.BytesIO()
        # BOM 头，保证 Excel 打开中文不乱码
        output.write(b"\xef\xbb\xbf")
        wrapper = io.TextIOWrapper(output, encoding="utf-8", newline="")

        writer = csv.writer(wrapper)
        writer.writerow([c.label for c in self.columns])
        for row in self.rows:
            writer.writerow([str(row.get(c.key) or "") for c in self.columns])

        wrapper.flush()
        wrapper.detach()
        output.seek(0)
        return output
