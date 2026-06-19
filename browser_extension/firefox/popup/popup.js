(function () {
  "use strict";

  const backendStatusEl = document.getElementById("backend-status");
  const urlDisplay = document.getElementById("current-url-display");
  const tabStatusLine = document.getElementById("tab-status-line");
  const btnSaveTab = document.getElementById("btn-save-tab");

  async function checkBackend() {
    try {
      const resp = await browser.runtime.sendMessage({ type: "GET_BACKEND_STATUS" });
      if (resp.ok) {
        backendStatusEl.textContent = "online";
        backendStatusEl.className = "online";
      } else {
        throw new Error(resp.error);
      }
    } catch {
      backendStatusEl.textContent = "offline";
      backendStatusEl.className = "offline";
    }
  }

  async function showCurrentTab() {
    try {
      const resp = await browser.runtime.sendMessage({ type: "GET_CURRENT_TAB_INFO" });
      if (resp.ok && resp.tab) {
        const tab = resp.tab;
        if (tab.url) {
          urlDisplay.textContent = tab.title || tab.url;
          urlDisplay.className = "url-display";
        } else {
          urlDisplay.textContent = "No active tab";
          urlDisplay.className = "url-display muted";
        }
        if (tab.isYouTube) {
          tabStatusLine.textContent = "\u2713 YouTube detected";
          tabStatusLine.className = "tab-status youtube";
          btnSaveTab.disabled = false;
        } else {
          tabStatusLine.textContent = "Not a YouTube page";
          tabStatusLine.className = "tab-status not-youtube";
          btnSaveTab.disabled = true;
        }
      } else {
        urlDisplay.textContent = "No tab detected";
        urlDisplay.className = "url-display muted";
        tabStatusLine.textContent = "";
        btnSaveTab.disabled = true;
      }
    } catch {
      urlDisplay.textContent = "Could not detect tab";
      urlDisplay.className = "url-display muted";
      btnSaveTab.disabled = true;
    }
  }

  document.getElementById("btn-open-sidebar").addEventListener("click", () => {
    browser.sidebarAction.open().catch(() => {
      urlDisplay.textContent = "Open sidebar manually via View \u2192 Sidebar \u2192 Music Library";
      urlDisplay.className = "url-display muted";
    });
  });

  document.getElementById("btn-save-tab").addEventListener("click", async () => {
    btnSaveTab.textContent = "Saving...";
    btnSaveTab.disabled = true;
    try {
      const tabResp = await browser.runtime.sendMessage({ type: "GET_CURRENT_TAB_INFO" });
      if (!tabResp.ok || !tabResp.tab || !tabResp.tab.isYouTube) {
        urlDisplay.textContent = "No YouTube tab found";
        urlDisplay.className = "url-display muted";
        return;
      }
      const result = await browser.runtime.sendMessage({ type: "DOWNLOAD_URL", url: tabResp.tab.url });
      if (result && result.ok) {
        urlDisplay.textContent = `Saved: ${result.title || ""}`;
        urlDisplay.className = "url-display";
        tabStatusLine.textContent = "\u2713 Saved to Jellyfin";
        tabStatusLine.className = "tab-status youtube";
      } else {
        const msg = result?.error || "unknown";
        urlDisplay.textContent = msg.length > 60 ? msg.substring(0, 60) + "..." : msg;
        urlDisplay.className = "url-display";
        tabStatusLine.textContent = "\u2717 Failed";
        tabStatusLine.className = "tab-status not-youtube";
      }
    } catch (err) {
      urlDisplay.textContent = err.message;
      urlDisplay.className = "url-display";
      tabStatusLine.textContent = "\u2717 Error";
      tabStatusLine.className = "tab-status not-youtube";
    } finally {
      btnSaveTab.textContent = "Save current YouTube";
      btnSaveTab.disabled = false;
      // Re-disable if tab is no longer YouTube
      showCurrentTab();
    }
  });

  checkBackend();
  showCurrentTab();
})();
