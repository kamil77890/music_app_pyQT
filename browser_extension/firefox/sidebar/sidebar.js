(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const statusBadge = $("status-badge");
  const tabStatusBadge = $("tab-status-badge");
  const tabTitle = $("tab-title");
  const tabUrl = $("tab-url");
  const btnSaveTab = $("btn-save-tab");
  const downloadStatus = $("download-status");
  const statusIcon = $("status-icon");
  const statusText = $("status-text");
  const libraryStatus = $("library-status");
  const groupBreadcrumb = $("group-breadcrumb");
  const groupList = $("group-list");
  const songList = $("song-list");
  const audioPlayer = $("audio-player");
  const playerSection = $("player-section");
  const playerTitle = $("player-title");

  let allSongs = [];
  let libraryGroups = [];
  let selectedGroup = null;
  let selectedArtist = null;
  let activeFilter = "All";
  let tabInfo = null;
  let pollingTimer = null;

  // --- Status helpers ---
  function setStatus(state, text) {
    downloadStatus.className = "status-" + state;
    statusText.textContent = text;
    if (state === "idle") {
      statusIcon.textContent = "\u23F3";
    } else if (state === "saving") {
      statusIcon.textContent = "\u23F3";
    } else if (state === "saved") {
      statusIcon.textContent = "\u2713";
    } else if (state === "failed") {
      statusIcon.textContent = "\u2717";
    }
  }

  function getErrorMessage(err) {
    if (!err) return "Unknown error";
    const msg = typeof err === "string" ? err : (err.message || err.error || String(err));
    if (msg.includes("Backend offline") || msg.includes("Failed to fetch") || msg.includes("NetworkError")) {
      return "Backend offline. Start music_app_pyQT on localhost:8000.";
    }
    if (msg.includes("YTDLP_FORBIDDEN") || msg.includes("403")) {
      return "YouTube blocked the download request. Try updating yt-dlp or enable cookies-from-browser in backend settings.";
    }
    if (msg.includes("NO_OUTPUT_FILE")) {
      return "Download finished without an audio file. Try another video or update yt-dlp.";
    }
    if (msg.includes("INVALID_URL") || msg.includes("invalid")) {
      return "This is not a valid YouTube URL.";
    }
    return msg;
  }

  // --- Backend status ---
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

  // --- Tab info ---
  function updateTabUI(info) {
    tabInfo = info;
    if (!info || !info.url) {
      tabTitle.textContent = "No active tab detected";
      tabTitle.className = "tab-title text-muted";
      tabUrl.textContent = "";
      tabStatusBadge.textContent = "No tab";
      tabStatusBadge.className = "tab-status-badge tab-unknown";
      btnSaveTab.disabled = true;
      return;
    }

    tabTitle.textContent = info.title || "(untitled)";
    tabTitle.className = "tab-title";
    tabUrl.textContent = info.url;

    if (info.isYouTube) {
      tabStatusBadge.textContent = "YouTube detected";
      tabStatusBadge.className = "tab-status-badge tab-youtube";
      btnSaveTab.disabled = false;
    } else {
      tabStatusBadge.textContent = "Not a YouTube page";
      tabStatusBadge.className = "tab-status-badge tab-not-youtube";
      btnSaveTab.disabled = true;
    }
  }

  async function fetchTabInfo() {
    try {
      const resp = await browser.runtime.sendMessage({ type: "GET_CURRENT_TAB_INFO" });
      if (resp.ok) {
        updateTabUI(resp.tab);
      }
    } catch {}
  }

  // --- Library ---
  function showLibraryError(err) {
    const message = "Error: " + (err && err.message ? err.message : String(err));
    if (libraryStatus) {
      libraryStatus.textContent = message;
    } else {
      setStatus("failed", message);
    }
  }

  async function loadLibrary(q) {
    const query = (q || "").trim();
    const showSearchResults = Boolean(query);
    songList.innerHTML = "";
    $("empty-state").style.display = "none";
    try {
      const resp = await browser.runtime.sendMessage({ type: "GET_LIBRARY", q: query });
      if (!resp.ok) throw new Error(resp.error);
      allSongs = resp.data.songs || [];
      renderDynamicFilters(allSongs);
      const visibleSongs = filterSongs(allSongs);
      if (showSearchResults || !groupList) {
        selectedGroup = null;
        selectedArtist = null;
        if (groupList) groupList.innerHTML = "";
        if (groupBreadcrumb) groupBreadcrumb.textContent = showSearchResults ? "Search Results" : "Library";
        renderSongs(visibleSongs);
        if (visibleSongs.length === 0) {
          $("empty-state").style.display = "flex";
        }
      }
    } catch (err) {
      showLibraryError(err);
    }
  }

  async function loadLibraryGroups() {
    if (!groupList) return;
    try {
      const resp = await browser.runtime.sendMessage({ type: "GET_LIBRARY_GROUPS" });
      if (!resp.ok) throw new Error(resp.error);
      libraryGroups = resp.data.groups || [];
      selectedGroup = null;
      selectedArtist = null;
      renderLibraryGroups();
    } catch (err) {
      showLibraryError(err);
    }
  }

  function renderLibraryGroups() {
    if (!groupList) return;
    groupList.innerHTML = "";
    songList.innerHTML = "";
    $("empty-state").style.display = "none";

    if (groupBreadcrumb) {
      const parts = ["Library Groups"];
      if (selectedGroup) parts.push(selectedGroup.name || "Group");
      if (selectedArtist) parts.push(selectedArtist.name || "Artist");
      groupBreadcrumb.textContent = parts.join(" / ");
      groupBreadcrumb.title = selectedGroup ? "Back to library groups" : "Library Groups";
    }

    if (selectedArtist) {
      renderSongs(selectedArtist.tracks || []);
      return;
    }

    const items = selectedGroup ? (selectedGroup.artists || []) : libraryGroups;
    for (const item of items) {
      const li = document.createElement("li");
      li.className = "group-item";
      li.textContent = selectedGroup ? `${item.name} (${item.track_count || 0})` : (item.name || "Ungrouped");
      li.addEventListener("click", () => {
        if (!selectedGroup) {
          selectedGroup = item;
          selectedArtist = null;
        } else {
          selectedArtist = item;
        }
        renderLibraryGroups();
      });
      groupList.appendChild(li);
    }

    if (items.length === 0) {
      $("empty-state").style.display = "flex";
    }
  }

  function collectFilterValues(songs) {
    const values = new Set();
    for (const song of songs) {
      const candidates = [
        song.primary_genre,
        song.style,
        song.subgenre,
        song.collection,
        ...(song.tags || []),
      ];
      for (const value of candidates) {
        const text = String(value || "").trim();
        if (!text || text.toLowerCase() === "unknown genre") continue;
        values.add(text);
      }
    }
    return Array.from(values).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  }

  function renderDynamicFilters(songs) {
    const container = $("library-filters");
    if (!container) return;
    container.innerHTML = "";

    const allButton = document.createElement("button");
    allButton.dataset.filter = "All";
    allButton.className = "filter-chip" + (activeFilter === "All" ? " active" : "");
    allButton.textContent = "All";
    allButton.addEventListener("click", () => applyFilter("All"));
    container.appendChild(allButton);

    for (const label of collectFilterValues(songs)) {
      const button = document.createElement("button");
      button.dataset.filter = label;
      button.className = "filter-chip" + (activeFilter === label ? " active" : "");
      button.textContent = label;
      button.addEventListener("click", () => applyFilter(label));
      container.appendChild(button);
    }
  }

  function applyFilter(filter) {
    activeFilter = filter;
    renderDynamicFilters(allSongs);
    const visibleSongs = filterSongs(allSongs);
    renderSongs(visibleSongs);
    $("empty-state").style.display = visibleSongs.length === 0 ? "flex" : "none";
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
      cover.onerror = () => { cover.src = ""; cover.style.background = "var(--surface-hover)"; };

      const info = document.createElement("div");
      info.className = "song-info";
      const genre = song.primary_genre || song.genre || "Unknown Genre";
      const badges = [song.style, song.subgenre, song.collection].filter(Boolean);
      const chips = [...badges, ...(song.tags || []).slice(0, 4), ...(song.mood || []).slice(0, 2)];
      info.innerHTML = `
        <div class="song-title">${esc(song.title || "Unknown")}</div>
        <div class="song-artist">${esc(song.artist || "Unknown Artist")}</div>
        <div class="song-album">${esc(song.album || "")}</div>
        <div class="song-genre">${esc(genre)}</div>
        <div class="song-tags">${chips.map(chip => `<span class="song-chip">${esc(chip)}</span>`).join("")}</div>
      `;

      const playBtn = document.createElement("button");
      playBtn.className = "song-play";
      playBtn.textContent = "\u25B6";
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

  function filterSongs(songs) {
    if (activeFilter === "All") return songs;
    const needle = activeFilter.toLowerCase();
    return songs.filter(song => {
      const values = [
        song.primary_genre,
        song.genre,
        song.style,
        song.subgenre,
        song.collection,
        ...(song.tags || []),
      ].filter(Boolean).map(value => String(value).toLowerCase());
      return values.some(value => value === needle || value.includes(needle));
    });
  }

  function playSong(song) {
    const streamUrl = getStreamUrl(song);
    if (!streamUrl) return;
    playerTitle.textContent = song.title || "Unknown";
    audioPlayer.src = streamUrl;
    playerSection.classList.add("active");
    audioPlayer.play().catch(() => {});
  }

  function esc(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
  }

  // --- Save current tab ---
  async function saveCurrentTab() {
    if (!tabInfo || !tabInfo.isYouTube || !tabInfo.url) {
      setStatus("failed", "No YouTube tab active");
      return;
    }
    await doSave(tabInfo.url);
  }

  async function doSave(url) {
    setStatus("saving", "Saving...");
    btnSaveTab.disabled = true;
    btnSaveTab.classList.add("saving");
    try {
      const result = await browser.runtime.sendMessage({ type: "DOWNLOAD_URL", url });
      if (result && result.ok) {
        const title = result.title || "";
        setStatus("saved", title ? `Saved: ${title}` : "Saved to Jellyfin");
        const query = $("input-search").value.trim();
        loadLibrary(query);
        if (!query) loadLibraryGroups();
      } else {
        const errMsg = getErrorMessage(result?.error || "unknown error");
        setStatus("failed", errMsg);
      }
    } catch (err) {
      setStatus("failed", getErrorMessage(err));
    } finally {
      btnSaveTab.disabled = false;
      btnSaveTab.classList.remove("saving");
      if (!tabInfo || !tabInfo.isYouTube) btnSaveTab.disabled = true;
    }
  }

  // --- Events ---
  function init() {
    checkStatus();
    fetchTabInfo();
    loadLibrary();
    loadLibraryGroups();

    // Listen for live tab updates from background
    browser.runtime.onMessage.addListener((msg) => {
      if (msg.type === "CURRENT_TAB_CHANGED") {
        updateTabUI(msg.tab);
      }
    });

    // Fallback polling every 2s if background events don't fire
    pollingTimer = setInterval(() => {
      fetchTabInfo();
    }, 2000);
  }

  $("btn-refresh").addEventListener("click", () => {
    const query = $("input-search").value.trim();
    checkStatus();
    loadLibrary(query);
    if (!query) loadLibraryGroups();
    fetchTabInfo();
    setStatus("idle", "Idle");
  });

  $("btn-save-tab").addEventListener("click", saveCurrentTab);

  $("btn-save-url").addEventListener("click", async () => {
    const url = $("input-url").value.trim();
    if (!url) return;
    $("input-url").value = "";
    await doSave(url);
  });

  $("input-url").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      $("btn-save-url").click();
    }
  });

  let searchTimer = null;
  $("input-search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      const query = $("input-search").value.trim();
      if (query) {
        loadLibrary(query);
      } else {
        loadLibrary();
        loadLibraryGroups();
      }
    }, 300);
  });

  if (groupBreadcrumb) {
    groupBreadcrumb.addEventListener("click", () => {
      selectedGroup = null;
      selectedArtist = null;
      renderLibraryGroups();
    });
  }

  $("btn-player-close").addEventListener("click", () => {
    audioPlayer.pause();
    audioPlayer.src = "";
    playerSection.classList.remove("active");
  });

  init();
})();
