"""测试外部组织员工接口

先调用组织列表获取所有组织，再依次尝试几个有子组织的上级组织查询员工。
接口: GET /api/v1/external/organizations/{oa_org_id}/employees
"""

import asyncio
from tests._common_external import (
    call_external_api, format_table, print_result,
)

ORG_ENDPOINT_CODE = "organizations.list"
ORG_ENDPOINT_PATH = "/api/v1/external/organizations/list"
EMP_ENDPOINT_CODE = "organizations.employees"
EMP_ENDPOINT_PATH_TEMPLATE = "/api/v1/external/organizations/{oa_org_id}/employees"

HEADERS = ["id", "oa_user_id", "姓名", "组织", "岗位", "手机号", "邮箱", "状态"]
KEYS = ["id", "oa_user_id", "emp_name", "org_name", "position_name", "phone", "email", "status"]


async def try_org(oa_org_id: str, org_name: str):
    emp_path = EMP_ENDPOINT_PATH_TEMPLATE.format(oa_org_id=oa_org_id)
    emp_body = await call_external_api(
        EMP_ENDPOINT_CODE, emp_path,
        query_string="page=1&page_size=20",
    )
    if emp_body is None:
        return False

    data = emp_body.get("data", {}) or {}
    total = data.get("total", 0)
    items = data.get("items", [])
    has_data = total > 0 or items

    if has_data:
        print_result(data, f"组织[{org_name}]员工列表", HEADERS, KEYS, 1, 20)
    else:
        print(f"组织[{org_name}] (oa_org_id={oa_org_id}): 无员工")
    return has_data


async def main():
    # 获取全部组织
    org_body = await call_external_api(
        ORG_ENDPOINT_CODE, ORG_ENDPOINT_PATH,
        query_string="page=1&page_size=50",
    )
    if org_body is None:
        print("无法获取组织列表，终止。")
        return

    org_data = org_body.get("data", {}) or {}
    orgs = org_data.get("items", [])
    if not orgs:
        print("组织列表为空。")
        return

    # 找出被引用最多的 parent_code（即子组织最多的上级组织）
    from collections import Counter
    parent_counts = Counter(o.get("parent_code") for o in orgs if o.get("parent_code"))
    # 按子组织数量排序，取前几名
    top_parents = parent_counts.most_common(5)

    print("=" * 80)
    print("组织员工查询 — 依次尝试有子组织的上级组织")
    print("=" * 80)

    org_map = {o["oa_org_id"]: o["org_name"] for o in orgs}

    found = False
    for parent_code, child_count in top_parents:
        org_name = org_map.get(parent_code, f"未知({parent_code})")
        print(f"\n--- 尝试: {org_name} (oa_org_id={parent_code}, {child_count}个子组织) ---")
        if await try_org(parent_code, org_name):
            found = True
            break

    if not found:
        # 兜底：尝试第一个叶子组织
        print(f"\n--- 兜底: 尝试第一个组织 ---")
        first = orgs[0]
        await try_org(first["oa_org_id"], first["org_name"])
        print("\n所有尝试的组织下均无员工或数据关联不存在。")


if __name__ == "__main__":
    asyncio.run(main())
