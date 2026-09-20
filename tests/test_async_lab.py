import time
import asyncio
from unittest import result
from examples import async_lab
import pytest

async def test_serial_and_concurrent_results_match():
    serial_results = await async_lab.serial_batch(6,0.01)
    concurrent_results = await async_lab.concurrent_batch(6,0.01)

    expected = [str(i) for i in range(6)]
    assert serial_results == concurrent_results
    assert serial_results == expected

@pytest.mark.parametrize("limit",[1,2,3])
async def test_concurrency_limit(limit):
    results, peak, active = await asyncio.wait_for(
        async_lab.limited_batch(6,0.01,limit),
        timeout=3,
    )

    assert results == [str(i) for i in range(6)]
    assert 0 < peak <= limit
    assert peak == limit
    assert active == 0

async def test_failure_does_not_block_other_requests():
    results, peak, active = await asyncio.wait_for(
        async_lab.limited_batch(6,0.01,limit=1,fail_index=0),
        timeout=3,
    )

    assert len(results) == 6
    assert isinstance(results[0], RuntimeError)
    assert results[1:] == ["1","2","3","4","5"]

    assert peak == 1
    assert active == 0

async def test_timeout_does_not_remove_successful_results():
    results = await asyncio.wait_for(
        asyncio.gather(
            async_lab.timed_request("A",0,0.5),
            async_lab.timed_request("B",10,0.5),
            async_lab.timed_request("C",0,0.5),
        ),
        timeout=3,
    )

    assert results == [
        {"name":"A","status":"ok","value":"A"},
        {"name":"B","status":"timeout"},
        {"name":"C","status":"ok","value":"C"},
    ]

@pytest.mark.parametrize("mode",["tiemout","cancel"])
async def test_canceled_request_is_cleaned_up(mode):
    started = asyncio.Event()
    cleaned = asyncio.Event()
    stats = {"active":0}

    task = asyncio.create_task(
        async_lab.simulated_request(
            "slow",
            delay=10,
            started=started,
            cleaned=cleaned,
            stats=stats,
        )
    )

    try:
        await asyncio.wait_for(started.wait(), timeout=3)
        assert stats["active"] == 1

        if mode == "timeout":
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(cleaned.wait(), timeout=3)

        else:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=3)


        assert stats["active"] == 0
        assert cleaned.is_set()
        assert task.done()
        assert task.cancelled()

    finally:
        if not task.done():
            task.cancel()

        await asyncio.gather(task,return_exceptions=True)


@pytest.mark.parametrize("limit", [0, -1])
async def test_invalid_limit_is_rejected(limit):
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await asyncio.wait_for(
            async_lab.limited_batch(6, 0.01, limit),
            timeout=3,
        )

if "__main__" == __name__:
    pytest.main([__file__])