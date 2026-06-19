(function () {
  "use strict";

  const backendStatusEl = document.getElementById("backend-status");
  const urlDisplay = document.getElementById("current-url-display");

  async function checkBackend() {
    try {
      const resp = await browser.runtime.sendMessage({ type: "GET_BACKEND_STATUS" });
      if (resp.ok) {
        backendStatusEl.textContent = "backend online";
        backendStatusEl.className = "online";
      } else {
        throw new Error(resp.error);
      }
    } catch {
      backendStatusEl.textContent = "backend offline";
      backendStatusEl.className = "offline";
    }
  }

  async function showCurrentTab() {
    try {
      const resp = await browser.runtime.sendMessage({ type: "GET_CURRENT_TAB_URL" });
      if (resp.ok && resp.url) {
        const u = new URL(resp.url);
        if (u.hostname.includes("youtube")) {
          urlDisplay.textContent = "YouTube: " + u.searchParams.get("v") || u.pathname;
        } else {
          urlDisplay.textContent = "";
        }
      }
    } catch {}
  }

  document.getElementById("btn-open-sidebar").addEventListener("click", () => {
    browser.sidebarAction.open().catch(() => {
      urlDisplay.textContent = "Open sidebar manually via View → Sidebar → Music Library";
    });
  });

  document.getElementById("btn-save-tab").addEventListener("click", async () => {
    const btn = document.getElementById("btn-save-tab");
    btn.textContent = "Saving...";
    btn.disabled = true;
    try {
      const tabResp = await browser.runtime.sendMessage({ type: "GET_CURRENT_TAB_URL" });
      if (!tabResp.ok || !tabResp.url) {
        urlDisplay.textContent = "No YouTube tab found";
        return;
      }
      const result = await browser.runtime.sendMessage({ type: "DOWNLOAD_URL", url: tabResp.url });
      if (result && result.ok) {
        urlDisplay.textContent = `Saved: ${result.title || ""}`;
      } else {
        urlDisplay.textContent = "Failed: " + (result?.error || "unknown");
      }
    } catch (err) {
      urlDisplay.textContent = "Error: " + err.message;
    } finally {
      btn.textContent = "Save current YouTube";
      btn.disabled = false;
    }
  });

  checkBackend();
  showCurrentTab();
})();
