"""测试外部员工列表接口

调用外部接口 GET /api/v1/external/employees/list 并打印第一页数据。
"""

import asyncio
from tests._common_external import (
    APP_KEY, APP_SECRET, BASE_URL,
    generate_signature, build_headers, print_request_info,
    call_external_api, format_table, print_result,
)

ENDPOINT_CODE = "employees.list"
ENDPOINT_PATH = "/api/v1/external/employees/list"
PAGE = 1
PAGE_SIZE = 20

HEADERS = ["id", "oa_user_id", "姓名", "组织", "岗位", "手机号", "邮箱", "状态"]
KEYS = ["id", "oa_user_id", "emp_name", "org_name", "position_name", "phone", "email", "status"]


async def main():
    body = await call_external_api(
        ENDPOINT_CODE, ENDPOINT_PATH,
        query_string=f"page={PAGE}&page_size={PAGE_SIZE}",
    )
    if body is None:
        return

    print_result(body.get("data", {}) or {}, "外部员工列表", HEADERS, KEYS, PAGE, PAGE_SIZE)


if __name__ == "__main__":
    asyncio.run(main())
