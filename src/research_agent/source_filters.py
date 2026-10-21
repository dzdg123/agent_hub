"""把本地文件过滤条件转换为两路共用的允许 ID 集合。"""

from __future__ import annotations

from pathlib import PurePosixPath

from .models import Source


def _relative_path(value: str) -> str:
    """统一路径分隔符；只接受语料目录内的相对路径，不访问文件系统。"""
    value = value.replace("\\", "/")
    path = PurePosixPath(value)
    if (not value.strip() or path.is_absolute() or ":" in value
            or ".." in path.parts or str(path) == "."):
        raise ValueError(f"relative_paths 必须是语料目录内的相对文件路径：{value!r}")
    return path.as_posix()


def normalize_filters(filters: dict[str, set[str]] | None) -> dict[str, set[str]]:
    """验证字段与值，返回独立集合；空字段集合保留为明确的空范围。"""
    if filters is None:
        return {}
    if not isinstance(filters, dict):
        raise TypeError("filters 必须是字典或 None")
    unknown = set(filters) - {"file_types", "relative_paths"}
    if unknown:
        raise ValueError(f"未知过滤字段：{', '.join(sorted(map(str, unknown)))}")
    normalized = {}
    for name, values in filters.items():
        if not isinstance(values, (set, frozenset)) or any(
            not isinstance(value, str) for value in values
        ):
            raise TypeError(f"{name} 必须是字符串集合")
        if name == "file_types":
            types = {value.strip().lower() for value in values}
            if types - {"txt", "markdown", "pdf"}:
                raise ValueError("file_types 只支持 txt、markdown、pdf")
            normalized[name] = types
        else:
            normalized[name] = {_relative_path(value) for value in values}
    return normalized


def resolve_allowed_ids(
    sources: list[Source], filters: dict[str, set[str]] | None = None,
) -> set[str] | None:
    """按规范 metadata 取交集；无条件返回 None，有条件但无匹配返回空集合。"""
    normalized = normalize_filters(filters)
    if not normalized:
        return None
    if any(not values for values in normalized.values()):
        return set()
    allowed = set()
    for source in sources:
        if "file_types" in normalized:
            file_type = source.metadata.get("file_type")
            if not isinstance(file_type, str) or file_type.strip().lower() not in normalized["file_types"]:
                continue
        if "relative_paths" in normalized:
            relative_path = source.metadata.get("relative_path")
            if not isinstance(relative_path, str) or _relative_path(relative_path) not in normalized["relative_paths"]:
                continue
        allowed.add(source.source_id)
    return allowed
