const form = document.querySelector("#batchForm");
const button = document.querySelector("#analyzeButton");
const message = document.querySelector("#formMessage");
const empty = document.querySelector("#emptyState");
const content = document.querySelector("#resultContent");
const badge = document.querySelector("#resultBadge");
const agents = [...document.querySelectorAll("#agents li")];
let timers = [];

function clearTimers() { timers.forEach(clearTimeout); timers = []; }
function setStep(index) {
  agents.forEach((agent, i) => {
    agent.classList.toggle("active", i === index);
    agent.classList.toggle("done", i < index);
  });
}
function finishSteps() { agents.forEach(agent => { agent.classList.remove("active"); agent.classList.add("done"); }); }
function escapeHtml(value) { const node = document.createElement("div"); node.textContent = String(value ?? ""); return node.innerHTML; }

async function checkStatus() {
  try {
    const response = await fetch("/api/status");
    const data = await response.json();
    const dot = document.querySelector("#statusDot");
    dot.className = data.live_ready ? "ready" : "error";
    document.querySelector("#apiStatus").textContent = data.live_ready ? "Configured" : `${data.missing.length} setting(s) missing`;
  } catch { document.querySelector("#apiStatus").textContent = "Server unavailable"; }
}

form.addEventListener("submit", async event => {
  event.preventDefault(); clearTimers(); message.textContent = ""; content.classList.add("hidden"); empty.classList.remove("hidden");
  button.disabled = true; button.textContent = "Analyzing..."; badge.textContent = "RUNNING"; setStep(0);
  [1,2,3,4].forEach((step, index) => timers.push(setTimeout(() => setStep(step), 700 * (index + 1))));
  try {
    const response = await fetch("/api/analyze", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({batch_id: document.querySelector("#batchId").value.trim()}) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Request failed");
    if (!data.ok) throw new Error(`${data.stage || "Adobe API"}: ${data.error || "Request failed"}`);
    await new Promise(resolve => timers.push(setTimeout(resolve, 3200)));
    render(data); finishSteps(); badge.textContent = "COMPLETE";
  } catch (error) {
    clearTimers(); agents.forEach(agent => agent.classList.remove("active")); message.textContent = error.message; badge.textContent = "ERROR";
  } finally { button.disabled = false; button.textContent = "Analyze Failed Batch"; }
});

function render(data) {
  empty.classList.add("hidden"); content.classList.remove("hidden");
  document.querySelector("#resultSubtitle").textContent = `Live Adobe result for ${data.batch_id}`;
  document.querySelector("#summaryText").textContent = data.summary;
  document.querySelector("#fileCount").textContent = data.failed_files.length;
  document.querySelector("#errorCount").textContent = data.validation_errors.length;
  document.querySelector("#selectedFile").textContent = data.selected_file || "None";
  document.querySelector("#validationErrors").innerHTML = data.validation_errors.length ? data.validation_errors.map(item => `<div class="error-item"><b>${escapeHtml(item.keyword || "validation")}</b><div>${escapeHtml(item.message)}</div><code>${escapeHtml(item.pointerToViolation || "Pointer unavailable")}</code></div>`).join("") : "<p>No validation errors were returned.</p>";
  document.querySelector("#recommendations").innerHTML = data.recommended_actions.map(item => `<li>${escapeHtml(item)}</li>`).join("");
  document.querySelector("#apiResponse").textContent = JSON.stringify(data.api_response, null, 2);
  document.querySelector("#incidentUpdate").textContent = data.incident_update;
}

document.querySelector("#copyButton").addEventListener("click", async event => {
  await navigator.clipboard.writeText(document.querySelector("#incidentUpdate").textContent);
  event.currentTarget.textContent = "Copied"; setTimeout(() => { event.currentTarget.textContent = "Copy"; }, 1400);
});

checkStatus();
