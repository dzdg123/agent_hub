const $ = (selector) => document.querySelector(selector);
let currentTask = null;
let eventSource = null;

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `请求失败：${response.status}`);
  return data;
}

function setTask(task) {
  currentTask = task;
  $("#task-panel").classList.remove("hidden");
  $("#task-title").textContent = task.query;
  $("#task-status").textContent = task.status;
  $("#plan").innerHTML = task.plan.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  $("#approve").disabled = task.status !== "waiting_approval";
  $("#cancel").disabled = ["completed", "failed", "cancelled"].includes(task.status);
  if (task.report) $("#report").textContent = task.report;
}

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value;
  return node.innerHTML;
}

async function refreshTask() {
  if (!currentTask) return;
  setTask(await api(`/api/research/${currentTask.task_id}`));
}

function watchEvents(taskId) {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/api/research/${taskId}/events`);
  eventSource.onmessage = async (message) => {
    const event = JSON.parse(message.data);
    const row = document.createElement("div");
    row.className = "event";
    row.textContent = `${new Date(event.created_at).toLocaleTimeString()} · ${event.message}`;
    $("#events").appendChild(row);
    $("#events").scrollTop = $("#events").scrollHeight;
    await refreshTask();
  };
  eventSource.onerror = () => eventSource.close();
}

$("#upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("#document").files[0];
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  $("#upload-status").textContent = "正在上传…";
  try {
    const result = await api("/api/documents", { method: "POST", body });
    $("#upload-status").textContent = `已索引 ${result.chunks} 个片段。`;
  } catch (error) {
    $("#upload-status").textContent = error.message;
  }
});

$("#research-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#events").innerHTML = "";
  $("#report").textContent = "报告完成后会显示在这里。";
  try {
    const task = await api("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: $("#query").value,
        use_web: $("#use-web").checked,
        use_documents: $("#use-documents").checked,
      }),
    });
    setTask(task);
  } catch (error) {
    alert(error.message);
  }
});

$("#approve").addEventListener("click", async () => {
  setTask(await api(`/api/research/${currentTask.task_id}/approve`, { method: "POST" }));
  watchEvents(currentTask.task_id);
});

$("#cancel").addEventListener("click", async () => {
  setTask(await api(`/api/research/${currentTask.task_id}/cancel`, { method: "POST" }));
});

api("/api/health").then((health) => {
  $("#health").textContent = health.demo_mode ? "离线演示模式" : `已连接 ${health.model}`;
}).catch((error) => { $("#health").textContent = error.message; });

