/* Before / after comparison slider + fair-compare modes + 100% pixel loupe */
(function () {
  "use strict";

  /* ------------------------------------------------------------------ */
  /* Fair compare — naive Lanczos-ish upscale of the source, rendered at */
  /* the enhanced image's exact pixel size so both sides share one scale  */
  /* ------------------------------------------------------------------ */
  function buildNaive(url, w, h) {
    return new Promise(function (resolve, reject) {
      const im = new Image();
      im.onload = function () {
        try {
          const c = document.createElement("canvas");
          c.width = w;
          c.height = h;
          const ctx = c.getContext("2d");
          ctx.imageSmoothingEnabled = true;
          ctx.imageSmoothingQuality = "high";
          let src = im;
          let sw = im.naturalWidth || w;
          let sh = im.naturalHeight || h;
          // stepwise doubling then a final fit — much crisper than one-shot
          while (sw * 2 <= w && sh * 2 <= h) {
            const step = document.createElement("canvas");
            step.width = sw * 2;
            step.height = sh * 2;
            const sctx = step.getContext("2d");
            sctx.imageSmoothingEnabled = true;
            sctx.imageSmoothingQuality = "high";
            sctx.drawImage(src, 0, 0, step.width, step.height);
            src = step;
            sw = step.width;
            sh = step.height;
          }
          ctx.drawImage(src, 0, 0, w, h);
          resolve(c.toDataURL("image/png"));
        } catch (err) {
          reject(err);
        }
      };
      im.onerror = function () { reject(new Error("source load failed")); };
      im.src = url;
    });
  }

  /* Size the compare box to the image's own aspect ratio, fitted to the
     viewport. Kills the fixed 16:10 letterbox that made the 4× result look
     softer than the 1:1 original. */
  function initFit(root) {
    const after = root.querySelector(".compare-after");
    if (!after) return;

    function fit() {
      const w = after.naturalWidth || 16;
      const h = after.naturalHeight || 10;
      const parent = root.parentElement;
      const maxW = Math.max(240, (parent ? parent.clientWidth : window.innerWidth) - 2);
      const maxH = Math.max(180, Math.min(window.innerHeight * 0.72, 780));
      const s = Math.min(maxW / w, maxH / h);
      root.style.width = Math.round(w * s) + "px";
      root.style.height = Math.round(h * s) + "px";
      root.style.aspectRatio = "";
      root.style.marginInline = "auto";
    }

    if (after.complete && after.naturalWidth) fit();
    after.addEventListener("load", fit);
    window.addEventListener("resize", fit);
  }

  /* ------------------------------------------------------------------ */
  /* Comparison slider                                                   */
  /* ------------------------------------------------------------------ */
  function initCompare(root) {
    const handle = root.querySelector(".compare-handle");
    const beforeWrap = root.querySelector(".compare-before-wrap");
    const beforeImg = root.querySelector(".compare-before");
    if (!handle || !beforeWrap) return;

    let dragging = false;

    function setPos(pct) {
      pct = Math.max(0, Math.min(100, pct));
      beforeWrap.style.width = pct + "%";
      handle.style.left = pct + "%";
      handle.setAttribute("aria-valuenow", String(Math.round(pct)));
      if (beforeImg) {
        const w = root.getBoundingClientRect().width;
        beforeImg.style.width = w + "px";
      }
    }

    function pctFromEvent(e) {
      const rect = root.getBoundingClientRect();
      const x = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
      return (x / rect.width) * 100;
    }

    function start(e) {
      if (root.classList.contains("loupe-on")) return;
      dragging = true;
      root.classList.add("is-dragging");
      setPos(pctFromEvent(e));
      e.preventDefault();
    }
    function move(e) {
      if (!dragging) return;
      setPos(pctFromEvent(e));
    }
    function end() {
      dragging = false;
      root.classList.remove("is-dragging");
    }

    handle.addEventListener("mousedown", start);
    root.addEventListener("mousedown", start);
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", end);

    handle.addEventListener("touchstart", start, { passive: false });
    root.addEventListener("touchstart", start, { passive: false });
    window.addEventListener("touchmove", move, { passive: false });
    window.addEventListener("touchend", end);

    handle.addEventListener("keydown", (e) => {
      const cur = parseFloat(handle.getAttribute("aria-valuenow") || "50");
      if (e.key === "ArrowLeft") { setPos(cur - 2); e.preventDefault(); }
      if (e.key === "ArrowRight") { setPos(cur + 2); e.preventDefault(); }
      if (e.key === "Home") { setPos(0); e.preventDefault(); }
      if (e.key === "End") { setPos(100); e.preventDefault(); }
    });

    window.addEventListener("resize", () => {
      const cur = parseFloat(handle.getAttribute("aria-valuenow") || "50");
      setPos(cur);
    });

    setPos(50);
  }

  /* ------------------------------------------------------------------ */
  /* Comparison modes: raw source vs naive ×N upscale of the source      */
  /* ------------------------------------------------------------------ */
  function initModes(root) {
    const beforeImg = root.querySelector(".compare-before");
    const afterImg = root.querySelector(".compare-after");
    const labelR = document.getElementById("compare-label-r");
    const buttons = root.querySelectorAll("[data-compare-mode]");
    if (!beforeImg || !afterImg || !buttons.length) return;

    const originalUrl = root.dataset.originalUrl || beforeImg.getAttribute("src") || "";
    const scaleLabel = root.dataset.scaleLabel || "";
    let naiveUrl = null;
    let mode = "source";

    function paint() {
      buttons.forEach((b) => {
        const active = b.dataset.compareMode === mode;
        b.classList.toggle("is-active", active);
        b.setAttribute("aria-pressed", String(active));
      });
      if (mode === "naive" && naiveUrl) {
        beforeImg.src = naiveUrl;
        if (labelR) labelR.textContent = "Naive " + scaleLabel;
      } else {
        mode = "source";
        beforeImg.src = originalUrl;
        if (labelR) labelR.textContent = "Original";
      }
    }

    buttons.forEach((b) => {
      b.addEventListener("click", () => {
        mode = b.dataset.compareMode;
        paint();
      });
    });

    function prep() {
      const w = afterImg.naturalWidth;
      const h = afterImg.naturalHeight;
      if (!w || !h || !originalUrl) return;
      buildNaive(originalUrl, w, h).then((data) => {
        naiveUrl = data;
        if (mode === "naive") paint();
      }).catch(() => {
        buttons.forEach((b) => { if (b.dataset.compareMode === "naive") b.disabled = true; });
      });
    }

    if (afterImg.complete && afterImg.naturalWidth) prep();
    afterImg.addEventListener("load", prep);
  }

  /* ------------------------------------------------------------------ */
  /* 100% pixel loupe — side-aware and letterbox-aware                    */
  /* ------------------------------------------------------------------ */
  function initLoupe(root) {
    const loupe = root.querySelector(".loupe");
    const afterImg = root.querySelector(".compare-after");
    const beforeImg = root.querySelector(".compare-before");
    const handle = root.querySelector(".compare-handle");
    const toggle = document.getElementById("loupe-toggle");
    if (!loupe || !afterImg || !toggle) return;

    const SIZE = 170; // loupe diameter in CSS px
    let on = false;

    function pickSide(x) {
      const rect = root.getBoundingClientRect();
      const pct = handle ? (parseFloat(handle.getAttribute("aria-valuenow") || "50") / 100) : 0.5;
      const img = x < pct * rect.width ? beforeImg : afterImg;
      return img && img.naturalWidth ? img : afterImg;
    }

    function show(e) {
      if (!on) return;
      const rect = root.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      if (x < 0 || y < 0 || x > rect.width || y > rect.height) {
        loupe.classList.add("hidden");
        return;
      }
      const img = pickSide(x);
      const nw = img.naturalWidth || 1;
      const nh = img.naturalHeight || 1;

      // object-fit: contain → compute the letterboxed content box first
      const scale = Math.min(rect.width / nw, rect.height / nh);
      const dw = nw * scale;
      const dh = nh * scale;
      const ox = (rect.width - dw) / 2;
      const oy = (rect.height - dh) / 2;
      const cx = (x - ox) / scale;
      const cy = (y - oy) / scale;
      if (cx < 0 || cy < 0 || cx > nw || cy > nh) {
        loupe.classList.add("hidden");
        return;
      }

      loupe.classList.remove("hidden");
      loupe.style.width = SIZE + "px";
      loupe.style.height = SIZE + "px";
      loupe.style.left = x - SIZE / 2 + "px";
      loupe.style.top = y - SIZE / 2 + "px";
      loupe.style.backgroundImage = 'url("' + (img.currentSrc || img.src) + '")';
      loupe.style.backgroundSize = nw + "px " + nh + "px"; // true 100% pixels
      loupe.style.backgroundPosition =
        -(cx - SIZE / 2) + "px " + -(cy - SIZE / 2) + "px";
    }

    toggle.addEventListener("click", () => {
      on = !on;
      toggle.setAttribute("aria-pressed", String(on));
      toggle.textContent = on ? "Loupe on — hover me" : "Inspect at 100%";
      root.classList.toggle("loupe-on", on);
      if (!on) loupe.classList.add("hidden");
    });

    root.addEventListener("mousemove", show);
    root.addEventListener("mouseleave", () => loupe.classList.add("hidden"));
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".compare").forEach((root) => {
      initFit(root);
      initCompare(root);
      initModes(root);
      initLoupe(root);
    });
  });
})();
