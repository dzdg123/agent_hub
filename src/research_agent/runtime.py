from __future__ import annotations

from functools import lru_cache

from .config import get_settings
from .demo_model import DemoModel
from .documents import load_all_documents
from .events import broker
from .llm import DeepSeekClient
from .retrieval import HybridIndex
from .web import DuckDuckGoHTMLSearch
from .workflow import ResearchServices, ResearchWorkflow


@lru_cache(maxsize=1)
def get_index() -> HybridIndex:
    settings = get_settings()
    index = HybridIndex()
    index.add(load_all_documents(settings.document_root))
    return index


def get_model():
    settings = get_settings()
    return DeepSeekClient(settings) if settings.deepseek_api_key else DemoModel()


def get_workflow() -> ResearchWorkflow:
    settings = get_settings()
    return ResearchWorkflow(
        ResearchServices(
            model=get_model(),
            index=get_index(),
            search_provider=DuckDuckGoHTMLSearch(settings.request_timeout_seconds),
            settings=settings,
            events=broker,
        )
    )

