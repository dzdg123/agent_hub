"""保留已有 PyCharm 配置使用的文件名，转到完整 Day 05 演示。"""

import asyncio
import sys

from day05_agent_v0 import main


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
