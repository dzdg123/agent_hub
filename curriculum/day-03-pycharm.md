# Day 03：异步、并发与失败处理——PyCharm 详细学习计划

> 适用项目：`E:\agent_project\agent-learning-lab`  
> Python：项目 `.venv` 中的 Python 3.11  
> 学习投入：全天合计 8 小时，各阶段时间灵活分配  
> 核心实验：本地模拟 I/O，无需 API Key、网络或真实模型费用

## 1. 今天要学会什么

Day 01 让程序成功调用模型，Day 02 研究一次调用如何可靠地完成。Day 03 解决一个新的问题：**当 Agent 需要执行多个独立查询时，如何让它们一起推进，并控制失败、超时和资源使用？**

例如，研究一个主题需要获取 5 个网页。每个请求主要在等待服务器响应。如果每次等一个请求结束再启动下一个，总耗时会累加；如果先安排多个请求，程序就能利用其中一个请求等待的时间推进其他请求。

今天先用 `asyncio.sleep()` 模拟网络等待。这里没有真正发送 HTTP 请求，但能观察调度、等待、异常和取消行为。

完成后，你应能解释并实际使用：

- `async def`、协程对象、`await`、Task 和事件循环。
- 串行、并发、并行的区别。
- `asyncio.gather()` 如何组织多个任务。
- `Semaphore` 如何限制同时进行的操作数量。
- 如何保留成功结果，同时记录失败与超时。
- 为什么取消后需要执行清理，并等待任务真正结束。

今天不要求掌握线程池底层、事件循环源码或生产级限流系统。`TaskGroup` 留作扩展。

## 2. 弹性安排与交付物

按“先预测 → 运行 → 观察 → 解释 → 修改 → 再验证”推进，不给各阶段规定小时数。阅读和编码遇到阻塞时，可以往返。

| 优先级 | 今日成果 | 保存位置 |
|---|---|---|
| 核心 | 串行、无限制并发、限制并发的对比实验 | `examples/async_lab.py` |
| 核心 | 普通失败、单任务超时、取消和清理实验 | 同一实验文件 |
| 核心 | 耗时、峰值并发数、成功/失败/超时统计 | `curriculum/day-03-log.md` |
| 核心 | 并发上限、失败保留结果、超时清理的行为测试 | `tests/test_async_lab.py` |
| 核心 | 与真实模型调用代码的对应笔记 | 学习日志 |
| 扩展 | TaskGroup 与 gather 的失败行为对比 | 实验文件或日志 |

**如果当天 8 小时用完仍有核心任务未完成，标记未完成项，下次优先补齐。不要靠删除验收条件宣告完成。**

## 3. 文件操作清单

以下路径均相对于项目根目录。

| 文件 | 操作 | 阅读或修改重点 |
|---|---|---|
| `examples/async_lab.py` | 修改 | 今天全部核心实验的入口 |
| `tests/test_async_lab.py` | 新建 | 验证行为，避免只凭打印判断 |
| `curriculum/day-03-log.md` | 新建 | 预测、数据、解释、问题、复盘 |
| `curriculum/daily-log-template.md` | 阅读或复制 | 日志模板 |
| `src/research_agent/llm.py` | 阅读 | `async def complete()`、HTTP 等待与重试等待 |
| `src/research_agent/mini_agent.py` | 阅读 | 模型调用与工具执行之间的数据依赖 |
| `pyproject.toml` | 阅读 | `asyncio_mode = "auto"` 测试配置 |

今天不需要改变模型客户端或 Agent 主循环。先在实验文件里确认异步行为，再理解它们如何应用到项目。

## 4. 开始前：确认环境与前置知识

### 4.1 在 PyCharm 中打开项目

项目目录：

```text
E:\agent_project\agent-learning-lab
```

运行配置应使用这个解释器：

```text
E:\agent_project\agent-learning-lab\.venv\Scripts\python.exe
```

Terminal 是否自动激活，与运行按钮选择的解释器是两件事。若终端没有激活环境，可以直接执行：

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pytest tests/test_llm.py -q
```

第二条用于检查 Day 02 客户端测试。测试数量以你完成 Day 02 后的实际结果为准，不要求仍然是最初的 2 个。

### 4.2 前置自查

- [ ] 知道 Python 函数的参数、返回值、列表和字典是什么。
- [ ] 能使用 `try / except / finally`。
- [ ] 能说出网络等待与本地计算的区别。
- [ ] 能解释 Day 02 为什么需要超时和有限重试。

如果 `try / finally` 不熟，先做一个普通函数实验：在 `try` 中故意抛异常，确认 `finally` 仍然运行。这会直接帮助你理解今天的资源清理。

### 4.3 创建学习日志

在 PyCharm 中复制日志模板，副本命名为 `day-03-log.md`。已有同名日志就继续填写，不覆盖。

先写：

```markdown
# Day 03 学习日志

## 今天的理解目标
- 我需要解释为什么 async 函数也可能串行运行。
- 我需要证明失败、超时后其他请求仍然完成。

## 实验记录
| 实验 | 运行前预测 | 实际结果 | 我的解释 |
|---|---|---|---|

## 耗时与并发统计
| 模式 | 次数 | 单次等待 | 并发上限 | 实测耗时 | 峰值并发 | 成功/失败/超时 |
|---|---|---|---|---|---|---|

## 错误与修复

## 测试证据

## API 使用
核心实验：0 次真实 API 调用，费用 0 元。

## 我能独立解释的概念

## 尚未完成的核心项
```

## 5. 阶段一：先运行现有实验

打开 `examples/async_lab.py`。现有文件包含：

- `simulated_request()`：模拟等待，可主动失败。
- `serial()`：5 次串行等待，每次 0.2 秒。
- `concurrent()`：并发上限为 3，其中一个请求主动失败。
- `main()`：打印耗时和结果。

右键文件，选择“运行”。随后在“运行 → 编辑配置”中确认：

| 配置项 | 值 |
|---|---|
| 名称 | `Day03 Async Lab` |
| 运行方式 | 脚本路径 |
| 脚本路径 | `E:\agent_project\agent-learning-lab\examples\async_lab.py` |
| 工作目录 | `E:\agent_project\agent-learning-lab` |
| 解释器 | 项目 `.venv\Scripts\python.exe` |

预期大致是：串行约 1 秒；限制并发约 0.4 秒。具体数字会受到系统调度影响，**不要要求毫秒数完全一致**。

观察结果列表中的 `RuntimeError`：现有 `gather(return_exceptions=True)` 把异常放进了结果列表。

当前两种模式同时改变了并发方式和是否失败。先把原始输出记入日志，后续建立相同条件的三组实验，避免混淆变量。

**检查点：**能指出模拟请求在哪一行等待，以及异常为什么出现在列表里而没有直接结束这次实验。

## 6. 阶段二：建立五个核心概念

| 概念 | 今天的理解方式 | 常见误解 |
|---|---|---|
| 协程函数 | 用 `async def` 定义的函数 | 写了 async 就自动更快 |
| 协程对象 | 调用协程函数得到的、尚需被执行的对象 | 调用函数时已经发送请求 |
| `await` | 等待可等待对象完成；遇到实际挂起时，其他任务有机会推进 | 每个 await 都保证切换任务 |
| Task | 交给事件循环调度的协程执行单元 | Task 等于线程 |
| 事件循环 | 协调哪些任务可以继续运行、哪些还在等待 | 一个循环同时执行多段 Python 代码 |

在今天的单线程实验中，同一时刻通常只有一个任务执行 Python 代码；多个等待过程可以重叠。这叫并发。并行则强调同一时刻实际执行多项工作，例如多个 CPU 核心计算。

这些定义可以对照 [Python 3.11 协程与可等待对象说明](https://docs.python.org/3.11/library/asyncio-task.html#awaitables)。

### 实验 A：创建协程对象不等于开始执行

临时在实验文件中加入以下函数，并让入口调用它；完成后再恢复主实验入口：

```python
async def inspect_coroutine():
    job = simulated_request("A", 0.2)
    print("已创建:", type(job).__name__)
    result = await job
    print("等待结束:", result)
```

操作：

1. 在 `simulated_request()` 函数体第一行设置断点。
2. 用调试器执行创建 `job` 的语句。
3. 确认此时函数体还未执行。
4. 执行 `await job`，再观察函数体开始执行。

不要故意把未等待的协程遗留在最终文件中。若看到 `coroutine was never awaited`，找到那个创建后没有 await 或调度的对象并修复。

### 实验 B：Task 提前调度

分别运行下面两种方式，先预测总耗时：

```python
# 方式一：约 0.4 秒
await simulated_request("A", 0.2)
await simulated_request("B", 0.2)
```

```python
# 方式二：约 0.2 秒
task_a = asyncio.create_task(simulated_request("A", 0.2))
task_b = asyncio.create_task(simulated_request("B", 0.2))
await task_a
await task_b
```

这解释了为什么不能单凭“有两个 await”判断串行还是并发：第二种方式先调度了两个 Task，随后才等待结果。保存任务引用，并保证最终等待它们结束。

**检查点：**用自己的话解释两个片段为什么耗时不同。

## 7. 阶段三：建立公平的三组性能实验

修改 `examples/async_lab.py`，让所有性能实验都处理相同的 6 个成功请求，每个等待 0.2 秒。

建议增加以下函数，名字可以自行调整：

```python
async def serial_batch(count: int, delay: float) -> list[str]:
    ...

async def concurrent_batch(count: int, delay: float) -> list[str]:
    ...

async def limited_batch(count: int, delay: float, limit: int) -> list[str]:
    ...
```

这里的 `...` 是待实现位置，必须替换为你的代码。

### 7.1 串行组

用循环逐个 `await simulated_request(...)`，收集结果。

### 7.2 无限制并发组

使用：

```python
results = await asyncio.gather(
    *(simulated_request(str(i), delay) for i in range(count))
)
```

解释 `*`：它把生成的多个协程展开成 `gather()` 的多个参数。

给其中一个任务更短的等待时间，观察：完成顺序可能变化，但 `gather()` 返回的列表仍按输入顺序排列。参考 [gather 官方说明](https://docs.python.org/3.11/library/asyncio-task.html#running-tasks-concurrently)。

### 7.3 限制并发组

创建一把共享的 `asyncio.Semaphore(limit)`，让每个请求在进入请求阶段前申请名额：

```python
semaphore = asyncio.Semaphore(limit)

async def limited(index: int):
    async with semaphore:
        return await simulated_request(str(index), delay)
```

再用 `gather()` 收集所有 `limited(i)`。

关键点：所有请求使用同一个 Semaphore。每个请求内部各自创建一个 Semaphore，无法约束这一批请求。

### 7.4 记录结果

| 模式 | 请求数 | 每次等待 | 并发上限 | 理想耗时近似值 |
|---|---:|---:|---:|---:|
| 串行 | 6 | 0.2 秒 | 1 | 1.2 秒 |
| 无限制并发 | 6 | 0.2 秒 | 6 | 0.2 秒 |
| 限制并发 | 6 | 0.2 秒 | 3 | 0.4 秒 |
| 限制并发 | 6 | 0.2 秒 | 2 | 0.6 秒 |

近似关系只适用于这里各任务等待相同、独立且开销很小的实验：

```text
串行 ≈ 请求数 × 等待时间
无限制并发 ≈ 最慢请求的等待时间
限制并发 ≈ ceil(请求数 / 并发上限) × 等待时间
```

使用 `time.perf_counter()` 计时。在普通“运行”模式下比较数据；调试器暂停会使计时失去意义。每组可以运行 3 次取中位数，不需要重复运行几十次。

**检查点：**把实测数据填入日志，解释为什么“每次请求没变快”，整体却更早完成。

## 8. 阶段四：证明并发上限有效

耗时变成约 0.4 秒，还不足以证明上限一定是 3。增加运行计数器：

```python
active = 0
peak_active = 0

async def limited(index: int):
    nonlocal active, peak_active
    async with semaphore:
        active += 1
        peak_active = max(peak_active, active)
        try:
            return await simulated_request(str(index), delay)
        finally:
            active -= 1
```

把它放入批次函数中，让变量属于本次运行，不使用跨实验共享的全局计数器。为了方便测试，可以返回 `results` 和统计数据，例如 `(results, peak_active, active)`，并相应更新返回类型。

要求：

- `limit=1、2、3` 时都能观察到对应的峰值。
- 峰值不能大于限制。
- 一批任务全部结束后，`active` 必须回到 0。
- 添加一次失败后，计数仍能恢复，名额仍能释放。
- `limit <= 0` 时主动抛出 `ValueError`，避免 `Semaphore(0)` 一直等待。

这里 `active += 1` 和更新峰值之间没有 await，在当前单事件循环线程实验中无需额外加锁。不要把这个结论直接推广到多线程代码。

**Semaphore 控制同时占用名额的数量，不等于每秒请求次数限制。** 真实 API 的 RPM/TPM 限制还需要额外设计。Semaphore 的用法可参考 [Python 3.11 同步原语](https://docs.python.org/3.11/library/asyncio-sync.html#semaphore)。

## 9. 阶段五：某个请求失败，其他请求继续

研究 Agent 经常允许“一个网页失败，但其他网页仍有价值”。单独建立故障实验，不与前面的性能基线混在一起。

### 9.1 保留所有结果

使用已有 `fail` 参数，让索引为 2 的请求失败：

```python
results = await asyncio.gather(
    *(simulated_request(str(i), 0.2, fail=i == 2) for i in range(6)),
    return_exceptions=True,
)
```

逐项处理结果：

```python
for index, result in enumerate(results):
    if isinstance(result, Exception):
        print(index, "失败", type(result).__name__)
    else:
        print(index, "成功", result)
```

这个分类示例用于本实验的普通异常；取消要在后续实验中单独处理。

验收：有 6 个位置，其中 5 个成功、1 个失败；能指出失败的是哪个请求。

### 9.2 理解默认 gather 的行为

改为默认 `gather()` 后，第一个普通异常会向等待它的代码传播；gather 本身不会因此自动取消其他子任务。

如果异常直接离开 `main()`，`asyncio.run()` 关闭事件循环时又会取消尚未完成的任务。这两件事容易混淆。

可选观察方式：先显式创建并保存 Task 列表，在 `try/except RuntimeError` 中等待默认 gather；捕获后，再通过 `await asyncio.gather(*tasks, return_exceptions=True)` 等待并检查剩余任务。这样主函数不会提前退出。

**检查点：**失败隔离意味着分别记录成功和失败，不是把所有异常都隐藏成“成功”。

## 10. 阶段六：单任务超时与清理

增加 `timed_request()` 包装器：

```python
async def timed_request(name: str, delay: float, timeout: float):
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
```

第一轮先验证超时；如果还要覆盖主动失败，可为包装器增加 `fail` 参数并传给 `simulated_request()`。

建立 3 个并发请求：A 等待 0.1 秒、B 等待 0.5 秒、C 等待 0.1 秒，分别设置 0.25 秒超时。

预期：A、C 成功，B 超时；结果包含三项，进程正常结束。

### 10.1 超时包在哪里，含义就不同

```python
# 只限制拿到并发名额后的请求阶段
async with semaphore:
    return await asyncio.wait_for(simulated_request(name, delay), 0.25)
```

如果把 `wait_for()` 放在包含申请 Semaphore 的整个协程外面，排队等待也会占用超时预算。今天先采用“取得名额后才计时”，并在日志写清楚这一选择。

### 10.2 观察取消与 finally

在模拟请求内部加 `try/finally`，在 finally 中记录“清理完成”。确认超时请求也执行清理。

`wait_for()` 超时会请求取消被等待的任务，并等待其取消处理，因此实际返回时间可能超过设置值。协程如果执行阻塞代码，超时也不能像硬件开关一样立刻打断它。参见 [Python 3.11 超时说明](https://docs.python.org/3.11/library/asyncio-task.html#timeouts)。

再做一次显式取消：启动一个较慢 Task，等待它开始，调用 `task.cancel()`，随后 await 这个 Task，并捕获 `asyncio.CancelledError`。确认 finally 运行、任务结束。

建议用 `asyncio.Event` 表示“任务已开始”，避免靠猜一个很短的 sleep 决定取消时机。

如果在任务内部捕获取消，清理后应重新 `raise`。Python 3.11 中 `CancelledError` 继承自 `BaseException`，普通 `except Exception` 不会捕获它。参考 [任务取消说明](https://docs.python.org/3.11/library/asyncio-task.html#task-cancellation)。

**检查点：**超时、普通错误、主动取消是三种不同结果；失败或取消后活动计数归零，没有被遗忘的运行任务。

## 11. 阶段七：找到阻塞事件循环的代码

在一个单独的对照实验里，将模拟请求中的：

```python
await asyncio.sleep(0.2)
```

临时替换为：

```python
time.sleep(0.2)
```

使用 3 个并发任务比较两种版本，观察耗时和开始/结束日志。之后恢复 `asyncio.sleep()`。

需要解释：

- `asyncio.sleep()` 让当前任务挂起，其他任务可以推进。
- `time.sleep()` 阻塞当前线程；如果它是事件循环线程，其他任务也无法推进。
- 把函数声明为 `async def` 不会自动把函数内部的同步阻塞代码转换为异步。
- CPU 密集计算也不会因为加上 async 自动获得多核加速。

打开 `src/research_agent/llm.py`，找到 HTTP 等待和重试等待，写出与模拟实验的对应关系。

再打开 `src/research_agent/mini_agent.py`：当前一轮模型回复决定调用哪个工具时，工具不能在这轮模型回复之前执行；下一轮模型还要读取工具结果。这是数据依赖，不能为了“并发”随意打乱。

在日志举出：

1. 可以并发的操作：多个独立搜索请求。
2. 有依赖的操作：生成查询计划后才能使用计划检索。
3. 不适合直接阻塞事件循环的操作：长时间本地计算或同步网络请求。

## 12. 阶段八：写行为测试

新建 `tests/test_async_lab.py`，围绕你实际实现的函数写测试。

为了让测试方便调用，实验函数应该返回结果和统计；打印汇总放在 `main()` 中。保留 `if __name__ == "__main__": asyncio.run(main())`，避免导入实验模块时自动运行。

可以从项目根目录执行 pytest，并使用 `from examples.async_lab import ...` 导入你的函数。此处替换为实际函数名，不要把省略号写进导入语句。若 PyCharm 找不到模块，先检查工作目录与解释器，并使用下面的完整命令验证。

至少覆盖以下行为：

| 测试 | 输入或设置 | 核心断言 |
|---|---|---|
| 串行与并发结果一致 | 相同成功请求 | 返回相同任务结果，顺序符合约定 |
| 限制有效 | 请求数大于上限 | `0 < peak_active <= limit`，最后 active 为 0 |
| 普通失败隔离 | 指定一个请求失败 | 其他结果完整，失败可定位 |
| 超时隔离 | 一个慢请求与多个快请求 | 慢请求超时，快请求成功 |
| 取消清理 | 取消一个已开始任务 | finally 已执行，任务已结束 |
| 无效上限 | `limit=0` | 抛出 `ValueError`，不进入等待 |

项目已有 `asyncio_mode = "auto"`，异步测试可以直接写 `async def test_...()`，在测试函数内部 await 实验函数，不要再嵌套 `asyncio.run()`。

**不要断言耗时必须等于 0.200 秒，也不要只凭速度判定并发正确。** 时间对比用于学习记录；峰值、结果集合、清理标志用于测试。必要时使用 Event 协调任务开始和结束，给整个测试设置宽松的等待上限，避免测试挂住。

在 PyCharm 右键新测试文件运行，或在 Terminal 执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_async_lab.py -q
```

通过后再检查与第一周直接相关的模块：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_async_lab.py tests/test_llm.py tests/test_mini_agent.py tests/test_tools.py -q
```

测试数量以你写出的案例为准。保存真实结果，不填写预设的“全部通过”。

## 13. 阶段九：复盘与提交

日志必须包含：

- 五个异步概念的个人解释。
- 三种调度方式的相同条件耗时表。
- 并发上限为 1、2、3 时的峰值统计。
- 一次普通失败、一次超时和一次取消的输出。
- 一个自己犯过的错误及修复。
- 一段对照真实 Agent 代码的说明。
- 测试结果与剩余问题。

在 PyCharm Terminal 中确认当前位置是项目根目录：

```powershell
git status
```

如果明确提示当前目录不是 Git 仓库，确认路径后再执行 `git init`。不要把未完成 Git 初始化误认为 Python 程序失败。

查看今天的差异并提交：

```powershell
git diff -- examples/async_lab.py
git diff --check
git add examples/async_lab.py tests/test_async_lab.py curriculum/day-03-log.md curriculum/day-03-pycharm.md
git diff --cached --stat
git status
git commit -m "learn: add async concurrency and failure experiments"
```

只提交学习代码与日志，确认暂存区没有 `.env`、密钥或运行时缓存。如果首次建仓还需要提交项目基础文件，应单独检查并补交，保证之后能从仓库复现实验。

## 14. 核心完成后的扩展任务

### 扩展 A：TaskGroup

用 Python 3.11 的 `asyncio.TaskGroup` 重写一组请求。先全成功，再让其中一个任务抛普通异常。

观察与 `gather(return_exceptions=True)` 的区别：TaskGroup 中某个任务发生未处理的普通异常时，会取消其他剩余任务，等待清理，并汇总异常；它不自动提供“保留全部独立请求结果”的业务策略。

如果希望 TaskGroup 中单个网页失败仍保留其他网页结果，可在子任务内部将预期业务错误转换成结果，同时让取消继续传播。对照 [TaskGroup 官方说明](https://docs.python.org/3.11/library/asyncio-task.html#task-groups)。

### 扩展 B：比较两种超时范围

把相同超时分别放在 Semaphore 内外，增加排队请求，解释为什么某些任务可能还没开始请求就已经超时。

### 扩展 C：同步 I/O 的接入

学习 `asyncio.to_thread()` 如何把同步阻塞 I/O 放到线程中，观察事件循环能否继续运行。注意取消 await 并不保证已经启动的线程函数立即停止。今天不把它作为所有阻塞问题的通用补丁。

## 15. 最终验收清单

- [ ] 能解释协程函数、协程对象、Task、await、事件循环的关系。
- [ ] 能说明串行、并发、并行的区别。
- [ ] 三组性能实验使用相同请求数据，并记录可比较结果。
- [ ] 并发实验在普通运行模式下通常明显快于串行；若没有，能排查阻塞点。
- [ ] 实测峰值始终不超过设置的并发上限。
- [ ] 单个普通失败不会丢失其他成功结果。
- [ ] 单个请求超时后其他请求仍能完成。
- [ ] 取消与异常后清理执行，活动计数回到 0。
- [ ] 没有 `coroutine was never awaited` 或未获取任务异常的警告。
- [ ] 至少覆盖表中六类行为测试，并保存真实运行证据。
- [ ] 能从项目代码举出可并发操作与必须按顺序执行的操作。
- [ ] 完成日志和 Git 提交。

## 16. 不看笔记的口头验收

1. 调用 `simulated_request()` 后，函数体立即执行了吗？
2. 为什么 `for ...: await request()` 通常仍然串行？
3. 为什么先创建多个 Task，再逐个 await，可以并发？
4. 并发后每个请求都变快了吗？
5. Semaphore 为 3，是否意味着每秒最多 3 次请求？
6. gather 的输出顺序和任务完成顺序一定相同吗？
7. 默认 gather 遇到异常，与 main 退出时清理任务，有什么区别？
8. 请求超时后需要做哪些清理？
9. 为什么取消不能只调用 cancel 就当作全部结束？
10. 为什么不能让下一轮模型在工具结果还没回来时读取该结果？

能结合自己运行过的例子解释这些问题，就达到了今天需要的理解深度。

## 17. 按需阅读的官方资料

不要求通读，每次遇到对应概念再查看：

- [Python 3.11：协程与任务](https://docs.python.org/3.11/library/asyncio-task.html)
- [Python 3.11：Semaphore](https://docs.python.org/3.11/library/asyncio-sync.html#semaphore)
- [Python 3.11：asyncio 调试建议](https://docs.python.org/3.11/library/asyncio-dev.html)

明天 Day 04 会进入工具接口、参数校验和 Function Calling。今天掌握的异步调用、失败处理与清理规则，会用于理解工具执行过程。
