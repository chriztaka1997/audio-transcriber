const jobList = document.getElementById("job-list");
const noJobs = document.getElementById("no-jobs");
const jobCount = document.getElementById("job-count");
const jobForm = document.getElementById("job-form");
const validateDirBtn = document.getElementById("validate-dir-btn");
const dirStatus = document.getElementById("dir-status");

const jobs = new Map(); // job_id -> job data

// --- WebSocket ---

let ws;
let reconnectTimeout;

function connectWS() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => {
        console.log("WebSocket connected");
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
    };

    ws.onclose = () => {
        console.log("WebSocket disconnected, reconnecting...");
        clearTimeout(reconnectTimeout);
        reconnectTimeout = setTimeout(connectWS, 2000);
    };

    ws.onerror = () => {
        ws.close();
    };
}

function handleMessage(msg) {
    if (msg.type === "job_update") {
        const job = msg.job;
        jobs.set(job.id, job);
        renderJob(job);
    } else if (msg.type === "download" || msg.type === "transcribe") {
        const existing = jobs.get(msg.job_id);
        if (existing) {
            existing.status = msg.status;
            if (msg.type === "download") {
                existing.download_progress = msg.progress;
                if (msg.speed) existing.download_speed = msg.speed;
            } else {
                existing.transcribe_progress = msg.progress;
            }
            renderJob(existing);
        }
    }
    updateJobCount();
}

// --- Rendering ---

function renderJob(job) {
    let card = document.getElementById(`job-${job.id}`);
    if (!card) {
        card = document.createElement("div");
        card.id = `job-${job.id}`;
        card.className = "job-card";
        jobList.prepend(card);
    }

    const name = job.video_name || extractSlug(job.url);
    const canCancel = ["queued", "downloading", "downloaded", "transcribing"].includes(job.status);

    const downloadPct = (job.download_progress || 0).toFixed(1);
    const transcribePct = (job.transcribe_progress || 0).toFixed(1);
    const speedText = job.download_speed || "";

    let outputHtml = "";
    if (job.status === "completed") {
        outputHtml = `<div class="job-output">`;
        if (job.video_path) outputHtml += `<span>Video: ${job.video_path}</span>`;
        if (job.transcript_path) outputHtml += `<span>Transcript: ${job.transcript_path}</span>`;
        outputHtml += `</div>`;
    }

    let errorHtml = "";
    if (job.status === "failed" && job.error) {
        errorHtml = `<div class="job-error">${escapeHtml(job.error)}</div>`;
    }

    card.innerHTML = `
        <div class="job-header">
            <div>
                <span class="job-name">${escapeHtml(name)}</span>
                <span class="status-badge status-${job.status}">${job.status}</span>
            </div>
            <div class="job-actions">
                ${canCancel ? `<button class="btn-cancel" onclick="cancelJob('${job.id}')">Cancel</button>` : ""}
            </div>
        </div>
        <div class="progress-section">
            <div class="progress-row">
                <span class="progress-label">Download</span>
                <div class="progress-bar-container">
                    <div class="progress-bar download" style="width: ${downloadPct}%"></div>
                </div>
                <span class="progress-info">${downloadPct}%${speedText ? " " + speedText : ""}</span>
            </div>
            <div class="progress-row">
                <span class="progress-label">Transcribe</span>
                <div class="progress-bar-container">
                    <div class="progress-bar transcribe" style="width: ${transcribePct}%"></div>
                </div>
                <span class="progress-info">${transcribePct}%</span>
            </div>
        </div>
        ${outputHtml}
        ${errorHtml}
    `;

    noJobs.style.display = jobs.size > 0 ? "none" : "block";
}

function updateJobCount() {
    const total = jobs.size;
    const active = [...jobs.values()].filter(j =>
        ["downloading", "downloaded", "transcribing"].includes(j.status)
    ).length;
    jobCount.textContent = total > 0 ? `(${active} active / ${total} total)` : "";
}

function extractSlug(url) {
    try {
        const parts = url.split("/");
        // Try to find a meaningful segment
        for (const part of parts.reverse()) {
            if (part && !part.includes("=") && part.length < 60) {
                return part.replace(/\.[^.]+$/, "");
            }
        }
    } catch {}
    return url.substring(0, 50) + "...";
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// --- Actions ---

jobForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const urlsText = document.getElementById("urls").value.trim();
    const outputDir = document.getElementById("output-dir").value.trim();
    const videoName = document.getElementById("video-name").value.trim();
    const transcriptName = document.getElementById("transcript-name").value.trim();
    const whisperModel = document.getElementById("whisper-model").value;
    const generateSrt = document.getElementById("generate-srt").checked;

    if (!urlsText || !outputDir) return;

    const urls = urlsText.split("\n").map(u => u.trim()).filter(u => u.length > 0);

    const submitBtn = jobForm.querySelector(".btn-primary");
    submitBtn.disabled = true;
    submitBtn.textContent = "Adding...";

    for (const url of urls) {
        try {
            const body = {
                url,
                output_dir: outputDir,
                whisper_model: whisperModel,
                generate_srt: generateSrt,
            };
            if (videoName) body.video_name = urls.length === 1 ? videoName : null;
            if (transcriptName) body.transcript_name = urls.length === 1 ? transcriptName : null;

            const resp = await fetch("/api/jobs", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });

            if (!resp.ok) {
                const err = await resp.json();
                console.error("Failed to create job:", err);
            }
        } catch (err) {
            console.error("Error creating job:", err);
        }
    }

    submitBtn.disabled = false;
    submitBtn.textContent = "Add to Queue";
    document.getElementById("urls").value = "";
});

validateDirBtn.addEventListener("click", async () => {
    const path = document.getElementById("output-dir").value.trim();
    if (!path) {
        dirStatus.textContent = "Enter a path first";
        dirStatus.className = "dir-status invalid";
        return;
    }

    try {
        const resp = await fetch("/api/validate-dir", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path }),
        });
        const result = await resp.json();

        if (result.valid) {
            dirStatus.textContent = `Valid: ${result.resolved}`;
            dirStatus.className = "dir-status valid";
        } else {
            dirStatus.textContent = result.error;
            dirStatus.className = "dir-status invalid";
        }
    } catch (err) {
        dirStatus.textContent = "Error checking path";
        dirStatus.className = "dir-status invalid";
    }
});

async function cancelJob(jobId) {
    try {
        await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
    } catch (err) {
        console.error("Error cancelling job:", err);
    }
}

// --- Init ---

async function loadJobs() {
    try {
        const resp = await fetch("/api/jobs");
        const jobsList = await resp.json();
        for (const job of jobsList) {
            jobs.set(job.id, job);
            renderJob(job);
        }
        updateJobCount();
    } catch (err) {
        console.error("Error loading jobs:", err);
    }
}

loadJobs();
connectWS();
