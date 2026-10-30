"""向助手系统提示注入用户身份、团队智能体清单与能力。"""

from datetime import datetime

from app.services.agent.context import UserContext


def _capability_names(ctx: UserContext) -> str:
    if not ctx.effective_capabilities:
        return "无（仅基础对话）"
    from app.services.agent.capabilities import CONFIGURABLE_CAPABILITIES
    names = [
        CONFIGURABLE_CAPABILITIES[code].name
        for code in sorted(ctx.effective_capabilities)
        if code in CONFIGURABLE_CAPABILITIES
    ]
    return "、".join(names) or "无"


def _team_roster(ctx: UserContext) -> str:
    if not ctx.members:
        return "无（尚未勾选任何智能体）"
    from app.services.agent.capabilities import CONFIGURABLE_CAPABILITIES
    lines = []
    for m in ctx.members:
        cap_names = "、".join(
            CONFIGURABLE_CAPABILITIES[code].name if code in CONFIGURABLE_CAPABILITIES else code
            for code in m.capabilities
        ) or "无"
        status = "启用" if m.status == "active" else "停用"
        desc = f"；{m.description}" if m.description else ""
        lines.append(f"- {m.display_name}（#{m.agent_id}，能力：{cap_names}，{status}{desc}）")
    return "\n".join(lines)


def build_agent_system_prompt(base_prompt: str, ctx: UserContext) -> str:
    lines = [
        base_prompt,
        "",
        "【身份】",
        f"- 服务对象：{ctx.user.display_name or ctx.user.username}（登录名 {ctx.user.username}，角色 {ctx.role_code}）",
        f"- 当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "【我的团队（我勾选的智能体）】",
        _team_roster(ctx),
        "",
        "【当前有效能力（= 团队成员能力并集）】",
        f"- {_capability_names(ctx)}",
    ]
    lines.extend([
        "",
        "【团队协作规则】",
        "- 你的能力来自团队成员：查询/推理/写工具只能调用团队内启用成员具备的能力。",
        "- 同一能力有多个成员时，按成员编号（member_id）选择最合适的一个；不确定就取编号最小的。",
        "- 写操作必须经用户确认；团队不具备的能力一律明确告知用户无法完成，不要编造。",
        "- 不泄露其他用户的私人会话。",
    ])
    return "\n".join(lines)
