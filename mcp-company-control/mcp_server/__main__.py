"""入口：python -m mcp_server"""

import logging

from . import __version__, server

logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("company-control MCP Server v%s 启动（stdio 传输）", __version__)
    server.mcp.run()


if __name__ == "__main__":
    main()
