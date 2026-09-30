"""审批中心 SQL 接入：只读校验 / 映射校验 / 行归一化 纯函数测试。"""

from app.services.common.approval_sql import (
    normalize_sql_row,
    render_deep_link,
    strip_sql_comments,
    validate_field_mapping,
    validate_readonly_sql,
    wrap_readonly_sql,
)


class TestValidateReadonlySql:
    def test_accepts_select_and_cte(self):
        assert validate_readonly_sql("SELECT id FROM t WHERE status = 'pending'") is None
        assert validate_readonly_sql("WITH x AS (SELECT 1) SELECT * FROM x") is None

    def test_rejects_empty(self):
        assert validate_readonly_sql("   ") == "取数 SQL 不能为空"
        assert validate_readonly_sql(None) == "取数 SQL 不能为空"

    def test_rejects_multi_statement(self):
        assert "单条" in validate_readonly_sql("SELECT 1; SELECT 2")

    def test_rejects_non_select(self):
        assert "只读查询" in validate_readonly_sql("UPDATE t SET a = 1")
        assert "只读查询" in validate_readonly_sql("/* c */ DELETE FROM t")

    def test_rejects_write_keywords_inside_select(self):
        err = validate_readonly_sql("SELECT * FROM t WHERE a IN (SELECT a FROM u) FOR UPDATE")
        assert "写操作" in err
        assert "写操作" in validate_readonly_sql("SELECT * FROM t WHERE a = 1 UNION SELECT * FROM (DELETE FROM x RETURNING *) y")

    def test_allows_forbidden_word_inside_string_literal(self):
        assert validate_readonly_sql("SELECT * FROM t WHERE type = 'update'") is None

    def test_comments_are_ignored_for_leading_keyword(self):
        assert validate_readonly_sql("-- 取数\nSELECT 1") is None


class TestStripAndWrap:
    def test_strip_line_and_block_comments(self):
        assert strip_sql_comments("SELECT 1 -- x\n/* y */ + 2").strip() == "SELECT 1 \n + 2"

    def test_strip_keeps_string_literals(self):
        assert "'--'" in strip_sql_comments("SELECT '--' AS a")

    def test_wrap_forces_limit_and_drops_trailing_semicolon(self):
        wrapped = wrap_readonly_sql("SELECT a FROM t ORDER BY a LIMIT 10;", 200)
        assert wrapped.startswith("SELECT * FROM (")
        assert wrapped.endswith(") AS approval_src LIMIT 200")
        assert "LIMIT 10" in wrapped


class TestValidateFieldMapping:
    def test_requires_all_required_fields(self):
        mapping = {"id": "c_id", "no": "c_no", "title": "c_title", "applicant": "c_app",
                   "submitted_at": "c_time", "current_node": "c_node"}
        assert validate_field_mapping(mapping) is None
        for key in ("id", "no", "title", "applicant", "submitted_at", "current_node"):
            broken = {k: v for k, v in mapping.items() if k != key}
            err = validate_field_mapping(broken)
            assert err and "必需" in err

    def test_rejects_empty_and_non_dict(self):
        assert validate_field_mapping(None) is not None
        assert validate_field_mapping({"id": " "}) is not None


class TestNormalizeSqlRow:
    CFG = {
        "biz_type": "purchase_payment", "biz_name": "采购付款申请",
        "field_mapping": {"id": "pay_id", "no": "pay_no", "title": "pay_title",
                          "applicant": "applicant_name", "submitted_at": "apply_time",
                          "current_node": "approval_node", "summary": "dept_name", "amount": "pay_amount"},
        "deep_link_template": "/purchase/payment-applies/{no}",
    }
    ROW = {"pay_id": 12, "pay_no": "PAY-1", "pay_title": "深南电路 9 月货款",
           "applicant_name": "张会计", "apply_time": "2026-09-22 16:20",
           "approval_node": "财务经理审批", "dept_name": "财务部", "pay_amount": 186400}

    def test_normalize_required_and_optional(self):
        item = normalize_sql_row(self.CFG, self.ROW)
        assert item["biz_type"] == "purchase_payment" and item["biz_name"] == "采购付款申请"
        assert item["id"] == 12 and item["no"] == "PAY-1" and item["title"] == "深南电路 9 月货款"
        assert item["applicant"] == "张会计" and item["current_node"] == "财务经理审批"
        assert item["summary"] == "财务部" and item["amount"] == 186400.0
        assert item["can_act"] is False and item["status"] == "pending"

    def test_missing_column_yields_none_not_error(self):
        item = normalize_sql_row(self.CFG, {"pay_id": 1})
        assert item["id"] == 1 and item["no"] is None and item["amount"] is None

    def test_render_deep_link(self):
        item = normalize_sql_row(self.CFG, self.ROW)
        assert render_deep_link(self.CFG["deep_link_template"], item) == "/purchase/payment-applies/PAY-1"
        assert render_deep_link(None, item) == ""
