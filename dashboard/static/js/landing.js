/* Landing page — starts a session, then hands over to /dashboard.
   Panel rendering lives in dashboard.js; this file only drives the form. */

"use strict";

const fileInput = document.getElementById("file-input");
const sampleSelect = document.getElementById("sample-select");
const msg = document.getElementById("controls-msg");
const startBtn = document.getElementById("start-btn");

/* The design shows one "No file choosen" slot; it doubles as the sample
   picker, so an uploaded file renames the placeholder option instead of
   adding a second control. */
const placeholder = sampleSelect.options[0];
const PLACEHOLDER_TEXT = placeholder.textContent;

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  placeholder.textContent = file ? file.name : PLACEHOLDER_TEXT;
  if (file) sampleSelect.value = "";
});

sampleSelect.addEventListener("change", () => {
  if (sampleSelect.value) {
    fileInput.value = "";
    placeholder.textContent = PLACEHOLDER_TEXT;
  }
});

document.getElementById("session-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const data = new FormData();
  const file = fileInput.files[0];
  if (file) data.append("file", file);
  else if (sampleSelect.value) data.append("sample", sampleSelect.value);
  else { msg.textContent = "Choose a file or a sample capture first."; return; }

  startBtn.disabled = true;
  msg.textContent = "Starting analysis…";

  let resp;
  try {
    resp = await fetch("/api/session", { method: "POST", body: data });
  } catch (_) {
    startBtn.disabled = false;
    msg.textContent = "Could not start session: backend not reachable.";
    return;
  }
  if (!resp.ok) {
    startBtn.disabled = false;
    const body = await resp.json().catch(() => null);
    msg.textContent = `Could not start session: ${(body && body.detail) || "backend error"}`;
    return;
  }
  window.location.href = "/dashboard";
});
