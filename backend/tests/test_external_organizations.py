"""测试外部组织列表接口

调用外部接口 GET /api/v1/external/organizations/list 并打印第一页数据。
"""

import asyncio
from tests._common_external import (
    APP_KEY, APP_SECRET, BASE_URL,
    generate_signature, build_headers, print_request_info,
    call_external_api, format_table, print_result,
)

ENDPOINT_CODE = "organizations.list"
ENDPOINT_PATH = "/api/v1/external/organizations/list"
PAGE = 1
PAGE_SIZE = 20

HEADERS = ["oa_org_id", "组织名称", "组织类型", "父组织编码", "负责人", "状态"]
KEYS = ["oa_org_id", "org_name", "org_type", "parent_code", "leader_name", "status"]


async def main():
    body = await call_external_api(
        ENDPOINT_CODE, ENDPOINT_PATH,
        query_string=f"page={PAGE}&page_size={PAGE_SIZE}",
    )
    if body is None:
        return

    print_result(body.get("data", {}) or {}, "外部组织列表", HEADERS, KEYS, PAGE, PAGE_SIZE)


if __name__ == "__main__":
    asyncio.run(main())
