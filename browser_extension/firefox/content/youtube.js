(function () {
  "use strict";

  let currentVideoId = null;
  let buttonEl = null;
  let statusEl = null;

  function getVideoId() {
    const url = new URL(window.location.href);
    if (url.hostname === "music.youtube.com") {
      return url.searchParams.get("v") || "";
    }
    return url.searchParams.get("v") || "";
  }

  function makeButton() {
    const container = document.createElement("div");
    container.id = "jf-music-saver";
    container.style.cssText =
      "position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;align-items:flex-end;gap:4px;font-family:Arial,sans-serif;";

    const btn = document.createElement("button");
    btn.id = "jf-save-btn";
    btn.textContent = "Save to Jellyfin";
    btn.style.cssText =
      "padding:10px 18px;background:#1e88e5;color:#fff;border:none;border-radius:6px;font-size:14px;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.3);transition:background .15s;";
    btn.addEventListener("mouseenter", () => (btn.style.background = "#1565c0"));
    btn.addEventListener("mouseleave", () => (btn.style.background = "#1e88e5"));

    const status = document.createElement("span");
    status.id = "jf-status";
    status.style.cssText = "font-size:12px;color:#aaa;padding:2px 8px;border-radius:4px;background:rgba(0,0,0,.6);";

    container.appendChild(btn);
    container.appendChild(status);
    document.body.appendChild(container);

    buttonEl = btn;
    statusEl = status;
  }

  function removeButton() {
    const el = document.getElementById("jf-music-saver");
    if (el) el.remove();
    buttonEl = null;
    statusEl = null;
  }

  function setStatus(text, isError) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.style.color = isError ? "#ef5350" : "#81c784";
  }

  async function handleClick() {
    const vid = getVideoId();
    if (!vid) {
      setStatus("No video found", true);
      return;
    }
    const url = `https://www.youtube.com/watch?v=${vid}`;
    setStatus("Saving...");
    try {
      const result = await browser.runtime.sendMessage({ type: "DOWNLOAD_CURRENT_VIDEO", url });
      if (result && result.ok) {
        setStatus("Saved!");
        setTimeout(() => setStatus(""), 3000);
      } else {
        setStatus(result?.error || "Failed", true);
      }
    } catch (err) {
      setStatus("Backend offline?", true);
    }
  }

  function update() {
    const vid = getVideoId();
    if (!vid) {
      if (buttonEl) removeButton();
      return;
    }
    if (vid === currentVideoId && buttonEl) return;
    currentVideoId = vid;
    if (!buttonEl) makeButton();
    buttonEl.onclick = handleClick;
    setStatus("");
  }

  let navTimer = null;
  function onNav() {
    clearTimeout(navTimer);
    navTimer = setTimeout(update, 600);
  }

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

  update();
})();
