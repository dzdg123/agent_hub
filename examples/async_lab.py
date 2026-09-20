"""Day 3 experiment: compare serial, concurrent and failure-isolated I/O."""

import asyncio
import time

from unittest import result

'''模拟等待'''
async def simulated_request(name: str, delay: float, fail: bool = False,*,started:asyncio.Event | None = None,cleaned:asyncio.Event | None = None,stats:dict[str,int] | None = None) -> str:
    if stats is not None:
        stats["active"] += 1

    try:
        print(f"{name}:开始请求")

        if started is not None:
            started.set()

        await asyncio.sleep(delay)

        if fail:
            raise RuntimeError(f"{name}: failed")

        return name

    finally:
        if stats is not None:
            stats["active"] -= 1

        print(f"{name}:清理完成")

        if cleaned is not None:
            cleaned.set()


async def serial() -> list[str]:
    return [await simulated_request(str(i), 0.2) for i in range(5)]


async def concurrent() -> list[object]:
    semaphore = asyncio.Semaphore(3)

    async def limited(index: int):
        async with semaphore:
            return await simulated_request(str(index), 0.2, fail=index == 2)

    return await asyncio.gather(*(limited(i) for i in range(5)), return_exceptions=True)

'A:创建协程对象不等于开始执行'
async def inspect_coroutine():
    job = simulated_request("A",0.2)
    print("已创建：",type(job).__name__)
    result = await job
    print("执行结束",result)


async def serial_batch(count: int, delay: float) -> list[str]:
    results = []
    for i in range(count):
        result = await simulated_request(str(i), delay)
        results.append(result)
    return results

async def concurrent_batch(count: int, delay: float) -> list[str]:
    return await asyncio.gather(*(simulated_request(str(i), delay) for i in range(count)))

async def limited_batch(count: int, delay: float, limit: int, fail_index: int|None = None) ->  tuple[list[str | BaseException], int, int]:
    if limit < 1:
        raise ValueError("limit must be >= 1")

    semaphore = asyncio.Semaphore(limit)

    active = 0
    peak_active = 0

    async def limited(index: int):
        nonlocal active, peak_active

        async with semaphore:
            active += 1
            peak_active = max(peak_active, active)
            try:
                return await simulated_request(str(index), delay,fail=index == fail_index)
            finally:
                active -= 1

    results = await asyncio.gather(*(limited(i) for i in range(count)),return_exceptions=True)

    return results, peak_active, active




async def main() -> None:
    for name, experiment in (("serial", serial), ("concurrent", concurrent)):
        started = time.perf_counter()
        result = await experiment()
        print(name, f"{time.perf_counter() - started:.3f}s", result)

    # await inspect_coroutine()
    # # 方式一：约 0.4 秒
    # started = time.perf_counter()
    # await simulated_request("A", 0.2)
    # await simulated_request("B", 0.2)
    # print(f"{time.perf_counter() - started:.3f}")
    #
    # # 方式二：约 0.2 秒
    # started = time.perf_counter()
    # task_a = asyncio.create_task(simulated_request("A", 0.2))
    # task_b = asyncio.create_task(simulated_request("B", 0.2))
    # await task_a
    # await task_b
    # print(f"{time.perf_counter() - started:.3f}")

    cases = [
        ("串行", lambda: serial_batch(6, 0.2)),
        ("无限制并发", lambda: concurrent_batch(6, 0.2)),
        ("限制并发：3", lambda: limited_batch(6, 0.2, 3)),
        ("限制并发：2", lambda: limited_batch(6, 0.2, 2)),
    ]

    for name, run in cases:
        start = time.perf_counter()
        results = await run()
        elapsed = time.perf_counter() - start
        print(f"{name}：{elapsed:.3f} 秒，结果：{results}")


async def stage_four() -> None:
    # 实验一：不同上限下，全部请求成功
    for limit in (1, 2, 3):
        results, peak, active = await limited_batch(
            count=6,
            delay=0.2,
            limit=limit,
        )

        print(
            f"成功组：limit={limit}, "
            f"peak={peak}, active={active}, results={results}"
        )

        assert results == [str(i) for i in range(6)]
        assert 0 < peak <= limit
        assert peak == limit  # 本实验请求充足，并且都会异步等待
        assert active == 0

    # 实验二：让最先进入的请求失败，观察后续请求能否继续
    results, peak, active = await limited_batch(
        count=6,
        delay=0.2,
        limit=1,
        fail_index=0,
    )

    print(
        f"失败组：limit=1, "
        f"peak={peak}, active={active}, results={results}"
    )

    assert len(results) == 6
    assert isinstance(results[0], RuntimeError)
    assert results[1:] == [str(i) for i in range(1, 6)]
    assert peak == 1
    assert active == 0

    # 实验三：无效上限应直接报错
    for invalid_limit in (0, -1):
        try:
            await limited_batch(6, 0.2, invalid_limit)
        except ValueError as exc:
            print(f"无效上限组：limit={invalid_limit}, 已拒绝：{exc}")
        else:
            raise AssertionError("无效上限没有抛出 ValueError")

    print("阶段四检查全部通过")

async def stage_five() -> None:
    results = await asyncio.gather(
        *(simulated_request(str(i), 0.2, fail=i == 2) for i in range(6)),
        return_exceptions=True
    )

    for index, result in enumerate(results):
        if isinstance(result, Exception):
            print(index, "失败", type(result).__name__)
        else:
            print(index, "成功", result)

async def timed_request(name:str,delay:float,timeout:float):
    try:
        value = await asyncio.wait_for(
            simulated_request(name, delay),
            timeout=timeout,
        )
        return {"name": name, "status": "ok", "value": value}
    except TimeoutError:
        return {"name": name, "status": "timeout"}
    except RuntimeError as exc:
        return {"name": name, "status": "error", "error": str(exc)}

async def stage_six() -> None:
    results = await asyncio.gather(
        timed_request("A", 0.1, 0.25),
        timed_request("B", 0.5, 0.25),
        timed_request("C", 0.2, 0.25),
        return_exceptions=True
    )
    for result in results:
        print(result)

async def stage_six_cleanup() -> None:
    print("\n--- 实验一：超时取消 ---")

    started = asyncio.Event()
    cleaned = asyncio.Event()
    stats = {"active": 0}

    task = asyncio.create_task(
        simulated_request(
            "超时请求",
            0.5,
            started=started,
            cleaned=cleaned,
            stats=stats,
        )
    )

    await started.wait()
    assert stats["active"] == 1

    try:
        await asyncio.wait_for(task, timeout=0.1)
    except TimeoutError:
        print("外部：收到 TimeoutError")
    else:
        raise AssertionError("预期超时，但请求正常完成")

    assert cleaned.is_set()
    assert stats["active"] == 0
    assert task.done()
    assert task.cancelled()

    print("验证通过：超时请求已清理，任务已结束，active=0")
 # 实验二：主动调用 cancel
    print("\n--- 实验二：主动取消 ---")

    started = asyncio.Event()
    cleaned = asyncio.Event()
    stats = {"active": 0}

    task = asyncio.create_task(
        simulated_request(
            "主动取消请求",
            delay=10,
            started=started,
            cleaned=cleaned,
            stats=stats,
        )
    )

    # 不猜测需要 sleep 多久，而是等请求自己通知“已开始”
    await started.wait()
    assert stats["active"] == 1

    task.cancel()  # 发出取消请求，还不能当作已经清理完成

    try:
        await task  # 等待任务处理取消并执行 finally
    except asyncio.CancelledError:
        print("外部：收到 CancelledError")
    else:
        raise AssertionError("预期取消，但请求正常返回")

    assert cleaned.is_set()
    assert stats["active"] == 0
    assert task.done()
    assert task.cancelled()

    print("验证通过：主动取消请求已清理，任务已结束，active=0")

    # 实验三：普通错误也必须执行清理
    print("\n--- 实验三：普通错误 ---")

    started = asyncio.Event()
    cleaned = asyncio.Event()
    stats = {"active": 0}

    try:
        await simulated_request(
            "失败请求",
            delay=0.01,
            fail=True,
            started=started,
            cleaned=cleaned,
            stats=stats,
        )
    except RuntimeError:
        print("外部：收到 RuntimeError")
    else:
        raise AssertionError("预期失败，但请求正常返回")

    assert cleaned.is_set()
    assert stats["active"] == 0

    print("验证通过：失败请求已清理，active=0")

async def stage_seven() -> None:
    async def run_group(blocking:bool) -> list[str]:
        label = "阻塞等待" if blocking else "异步等待"
        started = time.perf_counter()

        async def request(name:str):
            elapsed = time.perf_counter() - started
            print(f"{elapsed:.3f}s {name} 开始")

            if blocking:
                time.sleep(2)
            else:
                await asyncio.sleep(2)

            elapsed = time.perf_counter() - started
            print(f"{elapsed:.3f}s {name} 结束")

            return name

        print(f"\n--- {label} ---")

        results = await asyncio.gather(
            *(request(name) for name in ["A","B","C"])
        )

        elapsed = time.perf_counter() - started
        print(f"结果：{results}")
        print(f"总耗时：{elapsed:.3f}s ")

        return results

    async_results = await run_group(blocking=False)
    blocking_results = await run_group(blocking=True)

    assert async_results == blocking_results == ["A", "B", "C"]



if __name__ == "__main__":
    asyncio.run(stage_seven())
