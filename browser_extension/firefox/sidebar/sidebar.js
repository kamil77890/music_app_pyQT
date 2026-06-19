(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const statusBadge = $("status-badge");
  const libraryStatus = $("library-status");
  const songList = $("song-list");
  const audioPlayer = $("audio-player");
  const playerSection = $("player-section");

  let allSongs = [];

  // -- backend status --
  async function checkStatus() {
    try {
      const resp = await browser.runtime.sendMessage({ type: "GET_BACKEND_STATUS" });
      if (resp.ok) {
        statusBadge.textContent = "online";
        statusBadge.className = "badge-online";
      } else {
        throw new Error(resp.error);
      }
    } catch {
      statusBadge.textContent = "offline";
      statusBadge.className = "badge-offline";
    }
  }

  // -- library --
  async function loadLibrary(q) {
    libraryStatus.textContent = "Loading...";
    songList.innerHTML = "";
    try {
      const resp = await browser.runtime.sendMessage({ type: "GET_LIBRARY", q: q || "" });
      if (!resp.ok) throw new Error(resp.error);
      allSongs = resp.data.songs || [];
      renderSongs(allSongs);
      libraryStatus.textContent = allSongs.length
        ? `${allSongs.length} song${allSongs.length !== 1 ? "s" : ""}`
        : "Library is empty. Download some music!";
    } catch (err) {
      libraryStatus.textContent = "Error: " + err.message;
    }
  }

  function renderSongs(songs) {
    songList.innerHTML = "";
    for (const song of songs) {
      const li = document.createElement("li");
      li.className = "song-item";

      const cover = document.createElement("img");
      cover.className = "song-cover";
      cover.src = song.cover || song.thumbnail || "";
      cover.alt = "";
      cover.onerror = () => { cover.src = ""; cover.style.background = "var(--surface2)"; };

      const info = document.createElement("div");
      info.className = "song-info";
      info.innerHTML = `
        <div class="song-title">${esc(song.title || "Unknown")}</div>
        <div class="song-artist">${esc(song.artist || "Unknown Artist")} · ${esc(song.album || "")}</div>
      `;

      const playBtn = document.createElement("button");
      playBtn.className = "song-play";
      playBtn.textContent = "▶";
      playBtn.title = "Play";
      playBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        playSong(song);
      });

      li.appendChild(cover);
      li.appendChild(info);
      li.appendChild(playBtn);
      songList.appendChild(li);
    }
  }

  function playSong(song) {
    const streamUrl = getStreamUrl(song);
    if (!streamUrl) return;
    audioPlayer.src = streamUrl;
    playerSection.classList.add("active");
    audioPlayer.play().catch(() => {});
  }

  function esc(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  // -- save current tab --
  async function saveCurrentTab() {
    try {
      const tabResp = await browser.runtime.sendMessage({ type: "GET_CURRENT_TAB_URL" });
      if (!tabResp.ok || !tabResp.url) {
        libraryStatus.textContent = "No YouTube tab active";
        return;
      }
      const url = tabResp.url;
      if (!url.includes("youtube.com") && !url.includes("youtu.be")) {
        libraryStatus.textContent = "Active tab is not YouTube";
        return;
      }
      libraryStatus.textContent = "Saving...";
      const result = await browser.runtime.sendMessage({ type: "DOWNLOAD_URL", url });
      if (result && result.ok) {
        libraryStatus.textContent = `Saved: ${result.title || ""}`;
        loadLibrary($("input-search").value);
      } else {
        libraryStatus.textContent = "Failed: " + (result?.error || "unknown error");
      }
    } catch (err) {
      libraryStatus.textContent = "Error: " + err.message;
    }
  }

  // -- events --
  $("btn-refresh").addEventListener("click", () => {
    checkStatus();
    loadLibrary($("input-search").value);
  });

  $("btn-save-tab").addEventListener("click", saveCurrentTab);

  $("btn-save-url").addEventListener("click", async () => {
    const url = $("input-url").value.trim();
    if (!url) return;
    $("library-status").textContent = "Saving...";
    try {
      const result = await browser.runtime.sendMessage({ type: "DOWNLOAD_URL", url });
      if (result && result.ok) {
        $("library-status").textContent = `Saved: ${result.title || ""}`;
        $("input-url").value = "";
        loadLibrary($("input-search").value);
      } else {
        $("library-status").textContent = "Failed: " + (result?.error || "unknown error");
      }
    } catch (err) {
      $("library-status").textContent = "Error: " + err.message;
    }
  });

  let searchTimer = null;
  $("input-search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadLibrary($("input-search").value), 300);
  });

  // -- init --
  checkStatus();
  loadLibrary();
})();
