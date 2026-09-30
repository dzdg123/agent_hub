"""Day 05 合成实验的本地轨迹导出；不提供运行恢复。"""

from pathlib import Path
import re

from .models import MiniAgentResult, MiniAgentStatus


def save_trace(
    result: MiniAgentResult, output_dir: str | Path
) -> tuple[Path, Path]:
    """保存事件 JSONL 和完整结果 JSON，使用 run_detailed 自动生成的 ID。

    只接受 UUID hex 文件名；已有文件不覆盖。调用者负责选择可导出的内容。
    """
    if re.fullmatch(r"[0-9a-f]{32}", result.run_id) is None:
        raise ValueError("轨迹导出需要自动生成的 UUID hex run_id")
    if result.status == MiniAgentStatus.RUNNING:
        raise ValueError("只能导出已结束的运行")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    events_path = directory / f"{result.run_id}.events.jsonl"
    result_path = directory / f"{result.run_id}.result.json"
    if events_path.exists() or result_path.exists():
        raise FileExistsError(f"运行轨迹已存在: {result.run_id}")
    with events_path.open("x", encoding="utf-8") as stream:
        for event in result.events:
            stream.write(event.model_dump_json() + "\n")
    with result_path.open("x", encoding="utf-8") as stream:
        stream.write(result.model_dump_json(indent=2) + "\n")
    return events_path, result_path
