from pathlib import Path

from research_agent.documents import (
    load_all_documents_detailed,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
root = PROJECT_ROOT / "data" / "day07" / "input"

print("文档目录：", root)
print("目录存在：", root.exists())

result = load_all_documents_detailed(root)

print("成功文件：", result.loaded_files)
print("失败文件：", result.failed_files)
print("跳过文件：", result.skipped_files)
print("Source 数量：", len(result.sources))

print("\n错误：")
for error in result.errors:
    print(
        error.relative_path,
        error.error_code,
        error.message,
    )

print("\n警告：")
for warning in result.warnings:
    print(
        warning.relative_path,
        warning.page,
        warning.warning_code,
        warning.message,
    )