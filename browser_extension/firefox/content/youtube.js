(function () {
  "use strict";

  const CONTAINER_ID = "jf-music-saver";
  const POLL_INTERVAL = 5000;
  const TOAST_DURATION = 3500;

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

  // --- SVG download icon ---
  function downloadSVG() {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "22");
    svg.setAttribute("height", "22");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    const path1 = document.createElementNS(ns, "path");
    path1.setAttribute("d", "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4");
    svg.appendChild(path1);
    const path2 = document.createElementNS(ns, "polyline");
    path2.setAttribute("points", "7 10 12 15 17 10");
    svg.appendChild(path2);
    const path3 = document.createElementNS(ns, "line");
    path3.setAttribute("x1", "12");
    path3.setAttribute("y1", "15");
    path3.setAttribute("x2", "12");
    path3.setAttribute("y2", "3");
    svg.appendChild(path3);
    return svg;
  }

  // --- Spinner SVG ---
  function spinnerSVG() {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "20");
    svg.setAttribute("height", "20");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2.5");
    svg.style.animation = "jf-spin 0.8s linear infinite";
    const circle1 = document.createElementNS(ns, "circle");
    circle1.setAttribute("cx", "12");
    circle1.setAttribute("cy", "12");
    circle1.setAttribute("r", "10");
    circle1.setAttribute("stroke", "currentColor");
    circle1.setAttribute("stroke-opacity", "0.2");
    svg.appendChild(circle1);
    const circle2 = document.createElementNS(ns, "path");
    circle2.setAttribute("d", "M12 2a10 10 0 0 1 10 10");
    svg.appendChild(circle2);
    return svg;
  }

  // --- Checkmark SVG ---
  function checkSVG() {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "20");
    svg.setAttribute("height", "20");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2.5");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    const path = document.createElementNS(ns, "polyline");
    path.setAttribute("points", "20 6 9 17 4 12");
    svg.appendChild(path);
    return svg;
  }

  // --- X mark SVG ---
  function xSVG() {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "20");
    svg.setAttribute("height", "20");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2.5");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    const line1 = document.createElementNS(ns, "line");
    line1.setAttribute("x1", "18");
    line1.setAttribute("y1", "6");
    line1.setAttribute("x2", "6");
    line1.setAttribute("y2", "18");
    svg.appendChild(line1);
    const line2 = document.createElementNS(ns, "line");
    line2.setAttribute("x1", "6");
    line2.setAttribute("y1", "6");
    line2.setAttribute("x2", "18");
    line2.setAttribute("y2", "18");
    svg.appendChild(line2);
    return svg;
  }

  function injectSpinKeyframes() {
    if (document.getElementById("jf-spin-style")) return;
    const style = document.createElement("style");
    style.id = "jf-spin-style";
    style.textContent = "@keyframes jf-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }";
    document.head.appendChild(style);
  }

  // --- Create floating icon ---
  function createUI() {
    if (document.getElementById(CONTAINER_ID)) return;

    injectSpinKeyframes();

    containerEl = document.createElement("div");
    containerEl.id = CONTAINER_ID;

    btnEl = document.createElement("button");
    btnEl.id = "jf-floating-btn";
    btnEl.title = "Save to Jellyfin";
    btnEl.appendChild(downloadSVG());

    dotEl = document.createElement("span");
    dotEl.id = "jf-status-dot";

    toastEl = document.createElement("div");
    toastEl.id = "jf-toast";

    containerEl.appendChild(btnEl);
    containerEl.appendChild(dotEl);
    containerEl.appendChild(toastEl);
    document.body.appendChild(containerEl);

    btnEl.addEventListener("click", handleClick);
  }

  function applyButtonStyle() {
    if (!btnEl) return;
    const online = state.backendOnline && !state.isSaving;
    const isTransient = state.isSaving || state.backendOnline === null;
    const offline = !state.backendOnline && !state.isSaving;

    btnEl.style.cssText = [
      "position:fixed",
      "bottom:24px",
      "right:24px",
      "z-index:99999",
      "width:46px",
      "height:46px",
      "border-radius:50%",
      "display:flex",
      "align-items:center",
      "justify-content:center",
      "cursor:" + (online ? "pointer" : "default"),
      "border:2px solid " + (online ? "rgba(76,175,80,0.5)" : offline ? "rgba(239,83,80,0.3)" : "rgba(255,167,38,0.4)"),
      "background:" + (online ? "rgba(20,20,40,0.92)" : offline ? "rgba(20,20,40,0.7)" : "rgba(20,20,40,0.85)"),
      "color:" + (online ? "#81c784" : offline ? "#888" : "#ffa726"),
      "box-shadow:" + (online ? "0 2px 16px rgba(76,175,80,0.3)" : offline ? "0 2px 8px rgba(0,0,0,0.3)" : "0 2px 12px rgba(255,167,38,0.2)"),
      "transition:all 0.2s ease",
      "backdrop-filter:blur(6px)",
      "outline:none",
      "padding:0",
    ].join(";");

    if (online) {
      btnEl.addEventListener("mouseenter", onBtnHoverIn);
      btnEl.addEventListener("mouseleave", onBtnHoverOut);
      btnEl.addEventListener("mousedown", onBtnPress);
      btnEl.addEventListener("mouseup", onBtnRelease);
    } else {
      btnEl.removeEventListener("mouseenter", onBtnHoverIn);
      btnEl.removeEventListener("mouseleave", onBtnHoverOut);
      btnEl.removeEventListener("mousedown", onBtnPress);
      btnEl.removeEventListener("mouseup", onBtnRelease);
    }

    btnEl.title = online ? "Save to Jellyfin" : offline ? "Backend offline \u2014 start music_app_pyQT" : "Saving to Jellyfin...";

    dotEl.style.cssText = [
      "position:fixed",
      "bottom:20px",
      "right:20px",
      "z-index:100000",
      "width:10px",
      "height:10px",
      "border-radius:50%",
      "background:" + (online ? "#4caf50" : offline ? "#ef5350" : "#ffa726"),
      "border:2px solid rgba(20,20,40,0.95)",
      "transition:background 0.3s ease",
    ].join(";");
  }

  function onBtnHoverIn() {
    if (!btnEl || !state.backendOnline || state.isSaving) return;
    btnEl.style.transform = "scale(1.1)";
    btnEl.style.boxShadow = "0 2px 20px rgba(76,175,80,0.4)";
  }

  function onBtnHoverOut() {
    if (!btnEl) return;
    btnEl.style.transform = "";
    btnEl.style.boxShadow = state.backendOnline ? "0 2px 16px rgba(76,175,80,0.3)" : "0 2px 8px rgba(0,0,0,0.3)";
  }

  function onBtnPress() {
    if (!btnEl) return;
    btnEl.style.transform = "scale(0.92)";
  }

  function onBtnRelease() {
    if (!btnEl) return;
    btnEl.style.transform = "scale(1.08)";
    setTimeout(() => {
      if (btnEl) btnEl.style.transform = "";
    }, 150);
  }

  // --- Toast ---
  function showToast(text, isError) {
    if (!toastEl) return;
    clearTimeout(state.toastTimer);
    toastEl.textContent = text;
    toastEl.style.cssText = [
      "position:fixed",
      "bottom:78px",
      "right:24px",
      "z-index:99999",
      "padding:8px 14px",
      "border-radius:8px",
      "font-size:12px",
      "font-weight:500",
      "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif",
      "background:" + (isError ? "rgba(239,83,80,0.15)" : "rgba(76,175,80,0.15)"),
      "color:" + (isError ? "#ef5350" : "#81c784"),
      "border:1px solid " + (isError ? "rgba(239,83,80,0.3)" : "rgba(76,175,80,0.3)"),
      "backdrop-filter:blur(8px)",
      "box-shadow:0 4px 16px rgba(0,0,0,0.4)",
      "opacity:1",
      "transition:opacity 0.3s ease",
      "max-width:280px",
      "white-space:nowrap",
      "overflow:hidden",
      "text-overflow:ellipsis",
      "pointer-events:none",
    ].join(";");

    state.toastTimer = setTimeout(() => {
      if (toastEl) {
        toastEl.style.opacity = "0";
        setTimeout(() => { if (toastEl) toastEl.style.display = "none"; }, 300);
      }
    }, TOAST_DURATION);
  }

  function hideToast() {
    clearTimeout(state.toastTimer);
    if (toastEl) {
      toastEl.style.opacity = "0";
      toastEl.style.display = "none";
    }
  }

  // --- Icon content swap ---
  function setIconOnline() {
    if (!btnEl) return;
    btnEl.innerHTML = "";
    btnEl.appendChild(downloadSVG());
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

  // --- UI update ---
  function updateUI() {
    if (!btnEl) return;
    if (state.isSaving) return;
    applyButtonStyle();
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
    applyButtonStyle();
    showToast("Saving to Jellyfin...");

    try {
      const result = await browser.runtime.sendMessage({ type: "DOWNLOAD_CURRENT_VIDEO", url });
      if (result && result.ok) {
        setIconSaved();
        showToast("Saved to Jellyfin");
        setTimeout(() => {
          if (state.isSaving) {
            state.isSaving = false;
            checkBackend();
          }
        }, 2000);
      } else {
        const msg = result?.error || "Failed";
        let display = getErrorMessage(msg);
        setIconFailed();
        showToast(display, true);
        state.isSaving = false;
        setTimeout(checkBackend, 2500);
      }
    } catch (err) {
      setIconFailed();
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
      if (state.isSaving) {
        state.isSaving = false;
      }

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

    // SPA detection
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
