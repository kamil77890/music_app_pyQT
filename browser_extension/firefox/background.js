// --- Badge state ---
let _badgeBackendOnline = false;
let _badgeTabId = null;
let _badgeTimer = null;

function clearBadgeTimer() {
  if (_badgeTimer) { clearTimeout(_badgeTimer); _badgeTimer = null; }
}

function _badgeOpts() {
  return _badgeTabId ? { tabId: _badgeTabId } : {};
}

function updateBadge() {
  clearBadgeTimer();
  const opts = _badgeOpts();
  if (!_badgeBackendOnline) {
    browser.browserAction.setBadgeText({ text: "!", ...opts }).catch(() => {});
    browser.browserAction.setBadgeBackgroundColor({ color: "#ef5350", ...opts }).catch(() => {});
    browser.browserAction.setTitle({ title: "Backend offline \u2014 start music_app_pyQT", ...opts }).catch(() => {});
    return;
  }
  const isYT = currentTabInfo.isYouTube;
  if (isYT) {
    browser.browserAction.setBadgeText({ text: "YT", ...opts }).catch(() => {});
    browser.browserAction.setBadgeBackgroundColor({ color: "#26a69a", ...opts }).catch(() => {});
    browser.browserAction.setTitle({ title: "Save to Jellyfin", ...opts }).catch(() => {});
  } else {
    browser.browserAction.setBadgeText({ text: "", ...opts }).catch(() => {});
    browser.browserAction.setTitle({ title: "Music Library Saver", ...opts }).catch(() => {});
  }
}

function setBadgeSaving() {
  clearBadgeTimer();
  const opts = _badgeOpts();
  browser.browserAction.setBadgeText({ text: "\u00B7\u00B7\u00B7", ...opts }).catch(() => {});
  browser.browserAction.setBadgeBackgroundColor({ color: "#42a5f5", ...opts }).catch(() => {});
  browser.browserAction.setTitle({ title: "Saving to Jellyfin...", ...opts }).catch(() => {});
}

function setBadgeSaved() {
  clearBadgeTimer();
  const opts = _badgeOpts();
  browser.browserAction.setBadgeText({ text: "\u2713", ...opts }).catch(() => {});
  browser.browserAction.setBadgeBackgroundColor({ color: "#66bb6a", ...opts }).catch(() => {});
  browser.browserAction.setTitle({ title: "Saved to Jellyfin", ...opts }).catch(() => {});
  _badgeTimer = setTimeout(() => updateBadge(), 2000);
}

function setBadgeFailed() {
  clearBadgeTimer();
  const opts = _badgeOpts();
  browser.browserAction.setBadgeText({ text: "\u00D7", ...opts }).catch(() => {});
  browser.browserAction.setBadgeBackgroundColor({ color: "#ef5350", ...opts }).catch(() => {});
  browser.browserAction.setTitle({ title: "Download failed", ...opts }).catch(() => {});
  _badgeTimer = setTimeout(() => updateBadge(), 3000);
}

// --- YouTube tab state ---
let currentYouTubeTab = {
  tabId: null,
  url: null,
  title: null,
  videoId: null,
  isYouTube: false,
  updatedAt: null,
};

browser.runtime.onMessage.addListener(async (msg, sender) => {
  switch (msg.type) {
    case "DOWNLOAD_CURRENT_VIDEO": {
      try {
        setBadgeSaving();
        const result = await downloadToLibrary(msg.url);
        if (result && result.ok) {
          setBadgeSaved();
        } else {
          setBadgeFailed();
        }
        return result;
      } catch (err) {
        setBadgeFailed();
        return { ok: false, error: err.message };
      }
    }

    case "GET_BACKEND_STATUS": {
      try {
        const data = await checkHealth();
        _badgeBackendOnline = true;
        updateBadge();
        return { ok: true, data };
      } catch (err) {
        _badgeBackendOnline = false;
        updateBadge();
        return { ok: false, error: "Backend offline. Start music_app_pyQT server on localhost:8000." };
      }
    }

    case "GET_LIBRARY": {
      try {
        const data = await listSongs(msg.q || "");
        return { ok: true, data };
      } catch (err) {
        return { ok: false, error: err.message };
      }
    }

    case "DOWNLOAD_URL": {
      try {
        setBadgeSaving();
        const result = await downloadToLibrary(msg.url);
        if (result && result.ok) {
          setBadgeSaved();
        } else {
          setBadgeFailed();
        }
        return result;
      } catch (err) {
        setBadgeFailed();
        return { ok: false, error: err.message };
      }
    }

    case "GET_CURRENT_TAB_URL": {
      try {
        const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
        return { ok: true, url: tab ? tab.url : null, title: tab ? tab.title : null };
      } catch (err) {
        return { ok: false, error: err.message };
      }
    }

    case "GET_CURRENT_TAB_INFO": {
      try {
        const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
        if (!tab) return { ok: false, error: "No active tab" };
        const url = tab.url || "";
        const isYouTube = url.includes("youtube.com") || url.includes("youtu.be");
        let videoId = "";
        if (isYouTube) {
          try {
            const u = new URL(url);
            videoId = u.searchParams.get("v") || "";
          } catch {}
        }
        currentYouTubeTab.tabId = tab.id;
        currentYouTubeTab.url = url;
        currentYouTubeTab.title = tab.title || "";
        currentYouTubeTab.videoId = videoId;
        currentYouTubeTab.isYouTube = isYouTube;
        currentYouTubeTab.updatedAt = Date.now();
        _badgeTabId = tab.id;
        updateBadge();
        return { ok: true, tab: { id: tab.id, url, title: tab.title || "", isYouTube, videoId } };
      } catch (err) {
        return { ok: false, error: err.message };
      }
    }

    case "YOUTUBE_URL_CHANGED": {
      currentYouTubeTab.tabId = sender.tab ? sender.tab.id : null;
      currentYouTubeTab.url = msg.url || null;
      currentYouTubeTab.title = msg.title || null;
      currentYouTubeTab.videoId = msg.videoId || null;
      currentYouTubeTab.isYouTube = true;
      currentYouTubeTab.updatedAt = Date.now();
      _badgeTabId = sender.tab ? sender.tab.id : null;
      broadcastYouTubeUpdate();
      updateBadge();
      return { ok: true };
    }

    default:
      return { ok: false, error: `Unknown message type: ${msg.type}` };
  }
});

// --- Live tab tracking ---
let currentTabInfo = { id: null, url: "", title: "", isYouTube: false, videoId: "" };

async function updateTabInfo(tabId) {
  try {
    const tab = await browser.tabs.get(tabId);
    if (!tab || !tab.url) return;
    const url = tab.url || "";
    const isYouTube = url.includes("youtube.com") || url.includes("youtu.be");
    let videoId = "";
    if (isYouTube) {
      try {
        const u = new URL(url);
        videoId = u.searchParams.get("v") || "";
      } catch {}
    }
    currentTabInfo = { id: tab.id, url, title: tab.title || "", isYouTube, videoId };
    currentYouTubeTab.tabId = tab.id;
    currentYouTubeTab.url = url;
    currentYouTubeTab.title = tab.title || "";
    currentYouTubeTab.videoId = videoId;
    currentYouTubeTab.isYouTube = isYouTube;
    currentYouTubeTab.updatedAt = Date.now();
    _badgeTabId = tab.id;
    broadcastTabUpdate();
    updateBadge();
  } catch {
    // Tab might have been closed
  }
}

function broadcastTabUpdate() {
  // Send to all sidebar and popup views
  browser.runtime.sendMessage({
    type: "CURRENT_TAB_CHANGED",
    tab: currentTabInfo
  }).catch(() => {}); // Ignore if no receiver (e.g., sidebar not open)
}

function broadcastYouTubeUpdate() {
  browser.runtime.sendMessage({
    type: "CURRENT_TAB_CHANGED",
    tab: {
      id: currentYouTubeTab.tabId,
      url: currentYouTubeTab.url,
      title: currentYouTubeTab.title,
      isYouTube: currentYouTubeTab.isYouTube,
      videoId: currentYouTubeTab.videoId,
    }
  }).catch(() => {});
}

browser.tabs.onActivated.addListener((activeInfo) => {
  updateTabInfo(activeInfo.tabId);
});

browser.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.url || changeInfo.title) {
    // Only update if this is the active tab in the current window
    browser.tabs.query({ active: true, currentWindow: true }).then((tabs) => {
      if (tabs[0] && tabs[0].id === tabId) {
        updateTabInfo(tabId);
      }
    }).catch(() => {});
  }
});

browser.windows.onFocusChanged.addListener((windowId) => {
  if (windowId !== browser.windows.WINDOW_ID_NONE) {
    browser.tabs.query({ active: true, windowId }).then((tabs) => {
      if (tabs[0]) updateTabInfo(tabs[0].id);
    }).catch(() => {});
  }
});

// Initialize on load
browser.tabs.query({ active: true, currentWindow: true }).then((tabs) => {
  if (tabs[0]) updateTabInfo(tabs[0].id);
}).catch(() => {});
