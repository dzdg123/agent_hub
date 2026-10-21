"""三组公平对比：一次召回、统一预算、去重审核、固定分母。"""

from __future__ import annotations

import json
from dataclasses import asdict
from statistics import mean
from time import perf_counter

from .context import build_context
from .evidence_diagnostics import analyze_id_duplicates
from .fusion import fuse_rrf
from .models import Source
from .retrieval_pipeline import CandidateIndex, TwoBranchRetriever
from .source_filters import resolve_allowed_ids


METHODS = ("keyword", "vector", "rrf")
EDITABLE = {"support_level", "reason", "reviewer", "human_checked"}
REVIEW_FIELDS = [
    "query_id", "group", "question", "has_allowed_evidence", "filters",
    "reference_quote", "source_id", "file_path", "page", "content",
    "appearances", "preannotated_match", "support_level", "reason", "reviewer", "human_checked",
]


class TimedCandidateIndex:
    """单独记录 search 耗时，与协调层 all() 一致性检查耗时区分。"""

    def __init__(self, index: CandidateIndex) -> None:
        self.index = index
        self.last_search_ms: float | None = None

    def all(self) -> list[Source]:
        return self.index.all()

    def search(self, query, top_k=5, *, allowed_ids=None) -> list[Source]:
        started = perf_counter()
        try:
            return self.index.search(query, top_k, allowed_ids=allowed_ids)
        finally:
            self.last_search_ms = (perf_counter() - started) * 1000


def compare_query(
    retriever: TwoBranchRetriever, canonical_sources: list[Source], entry: dict, *,
    candidate_k: int = 6, top_k: int = 3, max_context_chars: int = 2000,
    rank_constant: int = 60, timed_indexes: dict[str, TimedCandidateIndex] | None = None,
) -> dict:
    """两路各查询一次；独立截取与 RRF 共用原始候选，不调用三次 search。"""
    if type(top_k) is not int or top_k != 3:
        raise ValueError("本实验固定 top_k=3，以保持 Hit@3 的定义")
    # 空输入也验证预算和融合参数，防止故障路径掩盖非法配置。
    build_context([], max_context_chars=max_context_chars)
    fuse_rrf({}, canonical_sources=canonical_sources, top_k=top_k, rank_constant=rank_constant)
    raw_filters = entry.get("filters", {})
    if (not isinstance(raw_filters, dict)
            or any(not isinstance(values, (list, set, frozenset))
                   or any(not isinstance(value, str) for value in values)
                   for values in raw_filters.values())):
        raise ValueError("实验 filters 必须使用字符串数组或集合")
    filters = {name: set(values) for name, values in raw_filters.items()}
    allowed = resolve_allowed_ids(canonical_sources, filters)
    allowed = set(source.source_id for source in canonical_sources) if allowed is None else allowed
    if timed_indexes:
        for index in timed_indexes.values():
            index.last_search_ms = None
    candidate = retriever.retrieve_candidates(
        entry["question"], query_id=entry["query_id"], filters=filters,
        candidate_k=candidate_k, top_k=top_k, allow_degraded=False,
    )
    branches = {name: branch.sources for name, branch in candidate.branches.items()}
    record = {
        **entry, "allowed_source_ids": sorted(allowed), "status": candidate.status,
        "candidate_result": asdict(candidate), "methods": {},
        "search_ms": {name: timed_indexes[name].last_search_ms if timed_indexes else None
                      for name in ("keyword", "vector")},
        "duplicate_diagnostics": None, "fusion_ms": None,
    }
    if candidate.status in {"failed", "degraded"}:
        return record  # 保留失败题，不能偷换成无结果的有效实验。
    record["duplicate_diagnostics"] = asdict(analyze_id_duplicates(branches))
    started = perf_counter()
    fusion = fuse_rrf(branches, canonical_sources=canonical_sources,
                      top_k=top_k, rank_constant=rank_constant)
    record["fusion_ms"] = (perf_counter() - started) * 1000
    record["fusion"] = asdict(fusion)
    rankings = {"keyword": branches["keyword"][:top_k],
                "vector": branches["vector"][:top_k], "rrf": fusion.sources}
    for method, sources in rankings.items():
        started = perf_counter()
        context = build_context(sources, max_context_chars=max_context_chars)
        context_ms = (perf_counter() - started) * 1000
        lookup = {source.source_id: source for source in sources}
        timing = record["search_ms"]
        query_ms = (timing[method] if method != "rrf" else
                    sum(timing.values()) + record["fusion_ms"]
                    if all(value is not None for value in timing.values()) else None)
        record["methods"][method] = {
            "sources": [source.model_dump(mode="json") for source in sources],
            "context": asdict(context), "context_ms": context_ms,
            "hot_retrieval_ms": query_ms,
            "filter_violation_count": sum(source.source_id not in allowed for source in sources),
            "context_filter_violation_count": sum(source_id not in allowed
                                                   for source_id in context.included_source_ids),
            "preannotation_hit": any(source.source_id in entry.get("acceptable_source_ids", [])
                                     for source in sources),
        }
        assert set(context.included_source_ids) <= lookup.keys()
    return record


def make_review_rows(raw: dict) -> list[dict[str, str]]:
    """审核原始候选并集；相同问题和 Source 的等级跨方法共享。"""
    rows = []
    for query in raw["queries"]:
        union, appearances = {}, {}
        for branch, result in query["candidate_result"]["branches"].items():
            for rank, source in enumerate(result["sources"], 1):
                # 运行时记录可能来自 asdict 的 Source 或从 JSON 加载的 dict。
                source = source.model_dump(mode="json") if isinstance(source, Source) else source
                source_id = source["source_id"]
                union.setdefault(source_id, source)
                appearances.setdefault(source_id, []).append(f"{branch}:{rank}")
        for source_id, source in sorted(union.items()):
            rows.append({
                "query_id": query["query_id"], "group": query["group"],
                "question": query["question"],
                "has_allowed_evidence": str(query["has_allowed_evidence"]),
                "filters": json.dumps(query.get("filters", {}), ensure_ascii=False, sort_keys=True),
                "reference_quote": query.get("evidence_quote", ""),
                "source_id": source_id, "file_path": source.get("file_path") or "",
                "page": str(source["page"]) if source.get("page") is not None else "",
                "content": source["content"], "appearances": ";".join(appearances[source_id]),
                "preannotated_match": str(source_id in query.get("acceptable_source_ids", [])),
                "support_level": "", "reason": "", "reviewer": "", "human_checked": "",
            })
    return rows


def _validate_reviews(raw: dict, rows: list[dict[str, str]]) -> dict:
    expected = make_review_rows(raw)
    if len(rows) != len(expected):
        raise ValueError("审核行数变化，不能添加或删除候选")
    indexed = {}
    for row in rows:
        key = (row.get("query_id"), row.get("source_id"))
        if key in indexed:
            raise ValueError(f"重复审核记录：{key}")
        indexed[key] = row
    for original in expected:
        key = (original["query_id"], original["source_id"])
        row = indexed.get(key)
        if row is None or set(row) != set(REVIEW_FIELDS):
            raise ValueError(f"审核字段或候选不匹配：{key}")
        if any(row[field] != original[field] for field in set(REVIEW_FIELDS) - EDITABLE):
            raise ValueError(f"不可修改候选正文、ID、来源、排名等原始字段：{key}")
        level = row["support_level"].strip()
        if level not in {"", "0", "1", "2"}:
            raise ValueError(f"支持等级必须为 0/1/2 或留空：{key}")
        if level and (not row["reason"].strip() or not row["reviewer"].strip()):
            raise ValueError(f"已评分记录必须填写理由和审核者：{key}")
        if row["human_checked"] not in {"", "yes", "no"}:
            raise ValueError("human_checked 只能填 yes/no 或留空")
    return indexed


def aggregate_comparison(raw: dict, rows: list[dict[str, str]]) -> dict:
    """待审核和整体失败保持 None；所有正向题保留在原分母中。"""
    reviewed = _validate_reviews(raw, rows)
    per_query = []
    for query in raw["queries"]:
        item = {"query_id": query["query_id"], "group": query["group"],
                "has_allowed_evidence": query["has_allowed_evidence"],
                "status": query["status"], "methods": {}}
        for method in METHODS:
            result = query["methods"].get(method)
            if result is None:
                item["methods"][method] = {"hit": None, "top1_support": None,
                    "context_hit": None, "unsupported_count": None, "topic_only_count": None}
                continue
            ids = [source["source_id"] for source in result["sources"]]
            levels = {source_id: reviewed[(query["query_id"], source_id)]["support_level"].strip()
                      for source_id in ids}
            complete = all(levels.values())
            included = result["context"]["included_source_ids"]
            item["methods"][method] = {
                "source_ids": ids, "support_levels": levels,
                "top1_source_id": ids[0] if ids else None,
                "hit": int("2" in levels.values()) if complete else None,
                "top1_support": int(bool(ids) and levels[ids[0]] == "2") if complete else None,
                "context_hit": int(any(levels[source_id] == "2" for source_id in included))
                               if complete else None,
                "unsupported_count": sum(level == "0" for level in levels.values()) if complete else None,
                "topic_only_count": sum(level == "1" for level in levels.values()) if complete else None,
            }
        vector, rrf = item["methods"]["vector"], item["methods"]["rrf"]
        item["top1_changed_from_vector"] = (
            vector.get("top1_source_id") != rrf.get("top1_source_id")
            if "source_ids" in vector and "source_ids" in rrf else None
        )
        item["rrf_added_unsupported_ids_vs_vector"] = (
            [source_id for source_id in rrf["source_ids"] if source_id not in vector["source_ids"]
             and rrf["support_levels"][source_id] == "0"]
            if vector["hit"] is not None and rrf["hit"] is not None else None
        )
        per_query.append(item)

    groups = {}
    for group in sorted({query["group"] for query in raw["queries"]}):
        records = [query for query in per_query if query["group"] == group]
        positives = [query for query in records if query["has_allowed_evidence"]]
        group_summary = {"positive_denominator": len(positives),
                         "no_evidence_count": len(records) - len(positives), "methods": {}}
        for method in METHODS:
            complete = bool(positives) and all(query["methods"][method]["hit"] is not None
                                               for query in positives)
            scores = [query["methods"][method] for query in positives]
            method_summary = {"review_complete": complete,
                              "evaluated_positive_count": sum(score["hit"] is not None for score in scores)}
            for field, name in [("hit", "hit_at_3"), ("top1_support", "top1_support_rate"),
                                ("context_hit", "context_retained_hit_rate")]:
                count = sum(score[field] for score in scores) if complete else None
                method_summary[name + "_count"] = count
                method_summary[name] = count / len(positives) if complete else None
            results = [query["methods"][method] for query in raw["queries"]
                       if query["group"] == group and method in query["methods"]]
            all_scores = [query["methods"][method] for query in records]
            all_reviewed = all(score["unsupported_count"] is not None for score in all_scores)
            method_summary.update({
                "unsupported_count": sum(score["unsupported_count"] for score in all_scores) if all_reviewed else None,
                "topic_only_count": sum(score["topic_only_count"] for score in all_scores) if all_reviewed else None,
                "returned_top3_count": sum(len(result["sources"]) for result in results),
                "preannotation_id_hit_count": sum(query["methods"][method]["preannotation_hit"]
                                                  for query in raw["queries"]
                                                  if query["group"] == group and query["has_allowed_evidence"]
                                                  and method in query["methods"]),
                "filter_violation_count": sum(result["filter_violation_count"] for result in results),
                "context_filter_violation_count": sum(result["context_filter_violation_count"] for result in results),
                "mean_context_chars": mean(result["context"]["used_chars"] for result in results) if results else None,
                "mean_hot_retrieval_ms": mean(result["hot_retrieval_ms"] for result in results
                                                if result["hot_retrieval_ms"] is not None)
                                         if any(result["hot_retrieval_ms"] is not None for result in results) else None,
                "successful_execution_count": len(results),
            })
            group_summary["methods"][method] = method_summary
        duplicates = [query["duplicate_diagnostics"] for query in raw["queries"]
                      if query["group"] == group and query["duplicate_diagnostics"] is not None]
        total = sum(value["raw_candidate_count"] for value in duplicates)
        unique = sum(value["unique_source_count"] for value in duplicates)
        group_summary["candidate_repetition"] = {
            "stage": "raw_keyword_and_vector_before_fusion", "raw_count": total,
            "unique_id_count_summed_per_query": unique,
            "rate": (total - unique) / total if total else 0.0,
        }
        groups[group] = group_summary
    return {
        "groups": groups, "per_query": per_query,
        "pending_candidate_rows": sum(not row["support_level"].strip() for row in rows),
        "human_checked_rows": sum(row["human_checked"] == "yes" for row in rows),
        "failed_query_ids": [query["query_id"] for query in raw["queries"] if query["status"] == "failed"],
        "degraded_query_ids": [query["query_id"] for query in raw["queries"] if query["status"] == "degraded"],
        "probe_note": "无允许证据题不计正向命中率；近邻候选不代表证据存在，等级2需核对题目标签。",
    }


def render_comparison_report(raw: dict, summary: dict, rows: list[dict[str, str]]) -> str:
    """输出实际 ID、审核状态和预算后的证据，不根据排名虚构支持等级。"""
    def cell(value):
        return str(value).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")
    lines = ["# Day 09 三组检索对比", "", f"运行：{raw['run_id']}", "",
             f"配置：candidate_k={raw['candidate_k']}，top_k={raw['top_k']}，"
             f"rank_constant={raw['rank_constant']}，Python字符预算={raw['max_context_chars']}。", "",
             "正式指标依据 review.csv 的正文审核；预标注 ID 命中只用于核对。空候选是未命中；失败题保留分母并使成绩不完整。", "",
             f"待审核候选：{summary['pending_candidate_rows']}；人工抽查记录：{summary['human_checked_rows']}。", "",
             "| 题组 | 方法 | 正向分母 | Hit@3 | Top-1支持率 | 预算后命中率 | 过滤违规（检索/上下文） |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for group, metrics in summary["groups"].items():
        for method, score in metrics["methods"].items():
            values = [group, method, metrics["positive_denominator"],
                      *["待审核/执行不完整" if score[key] is None else f"{score[key]:.1%}"
                        for key in ("hit_at_3", "top1_support_rate", "context_retained_hit_rate")],
                      f"{score['filter_violation_count']}/{score['context_filter_violation_count']}"]
            lines.append("| " + " | ".join(map(cell, values)) + " |")
    lines += ["", "## 解释性自动核对与成本", "",
              "下面的预标注ID命中仅核对预先固定的来源，不替代正文审核；耗时均为本次实测。", "",
              "| 题组 | 方法 | 预标注ID命中/正向分母 | 不支持(0级)/主题相关(1级) | 热检索均值ms | 上下文均值字符 |",
              "| --- | --- | --- | --- | --- | --- |"]
    for group, metrics in summary["groups"].items():
        for method, score in metrics["methods"].items():
            values = [group, method, f"{score['preannotation_id_hit_count']}/{metrics['positive_denominator']}",
                      f"{score['unsupported_count']}/{score['topic_only_count']}",
                      score["mean_hot_retrieval_ms"], score["mean_context_chars"]]
            lines.append("| " + " | ".join(map(cell, values)) + " |")
        duplicate = metrics["candidate_repetition"]
        lines += ["", f"{group} 融合前重复率：({duplicate['raw_count']}-"
                  f"{duplicate['unique_id_count_summed_per_query']})/{duplicate['raw_count']}"
                  f" = {duplicate['rate']:.1%}；空分母按0。", ""]
    if raw.get("startup"):
        lines += ["", "启动和预热（与热查询分开）：", "", "| 阶段 | 实测值 |", "| --- | --- |"]
        lines += [f"| {cell(name)} | {cell(value)} |" for name, value in raw["startup"].items()]
    lines += ["", "| 问题 | 关键词 Top-3 | 向量 Top-3 | RRF Top-3 | 三路 Hit | 预算后证据（K/V/R） | 解释 |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for query, evaluated in zip(raw["queries"], summary["per_query"], strict=True):
        ranks = [", ".join(evaluated["methods"][method].get("source_ids", [])) or "无"
                 for method in METHODS]
        hits = "/".join("待定" if evaluated["methods"][method]["hit"] is None
                        else str(evaluated["methods"][method]["hit"]) for method in METHODS)
        contexts = [", ".join(query["methods"][method]["context"]["included_source_ids"]) or "无"
                    if method in query["methods"] else "未执行" for method in METHODS]
        note = ("正向题" if query["has_allowed_evidence"] else "无允许证据，不计分母")
        note += f"；{query['status']}；相对向量新增0级：{evaluated['rrf_added_unsupported_ids_vs_vector']}"
        values = [query["query_id"], *ranks, hits, " / ".join(contexts), note]
        lines.append("| " + " | ".join(map(cell, values)) + " |")
    lines += ["", "## 实际差异分析", ""]
    reviewed_queries = [query for query in summary["per_query"] if query["has_allowed_evidence"]
                        and all(query["methods"][method]["hit"] is not None for method in METHODS)]
    def quality(query, method):
        score = query["methods"][method]
        return score["hit"], score["top1_support"]
    for title, left, right in [("关键词优势", "keyword", "vector"), ("向量优势", "vector", "keyword")]:
        examples = [query for query in reviewed_queries if quality(query, left) > quality(query, right)]
        if not reviewed_queries:
            lines.append(f"- {title}：待正文审核后比较，尚不宣称优势。")
        elif not examples:
            lines.append(f"- {title}：已审核样本未观察到；若还有待审核题，不代表全部数据结论。")
        else:
            query = examples[0]
            lines.append(f"- {title}：{query['query_id']}，{left} 的 (Hit, Top-1支持)={quality(query, left)}，"
                         f"{right}={quality(query, right)}。实际来源与理由见下方审核记录。")
    examples = [query for query in reviewed_queries if quality(query, "rrf") <= quality(query, "vector")]
    if examples:
        query = examples[0]
        lines.append(f"- 融合持平/退化：{query['query_id']}，RRF={quality(query, 'rrf')}，"
                     f"向量={quality(query, 'vector')}；Top-1改变={query['top1_changed_from_vector']}；"
                     f"新增不支持ID={query['rrf_added_unsupported_ids_vs_vector']}。")
    else:
        lines.append("- 融合持平/退化：待审核，或在已审核样本中未观察到。")
    lines += ["", "## 候选正文审核", "",
              "等级0=无关/不支持，1=主题相关但缺关键证据，2=正文直接支持。"
              "填写 support_level、reason、reviewer、human_checked（yes/no）；AI辅助需在 reviewer 明确标记并抽查。", ""]
    for query in raw["queries"]:
        lines += [f"### {query['query_id']}：{query['question']}", "",
                  f"过滤：{query.get('filters', {})}；参考原句：{query.get('evidence_quote', '无支持证据')}。", "",
                  "| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |",
                  "| --- | --- | --- | --- | --- |"]
        for row in rows:
            if row["query_id"] == query["query_id"]:
                values = [f"{row['source_id']} / {row['file_path']} / {row['page']}", row["content"],
                          row["support_level"] or "待填", row["reason"],
                          f"{row['reviewer']} / {row['human_checked']}"]
                lines.append("| " + " | ".join(map(cell, values)) + " |")
        lines.append("")
    lines += ["## 成本和边界", "",
              "模型加载、建库、预热单列于 raw_results.json 的 startup；逐题 search_ms 是热搜索时间，"
              "candidate_result 的 elapsed_ms 含来源一致性检查。RRF成本计两路搜索加融合，context_ms单列。", "",
              "候选重复率按每题融合前两路原始候选计算后汇总（不是跨问题去重）。跨路重合可提供有用信号。"
              "详见 summary.json 的分子、分母与统计范围。", "",
              "无差异的机制解释可独立运行 day09_fusion.py --demo；合成例子不能替代本次真实成绩。", ""]
    return "\n".join(lines)
