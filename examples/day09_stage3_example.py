from pathlib import Path
from uuid import uuid4

from examples.day08_evaluate_retrieval import load_fixed_dataset
from research_agent.embeddings import SentenceTransformerEmbedder
from research_agent.retrieval import ChromaIndex, KeywordIndex
from research_agent.retrieval_pipeline import TwoBranchRetriever
from research_agent.context import build_context
from research_agent.retrieval_errors import RetrievalOperationalError

# 1. 加载 Day 08 的规范资料，保留原来的内容和 ID。
project_root = Path(r"E:\agent_project\agent-learning-lab")
dataset_path = project_root / "data/day08/retrieval-v1"

manifest, _, sources = load_fixed_dataset(dataset_path)
config = manifest["config"]


# 2. 创建关键词索引。
keyword_index = KeywordIndex()
keyword_index.add(sources)


# 3. 使用与 Day 08 相同的模型配置创建向量索引。
embedder = SentenceTransformerEmbedder(
    model_name=config["model"],
    device="cpu",
    revision=config["resolved_model_commit"],
    query_instruction=config["query_instruction"],
)

vector_index = ChromaIndex(
    path=project_root / "data/day09/search" / uuid4().hex,
    collection_name="day09-search-v1",
    embedder=embedder,
)
vector_index.add(sources)


# 4. 创建两路检索协调器。
retriever = TwoBranchRetriever(
    sources,
    keyword_index=keyword_index,
    vector_index=vector_index,
)


vector_index = retriever._indexes["vector"]

# 临时替换向量搜索，模拟明确的运行故障。
original_search = vector_index.search

def simulated_failure(*args, **kwargs):
    raise RetrievalOperationalError(
        "模拟向量检索超时",
        operation="vector.search",
        error_type="TimeoutError",
    )

vector_index.search = simulated_failure

try:
    result = retriever.search(
        "offset",
        allow_degraded=True,
        query_id="q-degraded",
    )

    print("整体状态：", result.status)
    print("降级原因：", result.degraded_reason)

    for name, branch in result.branches.items():
        print(name, branch.status, branch.candidate_count)

    if result.status != "failed":
        context = build_context(result.final_sources)
        print(context.text)
finally:
    vector_index.search = original_search
