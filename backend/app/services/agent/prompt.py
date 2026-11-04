"""向助手系统提示注入用户身份、团队智能体清单与能力。"""

from datetime import datetime

from app.services.agent.capabilities import allowed_skill_admin_tools
from app.services.agent.context import UserContext
from app.services.agent.skills import SKILL_INDEX_DESCRIPTION_MAX


def _capability_names(ctx: UserContext) -> str:
    if not ctx.effective_capabilities:
        return "无（仅技能与基础对话）"
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


def _team_skill_index(ctx: UserContext) -> str:
    if not ctx.skills:
        return "无（团队成员未配置技能）"
    lines = []
    for skill in ctx.skills:
        description = (skill.description or "").strip()
        if len(description) > SKILL_INDEX_DESCRIPTION_MAX:
            description = description[:SKILL_INDEX_DESCRIPTION_MAX].rstrip() + "…"
        lines.append(
            f"- #{skill.skill_id} {skill.name}（所属：{skill.agent_name}；"
            f"{'含执行器' if skill.has_executor else '纯指令'}）：{description}"
        )
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
        "",
        "【团队技能（按需加载）】",
        _team_skill_index(ctx),
    ]
    lines.extend([
        "",
        "【团队协作规则】",
        "- 你的能力来自团队成员：查询/推理/写工具只能调用团队内启用成员具备的能力。",
        "- 能力并集非空时必须先调用对应工具取数，不要在没有尝试工具前声称“没有查询通道”。",
        "- 同一能力有多个成员时，按成员编号（member_id）选择最合适的一个；不确定就取编号最小的。",
        "- 写操作必须经用户确认；团队不具备的能力一律明确告知用户无法完成，不要编造。",
        "- 不泄露其他用户的私人会话。",
        "",
        "【技能使用规则】",
        "- 用户需求与技能说明匹配时，先调用 use_skill（skill_id）加载完整指令，再按指令执行。",
        "- 技能只提供方法与上下文，不改变能力边界与写操作确认；技能所属智能体不具备的能力仍不可调用。",
        "- 加载技能后返回文件清单；需要参考文档/资源时调用 read_skill_file，不要猜测文件内容。",
        "- 不要为了推断脚本用法读取 scripts/ 源码；SKILL.md 已给出命令、脚本路径和参数。",
        "- 含执行器的技能加载后会返回执行器参数 schema；需要执行时调用 run_skill_executor，并先加载技能。",
        "- 若 use_skill 返回 script_execution_available=true，可调用 run_skill_script 执行 scripts/ 下脚本；"
        "params 对象会通过 stdin 传入 JSON，args 数组会作为命令行参数传入。",
        "- 文档/表格生成任务：先用查询工具取数，再直接调用 run_skill_script，不要先读脚本源码。",
        "- 技能需要输入文件时用 input_files 传入文本内容（路径→内容），不要反复尝试不存在的输入文件。",
        "- 生成带表格的 Word：用 input_files 写 orders.md，args 用 to-docx --file orders.md --output orders.docx。",
        "- 脚本返回 files 时，必须把每个文件的下载链接（Markdown 链接）原样给用户。",
        "- 脚本执行未启用时不要声称已运行 scripts/ 下的脚本。",
    ])
    allowed_admin = allowed_skill_admin_tools(ctx.permissions, ctx.effective_capabilities)
    if allowed_admin:
        rules = ["", "【技能管理（当前团队具备相应能力）】"]
        if "create_skill" in allowed_admin:
            rules.append(
                "- create_skill 必须提供完整 SKILL.md；默认只写指令与资源；"
                "只有用户明确要求可执行脚本时才传 allow_scripts=true。"
            )
        if "install_skill" in allowed_admin:
            rules.append(
                "- install_skill 支持 SkillHub 单个技能（skill，如 @zcwl/multi-search-engine）、"
                "专家包（pack，如 tech-test-automation；按 skillhub-pack-install.md 协议安装主技能和全部子技能）"
                "或 HTTPS 公网 zip 直链（url）。"
            )
        if "uninstall_skill" in allowed_admin:
            rules.append(
                "- uninstall_skill 支持 pack（卸载整个 SkillHub 专家包及子技能）"
                "或 skill_key/skill_id（单个导入技能）；内置技能不可卸载。"
            )
        rules.append("- 创建/安装后需在智能体管理中绑定才能使用。")
        lines.extend(rules)
    lines.extend([
        "",
        "【需要用户确认时】",
        "- 如果你需要用户做选择或补充信息才能继续，请自行判断交互类型（单选、多选、填空），并在最终回复末尾追加：",
        "```spc-confirm",
        '{"title":"需要确认","questions":[{"id":"q1","type":"single","label":"请选择","options":[{"label":"选项A","value":"a"},{"label":"选项B","value":"b"}],"required":true}]}',
        "```",
        "- type 只能是 single、multiple、text；single/multiple 必须提供至少两个 options；text 可提供 placeholder。",
        "- 不需要用户确认时不要输出该代码块；不要在正文里重复同一组选项。",
    ])
    return "\n".join(lines)
