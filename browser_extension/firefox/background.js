browser.runtime.onMessage.addListener(async (msg, sender) => {
  switch (msg.type) {
    case "DOWNLOAD_CURRENT_VIDEO": {
      try {
        const result = await downloadToLibrary(msg.url);
        return result;
      } catch (err) {
        return { ok: false, error: err.message };
      }
    }

    case "GET_BACKEND_STATUS": {
      try {
        const data = await checkHealth();
        return { ok: true, data };
      } catch (err) {
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
        const result = await downloadToLibrary(msg.url);
        return result;
      } catch (err) {
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
        return { ok: true, tab: { id: tab.id, url, title: tab.title || "", isYouTube, videoId } };
      } catch (err) {
        return { ok: false, error: err.message };
      }
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
    broadcastTabUpdate();
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
