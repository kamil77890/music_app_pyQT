(function () {
  "use strict";

  const CONTAINER_ID = "jf-music-saver";
  const POLL_INTERVAL = 5000;
  const TOAST_DURATION = 3500;
  const MUSIC_ICON_URL = browser.runtime.getURL("icons/icon-48.png");

  let state = {
    videoId: null,
    backendOnline: false,
    isSaving: false,
    pollTimer: null,
    toastTimer: null,
  };

  let containerEl = null;
  let btnEl = null;
  let dotEl = null;
  let toastEl = null;
  let tooltipEl = null;

  function getVideoId() {
    try {
      return new URL(window.location.href).searchParams.get("v") || "";
    } catch {
      return "";
    }
  }

  function getPageTitle() {
    return document.title || "";
  }

  // ===================== SVG HELPERS =====================

  function svgEl(viewBox, w, h) {
    const ns = "http://www.w3.org/2000/svg";
    const s = document.createElementNS(ns, "svg");
    s.setAttribute("viewBox", viewBox);
    s.setAttribute("width", String(w));
    s.setAttribute("height", String(h));
    s.setAttribute("fill", "none");
    s.setAttribute("stroke", "currentColor");
    s.setAttribute("stroke-width", "2");
    s.setAttribute("stroke-linecap", "round");
    s.setAttribute("stroke-linejoin", "round");
    return s;
  }

  function path(d) {
    const ns = "http://www.w3.org/2000/svg";
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", d);
    return p;
  }

  function polyline(points) {
    const ns = "http://www.w3.org/2000/svg";
    const pl = document.createElementNS(ns, "polyline");
    pl.setAttribute("points", points);
    return pl;
  }

  function line(x1, y1, x2, y2) {
    const ns = "http://www.w3.org/2000/svg";
    const l = document.createElementNS(ns, "line");
    l.setAttribute("x1", String(x1));
    l.setAttribute("y1", String(y1));
    l.setAttribute("x2", String(x2));
    l.setAttribute("y2", String(y2));
    return l;
  }

  function circle(cx, cy, r, extra) {
    const ns = "http://www.w3.org/2000/svg";
    const c = document.createElementNS(ns, "circle");
    c.setAttribute("cx", String(cx));
    c.setAttribute("cy", String(cy));
    c.setAttribute("r", String(r));
    if (extra) Object.entries(extra).forEach(([k, v]) => c.setAttribute(k, String(v)));
    return c;
  }

  function spinnerSVG() {
    const s = svgEl("0 0 24 24", 20, 20);
    s.setAttribute("class", "jf-spinner-icon");
    s.appendChild(circle(12, 12, 10, { "stroke-opacity": 0.2 }));
    s.appendChild(path("M12 2a10 10 0 0 1 10 10"));
    return s;
  }

  function checkSVG() {
    const s = svgEl("0 0 24 24", 20, 20);
    s.setAttribute("class", "jf-check-icon");
    s.appendChild(polyline("20 6 9 17 4 12"));
    return s;
  }

  function xSVG() {
    const s = svgEl("0 0 24 24", 20, 20);
    s.setAttribute("class", "jf-x-icon");
    s.appendChild(line(18, 6, 6, 18));
    s.appendChild(line(6, 6, 18, 18));
    return s;
  }

  // ===================== STYLE INJECTION =====================

  function injectStyles() {
    if (document.getElementById("jf-style")) return;
    const style = document.createElement("style");
    style.id = "jf-style";
    style.textContent = `

/* --- container --- */
#jf-music-saver {
  position: fixed;
  bottom: 28px;
  right: 28px;
  z-index: 99999;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, sans-serif;
  pointer-events: none;
}
#jf-music-saver > * { pointer-events: auto; }

/* --- button base --- */
#jf-floating-btn {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid rgba(255,255,255,0.08);
  background: radial-gradient(circle at 35% 30%, rgba(40,40,70,0.95), rgba(15,12,35,0.98));
  backdrop-filter: blur(8px);
  box-shadow: 0 4px 16px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.06);
  color: #a0a0c0;
  cursor: default;
  padding: 0;
  outline: none;
  transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1),
              box-shadow 0.25s ease,
              border-color 0.25s ease,
              color 0.25s ease,
              background 0.25s ease;
  position: relative;
  user-select: none;
}
#jf-floating-btn:focus-visible {
  box-shadow: 0 0 0 3px rgba(124,77,255,0.5);
}

/* --- online --- */
#jf-floating-btn.jf-online {
  color: #7ec8a8;
  border-color: rgba(126,200,168,0.35);
  background: radial-gradient(circle at 35% 30%, rgba(30,50,45,0.95), rgba(10,20,18,0.98));
  box-shadow: 0 4px 20px rgba(126,200,168,0.15), inset 0 1px 0 rgba(126,200,168,0.08);
  cursor: pointer;
}
#jf-floating-btn.jf-online:hover {
  transform: scale(1.08);
  border-color: rgba(126,200,168,0.6);
  box-shadow: 0 6px 28px rgba(126,200,168,0.25), inset 0 1px 0 rgba(126,200,168,0.1);
}
#jf-floating-btn.jf-online:active {
  transform: scale(0.93);
  transition-duration: 0.05s;
}

/* --- offline --- */
#jf-floating-btn.jf-offline {
  color: #706090;
  border-color: rgba(112,96,144,0.25);
  background: radial-gradient(circle at 35% 30%, rgba(30,25,45,0.9), rgba(12,10,22,0.95));
  box-shadow: 0 2px 10px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.03);
  cursor: default;
}

/* --- saving --- */
#jf-floating-btn.jf-saving {
  color: #70b8ff;
  border-color: rgba(112,184,255,0.4);
  background: radial-gradient(circle at 35% 30%, rgba(20,40,60,0.95), rgba(8,16,28,0.98));
  box-shadow: 0 4px 20px rgba(112,184,255,0.12), inset 0 1px 0 rgba(112,184,255,0.06);
  cursor: default;
  animation: jf-pulse 1.2s ease-in-out infinite;
}

/* --- saved --- */
#jf-floating-btn.jf-saved {
  color: #6cd4a0;
  border-color: rgba(108,212,160,0.5);
  background: radial-gradient(circle at 35% 30%, rgba(25,55,40,0.95), rgba(8,22,15,0.98));
  box-shadow: 0 4px 24px rgba(108,212,160,0.2), inset 0 1px 0 rgba(108,212,160,0.08);
  cursor: default;
  animation: jf-success-pop 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* --- failed --- */
#jf-floating-btn.jf-failed {
  color: #f07060;
  border-color: rgba(240,112,96,0.4);
  background: radial-gradient(circle at 35% 30%, rgba(55,25,22,0.95), rgba(25,10,8,0.98));
  box-shadow: 0 4px 20px rgba(240,112,96,0.12), inset 0 1px 0 rgba(240,112,96,0.06);
  cursor: default;
  animation: jf-error-shake 0.35s ease;
}

/* --- SVG icons inside button --- */
#jf-floating-btn svg {
  display: block;
  filter: drop-shadow(0 0 4px currentColor);
}

/* --- status dot --- */
#jf-status-dot {
  position: absolute;
  bottom: -1px;
  right: -1px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2.5px solid rgba(15,12,35,0.95);
  transition: background 0.3s ease, box-shadow 0.3s ease;
  pointer-events: none;
  z-index: 2;
}
#jf-music-saver.jf-online-dot #jf-status-dot {
  background: #4caf50;
  box-shadow: 0 0 6px rgba(76,175,80,0.4);
}
#jf-music-saver.jf-offline-dot #jf-status-dot {
  background: #ef5350;
  box-shadow: 0 0 4px rgba(239,83,80,0.2);
}
#jf-music-saver.jf-busy-dot #jf-status-dot {
  background: #ffa726;
  box-shadow: 0 0 6px rgba(255,167,38,0.3);
}

/* --- tooltip --- */
#jf-tooltip {
  position: absolute;
  bottom: 68px;
  right: 4px;
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
  background: rgba(15,12,35,0.92);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,0.08);
  color: #b0b0d0;
  box-shadow: 0 4px 12px rgba(0,0,0,0.5);
  pointer-events: none;
  opacity: 0;
  transform: translateY(4px);
  transition: opacity 0.18s ease, transform 0.18s ease;
}
#jf-floating-btn:hover + #jf-tooltip,
#jf-tooltip.jf-visible {
  opacity: 1;
  transform: translateY(0);
}

/* --- toast --- */
#jf-toast {
  position: fixed;
  bottom: 96px;
  right: 28px;
  z-index: 99998;
  padding: 10px 16px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.4;
  max-width: 280px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
  opacity: 0;
  transform: translateY(8px) scale(0.96);
  transition: opacity 0.22s ease, transform 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
  box-shadow: 0 8px 24px rgba(0,0,0,0.5);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.06);
}
#jf-toast.jf-toast-visible {
  opacity: 1;
  transform: translateY(0) scale(1);
}
#jf-toast.jf-toast-success {
  background: rgba(25,55,40,0.88);
  color: #6cd4a0;
  border-color: rgba(108,212,160,0.15);
  box-shadow: 0 8px 24px rgba(0,0,0,0.5), inset 0 1px 0 rgba(108,212,160,0.06);
}
#jf-toast.jf-toast-error {
  background: rgba(55,20,18,0.88);
  color: #f07060;
  border-color: rgba(240,112,96,0.15);
  box-shadow: 0 8px 24px rgba(0,0,0,0.5), inset 0 1px 0 rgba(240,112,96,0.06);
}

/* --- keyframes --- */
@keyframes jf-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
@keyframes jf-pulse {
  0%, 100% { box-shadow: 0 4px 20px rgba(112,184,255,0.12), inset 0 1px 0 rgba(112,184,255,0.06); }
  50% { box-shadow: 0 4px 28px rgba(112,184,255,0.22), inset 0 1px 0 rgba(112,184,255,0.1); }
}
@keyframes jf-success-pop {
  0% { transform: scale(1); }
  40% { transform: scale(1.12); }
  100% { transform: scale(1); }
}
@keyframes jf-error-shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-3px); }
  40% { transform: translateX(3px); }
  60% { transform: translateX(-2px); }
  80% { transform: translateX(2px); }
}
#jf-floating-btn.jf-saving svg.jf-spinner-icon {
  animation: jf-spin 0.75s linear infinite;
}
#jf-floating-btn.jf-saved svg.jf-check-icon {
  animation: jf-success-pop 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

`;
    document.head.appendChild(style);
  }

  // ===================== UI BUILDING =====================

  function createUI() {
    if (document.getElementById(CONTAINER_ID)) return;

    injectStyles();

    containerEl = document.createElement("div");
    containerEl.id = CONTAINER_ID;
    containerEl.className = "jf-offline-dot";

    btnEl = document.createElement("button");
    btnEl.id = "jf-floating-btn";
    btnEl.className = "jf-offline";
    btnEl.setAttribute("aria-label", "Save to Jellyfin");
    const initImg = document.createElement("img");
    initImg.src = MUSIC_ICON_URL;
    initImg.alt = "Save to Jellyfin";
    initImg.style.cssText = "width:34px;height:34px;border-radius:4px;object-fit:contain;display:block;";
    btnEl.appendChild(initImg);

    tooltipEl = document.createElement("span");
    tooltipEl.id = "jf-tooltip";
    tooltipEl.textContent = "Save to Jellyfin";

    dotEl = document.createElement("span");
    dotEl.id = "jf-status-dot";

    toastEl = document.createElement("div");
    toastEl.id = "jf-toast";

    containerEl.appendChild(btnEl);
    containerEl.appendChild(tooltipEl);
    containerEl.appendChild(dotEl);
    containerEl.appendChild(toastEl);
    document.body.appendChild(containerEl);

    btnEl.addEventListener("click", handleClick);
  }

  // ===================== STATE / UI UPDATE =====================

  function setStateClass(className) {
    btnEl.className = "jf-" + className;
  }

  function setDotState(dotClass) {
    containerEl.className = "jf-" + dotClass + "-dot";
  }

  function setTooltip(text) {
    if (!tooltipEl) return;
    tooltipEl.textContent = text;
  }

  function setIconOnline() {
    if (!btnEl) return;
    btnEl.innerHTML = "";
    const img = document.createElement("img");
    img.src = MUSIC_ICON_URL;
    img.alt = "Save to Jellyfin";
    img.style.cssText = "width:34px;height:34px;border-radius:4px;object-fit:contain;display:block;";
    btnEl.appendChild(img);
  }

  function setIconSaving() {
    if (!btnEl) return;
    btnEl.innerHTML = "";
    btnEl.appendChild(spinnerSVG());
  }

  function setIconSaved() {
    if (!btnEl) return;
    btnEl.innerHTML = "";
    btnEl.appendChild(checkSVG());
  }

  function setIconFailed() {
    if (!btnEl) return;
    btnEl.innerHTML = "";
    btnEl.appendChild(xSVG());
  }

  function applyUI() {
    if (!btnEl) return;
    const online = state.backendOnline && !state.isSaving;
    const offline = !state.backendOnline && !state.isSaving;

    if (state.isSaving) {
      setStateClass("saving");
      setDotState("busy");
      setTooltip("Saving to Jellyfin...");
      btnEl.setAttribute("aria-label", "Saving to Jellyfin...");
    } else if (online) {
      setStateClass("online");
      setDotState("online");
      setTooltip("Save to Jellyfin");
      btnEl.setAttribute("aria-label", "Save to Jellyfin");
    } else if (offline) {
      setStateClass("offline");
      setDotState("offline");
      setTooltip("Backend offline \u2014 start music_app_pyQT");
      btnEl.setAttribute("aria-label", "Backend offline");
    }
  }

  // --- Toast ---
  function showToast(text, isError) {
    if (!toastEl) return;
    clearTimeout(state.toastTimer);
    toastEl.textContent = text;
    toastEl.className = isError ? "jf-toast jf-toast-error" : "jf-toast jf-toast-success";
    toastEl.classList.add("jf-toast-visible");
    state.toastTimer = setTimeout(() => {
      toastEl.classList.remove("jf-toast-visible");
    }, TOAST_DURATION);
  }

  function hideToast() {
    clearTimeout(state.toastTimer);
    if (toastEl) {
      toastEl.classList.remove("jf-toast-visible");
    }
  }

  // --- Backend check ---
  async function checkBackend() {
    try {
      const resp = await browser.runtime.sendMessage({ type: "GET_BACKEND_STATUS" });
      state.backendOnline = !!(resp && resp.ok);
    } catch {
      state.backendOnline = false;
    }
    if (state.isSaving) return;
    updateUI();
  }

  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(checkBackend, POLL_INTERVAL);
  }

  function stopPolling() {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }

  function updateUI() {
    if (!btnEl) return;
    if (state.isSaving) return;
    applyUI();
    setIconOnline();
  }

  // --- Download ---
  async function handleClick() {
    if (state.isSaving) return;
    if (!state.backendOnline) {
      showToast("Backend offline \u2014 start music_app_pyQT", true);
      return;
    }
    const vid = getVideoId();
    if (!vid) {
      showToast("No YouTube video detected", true);
      return;
    }
    const url = `https://www.youtube.com/watch?v=${vid}`;

    state.isSaving = true;
    setIconSaving();
    applyUI();
    showToast("Saving to Jellyfin...");

    try {
      const result = await browser.runtime.sendMessage({ type: "DOWNLOAD_CURRENT_VIDEO", url });
      if (result && result.ok) {
        setIconSaved();
        applyUI();
        showToast("Saved to Jellyfin");
        setTimeout(() => {
          if (state.isSaving) {
            state.isSaving = false;
            checkBackend();
          }
        }, 2000);
      } else {
        const msg = result?.error || "Failed";
        const display = getErrorMessage(msg);
        setIconFailed();
        applyUI();
        showToast(display, true);
        state.isSaving = false;
        setTimeout(checkBackend, 2500);
      }
    } catch (err) {
      setIconFailed();
      applyUI();
      showToast("Backend offline \u2014 start music_app_pyQT", true);
      state.isSaving = false;
      setTimeout(checkBackend, 2500);
    }
  }

  function getErrorMessage(msg) {
    if (!msg) return "Unknown error";
    if (msg.includes("403") || msg.includes("Forbidden") || msg.includes("YTDLP_FORBIDDEN")) {
      return "YouTube blocked this download. Try cookies-from-browser or update yt-dlp.";
    }
    if (msg.includes("NO_OUTPUT_FILE")) {
      return "Download finished without audio file.";
    }
    if (msg.includes("INVALID_URL")) {
      return "This is not a valid YouTube video.";
    }
    if (msg.includes("Backend offline") || msg.includes("Failed to fetch") || msg.includes("NetworkError")) {
      return "Backend offline \u2014 start music_app_pyQT.";
    }
    return msg.length > 50 ? msg.substring(0, 47) + "..." : msg;
  }

  // --- SPA navigation ---
  function onNav() {
    clearTimeout(navTimer);
    navTimer = setTimeout(() => {
      const vid = getVideoId();
      if (vid === state.videoId) return;
      state.videoId = vid;
      hideToast();
      if (state.isSaving) state.isSaving = false;

      if (!vid) {
        if (containerEl) containerEl.style.display = "none";
        return;
      }

      if (containerEl) containerEl.style.display = "";
      state.backendOnline = false;
      checkBackend();
      startPolling();

      browser.runtime.sendMessage({
        type: "YOUTUBE_URL_CHANGED",
        url: window.location.href,
        title: getPageTitle(),
        videoId: vid,
      }).catch(() => {});
    }, 400);
  }

  let navTimer = null;

  // --- Init ---
  function init() {
    const vid = getVideoId();
    if (!vid) return;
    state.videoId = vid;

    createUI();
    checkBackend();
    startPolling();

    const origPushState = history.pushState;
    const origReplaceState = history.replaceState;
    history.pushState = function () {
      origPushState.apply(this, arguments);
      onNav();
    };
    history.replaceState = function () {
      origReplaceState.apply(this, arguments);
      onNav();
    };
    window.addEventListener("popstate", onNav);
    window.addEventListener("yt-navigate-finish", onNav);
  }

  init();
})();
