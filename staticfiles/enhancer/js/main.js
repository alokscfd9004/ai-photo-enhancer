/* AI Photo Enhancer — upload + job polling */
(function () {
  "use strict";

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  /* ------------------------------------------------------------------ */
  /* Day / Night theme (persisted)                                        */
  /* ------------------------------------------------------------------ */
  (function initTheme() {
    const toggle = document.getElementById("theme-toggle");
    if (!toggle) return;
    function apply(t) {
      document.documentElement.setAttribute("data-theme", t);
      toggle.setAttribute("aria-pressed", String(t === "night"));
      toggle.setAttribute(
        "aria-label",
        t === "night" ? "Switch to day theme" : "Switch to night theme"
      );
      try { localStorage.setItem("theme", t); } catch (e) {}
    }
    apply(document.documentElement.getAttribute("data-theme") === "night" ? "night" : "day");
    toggle.addEventListener("click", () => {
      const c = document.documentElement.getAttribute("data-theme") === "night" ? "night" : "day";
      apply(c === "night" ? "day" : "night");
    });
  })();

  /* Fit-to-target tiers — must match enhancer.services.TARGET_BOXES */
  const TARGET_BOXES = {
    low: [854, 480],
    medium: [1280, 720],
    hd: [1920, 1080],
    "2k": [2560, 1440],
    "4k": [3840, 2160],
  };

  function fitTarget(w, h, box) {
    const s = Math.min(box[0] / w, box[1] / h);
    return [Math.max(1, Math.round(w * s)), Math.max(1, Math.round(h * s))];
  }

  function bytes(n) {
    if (!n && n !== 0) return "—";
    const u = ["B", "KB", "MB", "GB"];
    let i = 0;
    let v = Number(n);
    while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
    return (i === 0 ? v : v.toFixed(1)) + " " + u[i];
  }

  /* ------------------------------------------------------------------ */
  /* Upload page                                                        */
  /* ------------------------------------------------------------------ */
  const dropzone = $("#dropzone");
  const fileInput = $("#file-input");
  const form = $("#upload-form");

  if (dropzone && fileInput && form) {
    const emptyState = $("#dropzone-empty");
    const previewState = $("#dropzone-preview");
    const previewImg = $("#preview-img");
    const previewName = $("#preview-name");
    const clearBtn = $("#clear-file");
    const submitBtn = $("#submit-btn");
    const denoiseInput = form.querySelector('[name="denoise_strength"]');
    const denoiseValue = $("#denoise-value");

    if (denoiseInput && denoiseValue) {
      const sync = () => { denoiseValue.textContent = Number(denoiseInput.value).toFixed(2); };
      denoiseInput.addEventListener("input", sync);
      sync();
    }

    const sharpInput = form.querySelector('[name="sharpness"]');
    const sharpValue = $("#sharpness-value");
    if (sharpInput && sharpValue) {
      const syncSharp = () => { sharpValue.textContent = Number(sharpInput.value).toFixed(2); };
      sharpInput.addEventListener("input", syncSharp);
      syncSharp();
    }

    const texInput = form.querySelector('[name="texture"]');
    const texValue = $("#texture-value");
    if (texInput && texValue) {
      const syncTex = () => { texValue.textContent = Number(texInput.value).toFixed(2); };
      texInput.addEventListener("input", syncTex);
      syncTex();
    }

    /* live "→ WxH" readout for the selected target tier */
    const targetInput = form.querySelector('[name="target"]');
    const readout = $("#size-readout");
    let natural = null;

    function syncSize() {
      if (!readout || !targetInput) return;
      const box = TARGET_BOXES[targetInput.value];
      if (!box) return;
      if (!natural) {
        readout.textContent = "Fits inside the box — aspect kept. Works up and down.";
        return;
      }
      const out = fitTarget(natural.w, natural.h, box);
      const dir = out[0] >= natural.w && out[1] >= natural.h ? "up" : "down";
      const label = out[0] + " × " + out[1];
      readout.innerHTML =
        "→ <strong>" + label + "</strong> · " + natural.w + "×" + natural.h + " (" + dir + ")";
    }
    if (targetInput) targetInput.addEventListener("change", syncSize);
    syncSize();

    function showFile(file) {
      if (!file) return;
      const maxBytes = (window.APP.maxUploadMb || 25) * 1024 * 1024;
      if (file.size > maxBytes) {
        alert("File is larger than " + window.APP.maxUploadMb + " MB.");
        return;
      }
      const url = URL.createObjectURL(file);
      previewImg.src = url;
      previewName.textContent = file.name + " · " + bytes(file.size);
      emptyState.classList.add("hidden");
      previewState.classList.remove("hidden");
      const probe = new Image();
      probe.onload = () => {
        natural = { w: probe.naturalWidth, h: probe.naturalHeight };
        syncSize();
      };
      probe.src = url;
    }

    function resetDrop() {
      fileInput.value = "";
      previewImg.removeAttribute("src");
      emptyState.classList.remove("hidden");
      previewState.classList.add("hidden");
      natural = null;
      syncSize();
    }

    dropzone.addEventListener("click", () => fileInput.click());
    dropzone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
    });
    fileInput.addEventListener("change", () => showFile(fileInput.files[0]));
    clearBtn.addEventListener("click", (e) => { e.stopPropagation(); resetDrop(); });

    ["dragenter", "dragover"].forEach((evt) =>
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropzone.classList.add("is-drag");
      })
    );
    ["dragleave", "drop"].forEach((evt) =>
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropzone.classList.remove("is-drag");
      })
    );
    dropzone.addEventListener("drop", (e) => {
      const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (!file) return;
      const dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
      showFile(file);
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!fileInput.files || !fileInput.files[0]) {
        alert("Choose a photo first.");
        return;
      }
      if (!window.APP.engineAvailable) {
        alert("Real-ESRGAN engine is not installed on this server.");
        return;
      }

      submitBtn.disabled = true;
      submitBtn.querySelector(".btn-label").classList.add("hidden");
      submitBtn.querySelector(".btn-busy").classList.remove("hidden");

      const payload = new FormData(form);
      payload.delete("csrfmiddlewaretoken");

      try {
        const resp = await fetch("/api/upload/", {
          method: "POST",
          body: payload,
          headers: {
            "X-Requested-With": "fetch",
            "X-CSRFToken": window.APP.csrfToken,
          },
        });
        const data = await resp.json();
        if (!resp.ok) {
          const first = data.errors ? Object.values(data.errors)[0] : "Upload failed";
          throw new Error(Array.isArray(first) ? first[0] : first);
        }
        window.location.href = data.job.result_url;
      } catch (err) {
        alert(err.message || "Upload failed.");
        submitBtn.disabled = false;
        submitBtn.querySelector(".btn-label").classList.remove("hidden");
        submitBtn.querySelector(".btn-busy").classList.add("hidden");
      }
    });
  }

  /* ------------------------------------------------------------------ */
  /* Result page — poll job status                                      */
  /* ------------------------------------------------------------------ */
  const root = $("#result-root");
  if (root) {
    const jobId = root.dataset.jobId;
    let status = root.dataset.status;

    const statusPanel = $("#status-panel");
    const errorPanel = $("#error-panel");
    const comparePanel = $("#compare-panel");
    const progressBar = $("#progress-bar");
    const statusTitle = $("#status-title");
    const statusText = $("#status-text");

    const steps = [
      { p: 12, t: "Uploading to the engine…", s: "Validating pixels and preparing tiles." },
      { p: 34, t: "Analysing textures…", s: "Real-ESRGAN is mapping edges and fine detail." },
      { p: 62, t: "Reconstructing detail…", s: "Synthesising high-resolution features." },
      { p: 84, t: "Finalising your HD image…", s: "Almost done — sharpening and encoding." },
    ];
    let step = 0;

    function tickProgress() {
      if (status === "completed" || status === "failed") return;
      const s = steps[Math.min(step, steps.length - 1)];
      if (progressBar) progressBar.style.width = s.p + "%";
      if (statusTitle) statusTitle.textContent = s.t;
      if (statusText) statusText.textContent = s.s;
      step += 1;
      setTimeout(tickProgress, 2200);
    }

    async function poll() {
      try {
        const resp = await fetch("/api/jobs/" + jobId + "/", {
          headers: { "X-Requested-With": "fetch" },
        });
        if (!resp.ok) throw new Error("status " + resp.status);
        const job = await resp.json();
        status = job.status;

        if (job.status === "completed") {
          if (progressBar) progressBar.style.width = "100%";
          if (statusPanel) statusPanel.classList.add("hidden");
          if (errorPanel) errorPanel.classList.add("hidden");

          const after = $("#img-after");
          const beforeWrap = $("#before-wrap");
          if (after && job.enhanced.url) {
            after.src = job.enhanced.url + "?t=" + Date.now();
          }
          if (beforeWrap && job.original.url) {
            const b = $("#img-before");
            if (b) b.src = job.original.url;
          }
          if (comparePanel) comparePanel.classList.remove("hidden");

          const od = $("#stat-orig-dims");
          const ed = $("#stat-enh-dims");
          const os = $("#stat-orig-size");
          const es = $("#stat-enh-size");
          const tm = $("#stat-time");
          if (od && job.original.width) od.textContent = job.original.width + " × " + job.original.height;
          if (ed && job.enhanced.width) ed.textContent = job.enhanced.width + " × " + job.enhanced.height;
          if (os) os.textContent = bytes(job.original.size);
          if (es) es.textContent = bytes(job.enhanced.size);
          if (tm) tm.textContent = (job.processing_seconds || 0) + "s";

          // reveal download buttons if the template rendered without them
          return;
        }

        if (job.status === "failed") {
          if (statusPanel) statusPanel.classList.add("hidden");
          if (comparePanel) comparePanel.classList.add("hidden");
          if (errorPanel) {
            errorPanel.classList.remove("hidden");
            const t = $("#error-text");
            if (t) t.textContent = job.error || "Unknown engine error.";
          }
          return;
        }

        setTimeout(poll, 1500);
      } catch (e) {
        setTimeout(poll, 3000);
      }
    }

    if (status === "pending" || status === "processing") {
      tickProgress();
      poll();
    }
  }
})();
