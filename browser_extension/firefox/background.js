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
        return { ok: true, url: tab ? tab.url : null };
      } catch (err) {
        return { ok: false, error: err.message };
      }
    }

    default:
      return { ok: false, error: `Unknown message type: ${msg.type}` };
  }
});
