from app.services.ai.dsml import parse_dsml_tool_calls

INSTALL_CONTENT = """我现在用技能管理智能体按 SkillHub 协议安装该技能。

<｜｜DSML｜｜ calls>
<｜｜DSML｜｜ invoke name="install_skill">
<｜｜DSML｜｜ parameter name="skill_key" string="true">@zcwl/multi-search-engine</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
</｜｜DSML｜｜ calls>"""

QUERY_CONTENT = """<｜｜DSML｜｜ calls>
<｜｜DSML｜｜ invoke name="call_query_agent">
<｜｜DSML｜｜ parameter name="path" string="true">/external/production/order-links/list</｜｜DSML｜｜ parameter>
<｜｜DSML｜｜ parameter name="params" string="false">{"order_no": "HJY20261023-308"}</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
</｜｜DSML｜｜ calls>"""


def test_parse_dsml_string_parameter():
    text, calls = parse_dsml_tool_calls(INSTALL_CONTENT)

    assert "DSML" not in text
    assert text == "我现在用技能管理智能体按 SkillHub 协议安装该技能。"
    assert len(calls) == 1
    assert calls[0].name == "install_skill"
    assert calls[0].arguments == {"skill_key": "@zcwl/multi-search-engine"}


def test_parse_dsml_json_parameter():
    text, calls = parse_dsml_tool_calls(QUERY_CONTENT)

    assert text == ""
    assert len(calls) == 1
    assert calls[0].name == "call_query_agent"
    assert calls[0].arguments == {
        "path": "/external/production/order-links/list",
        "params": {"order_no": "HJY20261023-308"},
    }


def test_parse_dsml_keeps_plain_text_untouched():
    text, calls = parse_dsml_tool_calls("正常回复")

    assert text == "正常回复"
    assert calls == []
XML_TOOL_CALL_CONTENT = """I will install the skill.

<tool_call>
{"name": "install_skill", "arguments": {"skill": "@zcwl/multi-search-engine"}}
</tool_call>"""


def test_parse_xml_tool_call_json():
    text, calls = parse_dsml_tool_calls(XML_TOOL_CALL_CONTENT)

    assert "<tool_call>" not in text
    assert text == "I will install the skill."
    assert len(calls) == 1
    assert calls[0].name == "install_skill"
    assert calls[0].arguments == {"skill": "@zcwl/multi-search-engine"}
