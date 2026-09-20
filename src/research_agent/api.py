from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .documents import SUPPORTED_SUFFIXES, DocumentLoadError, load_document
from .events import broker
from .models import ResearchRequest, ResearchTask, TaskStatus
from .models import RunEvent
from .runtime import get_index, get_workflow
from .storage import TaskStore


settings = get_settings()
store = TaskStore(settings.database_path)
app = FastAPI(title="Agent Learning Lab", version="0.1.0")
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
async def homepage():
    return FileResponse(static_dir / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "model": settings.deepseek_model, "demo_mode": not bool(settings.deepseek_api_key)}


@app.post("/api/documents", status_code=201)
async def upload_document(file: UploadFile = File(...)):
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(422, "只支持 TXT、Markdown 和 PDF")
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "文件不得超过 10 MB")
    target = settings.document_root / filename
    target.write_bytes(content)
    try:
        sources = load_document(target, settings.document_root)
    except DocumentLoadError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from exc
    get_index().add(sources)
    return {"filename": filename, "chunks": len(sources), "source_ids": [s.source_id for s in sources]}


@app.post("/api/research", response_model=ResearchTask, status_code=202)
async def create_research(request: ResearchRequest):
    task_id = uuid.uuid4().hex
    workflow = get_workflow()
    task = ResearchTask(
        task_id=task_id,
        query=request.query,
        use_web=request.use_web,
        use_documents=request.use_documents,
    )
    store.save(task)
    try:
        task.plan = await workflow.plan(task_id, request.query)
        task.status = TaskStatus.WAITING_APPROVAL
        task.progress = 0.1
    except Exception as exc:
        task.status = TaskStatus.FAILED
        task.errors.append(f"计划生成失败: {type(exc).__name__}: {exc}")
    store.save(task)
    return task


@app.get("/api/research", response_model=list[ResearchTask])
async def list_research():
    return store.list_recent()


@app.get("/api/research/{task_id}", response_model=ResearchTask)
async def get_research(task_id: str):
    task = store.get(task_id)
    if task is None:
        raise HTTPException(404, "研究任务不存在")
    return task


@app.post("/api/research/{task_id}/approve", response_model=ResearchTask, status_code=202)
async def approve_research(task_id: str):
    task = store.get(task_id)
    if task is None:
        raise HTTPException(404, "研究任务不存在")
    if task.status != TaskStatus.WAITING_APPROVAL:
        raise HTTPException(409, f"当前状态不能确认: {task.status}")
    task.status = TaskStatus.RUNNING
    task.progress = 0.2
    store.save(task)
    asyncio.create_task(_run_task(task_id))
    return task


async def _run_task(task_id: str) -> None:
    task = store.get(task_id)
    if task is None:
        return
    try:
        state = await get_workflow().run(
            task_id=task_id,
            query=task.query,
            plan=task.plan,
            use_web=task.use_web,
            use_documents=task.use_documents,
            is_cancelled=lambda: store.is_cancelled(task_id),
        )
        current = store.get(task_id) or task
        if current.status == TaskStatus.CANCELLED or state["status"] == "cancelled":
            current.status = TaskStatus.CANCELLED
        else:
            current.status = TaskStatus.COMPLETED
            current.progress = 1.0
            current.report = state.get("report")
            current.errors.extend(state.get("errors", []))
            current.usage = state.get("usage", current.usage)
        store.save(current)
        await broker.publish(
            RunEvent(
                run_id=task_id,
                kind="cancelled" if current.status == TaskStatus.CANCELLED else "completed",
                message="任务已取消" if current.status == TaskStatus.CANCELLED else "研究报告已完成",
            )
        )
    except Exception as exc:
        task = store.get(task_id) or task
        task.status = TaskStatus.FAILED
        task.errors.append(f"研究失败: {type(exc).__name__}: {exc}")
        store.save(task)
        await broker.publish(
            RunEvent(run_id=task_id, kind="failed", message="研究任务失败", data={"error": str(exc)})
        )


@app.post("/api/research/{task_id}/cancel", response_model=ResearchTask)
async def cancel_research(task_id: str):
    task = store.cancel(task_id)
    if task is None:
        raise HTTPException(404, "研究任务不存在")
    await broker.publish(RunEvent(run_id=task_id, kind="cancelled", message="任务已取消"))
    return task


@app.get("/api/research/{task_id}/events")
async def research_events(task_id: str):
    if store.get(task_id) is None:
        raise HTTPException(404, "研究任务不存在")

    async def stream():
        async for event in broker.subscribe(task_id):
            yield f"data: {event.model_dump_json()}\n\n"
            if event.kind in {"completed", "cancelled", "failed"}:
                break

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/research/{task_id}/report")
async def research_report(task_id: str):
    task = store.get(task_id)
    if task is None:
        raise HTTPException(404, "研究任务不存在")
    if task.status != TaskStatus.COMPLETED or not task.report:
        raise HTTPException(409, "报告尚未完成")
    return {"task_id": task_id, "report": task.report}


def run() -> None:
    import uvicorn

    uvicorn.run("research_agent.api:app", host="127.0.0.1", port=8000, reload=False)
