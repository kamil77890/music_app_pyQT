(function () {
  "use strict";

  let currentVideoId = null;
  let containerEl = null;
  let buttonEl = null;
  let statusEl = null;

  function getVideoId() {
    try {
      const url = new URL(window.location.href);
      return url.searchParams.get("v") || "";
    } catch {
      return "";
    }
  }

  function getPageTitle() {
    return document.title || "";
  }

  function makeButton() {
    containerEl = document.createElement("div");
    containerEl.id = "jf-music-saver";
    containerEl.style.cssText =
      "position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;align-items:flex-end;gap:6px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;";

    const btn = document.createElement("button");
    btn.id = "jf-save-btn";
    btn.textContent = "\u266B Save to Jellyfin";
    btn.style.cssText =
      "padding:10px 20px;background:linear-gradient(135deg,#7c4dff,#9155ff);color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;box-shadow:0 4px 16px rgba(124,77,255,0.4);transition:all .15s;letter-spacing:0.3px;";
    btn.addEventListener("mouseenter", () => {
      btn.style.transform = "translateY(-1px)";
      btn.style.boxShadow = "0 6px 20px rgba(124,77,255,0.5)";
    });
    btn.addEventListener("mouseleave", () => {
      btn.style.transform = "";
      btn.style.boxShadow = "0 4px 16px rgba(124,77,255,0.4)";
    });

    const status = document.createElement("span");
    status.id = "jf-status";
    status.style.cssText =
      "font-size:11px;color:#ccc;padding:4px 10px;border-radius:6px;background:rgba(0,0,0,0.6);backdrop-filter:blur(4px);border:1px solid rgba(255,255,255,0.08);transition:all .2s;";

    containerEl.appendChild(btn);
    containerEl.appendChild(status);
    document.body.appendChild(containerEl);

    buttonEl = btn;
    statusEl = status;
  }

  function removeButton() {
    const el = document.getElementById("jf-music-saver");
    if (el) el.remove();
    containerEl = null;
    buttonEl = null;
    statusEl = null;
  }

  function setStatus(text, isError) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.style.color = isError ? "#ef5350" : "#81c784";
    statusEl.style.borderColor = isError ? "rgba(239,83,80,0.3)" : "rgba(129,199,132,0.3)";
  }

  function setSaving() {
    if (!buttonEl) return;
    buttonEl.textContent = "\u23F3 Saving...";
    buttonEl.style.opacity = "0.7";
    buttonEl.style.pointerEvents = "none";
  }

  function setRestore() {
    if (!buttonEl) return;
    buttonEl.textContent = "\u266B Save to Jellyfin";
    buttonEl.style.opacity = "1";
    buttonEl.style.pointerEvents = "auto";
  }

  async function handleClick() {
    const vid = getVideoId();
    if (!vid) {
      setStatus("No video found", true);
      return;
    }
    const url = `https://www.youtube.com/watch?v=${vid}`;
    setStatus("Saving...");
    setSaving();
    try {
      const result = await browser.runtime.sendMessage({ type: "DOWNLOAD_CURRENT_VIDEO", url });
      if (result && result.ok) {
        setStatus("\u2713 Saved!");
        setTimeout(() => setStatus(""), 3000);
      } else {
        const msg = result?.error || "Failed";
        if (msg.includes("403") || msg.includes("Forbidden")) {
          setStatus("YouTube blocked request", true);
        } else {
          setStatus(msg.length > 30 ? msg.substring(0, 30) + "..." : msg, true);
        }
      }
    } catch (err) {
      setStatus("Backend offline?", true);
    } finally {
      setRestore();
    }
  }

  function update() {
    const vid = getVideoId();
    const title = getPageTitle();
    if (!vid) {
      if (containerEl) removeButton();
      return;
    }
    if (vid === currentVideoId && containerEl) return;
    currentVideoId = vid;
    if (!containerEl) makeButton();
    buttonEl.onclick = handleClick;
    setStatus("");

    // Notify background about URL change
    browser.runtime.sendMessage({
      type: "YOUTUBE_URL_CHANGED",
      url: window.location.href,
      title: title,
      videoId: vid
    }).catch(() => {});
  }

  let navTimer = null;
  function onNav() {
    clearTimeout(navTimer);
    navTimer = setTimeout(update, 600);
  }

  // SPA navigation detection
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

  // Initial detection
  update();
})();
