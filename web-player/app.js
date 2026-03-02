const bookSelect = document.getElementById("bookSelect");
const reloadBtn = document.getElementById("reloadBtn");
const audio = document.getElementById("audio");
const currentTimeEl = document.getElementById("currentTime");
const durationEl = document.getElementById("duration");
const bookmarkLabel = document.getElementById("bookmarkLabel");
const saveBookmarkBtn = document.getElementById("saveBookmarkBtn");
const bookmarkList = document.getElementById("bookmarkList");

const STORAGE_KEY = "audiobook-player-state-v1";
let state = loadState();
let pendingResumeTime = null;
let library = [];

function loadState() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function formatTime(totalSeconds) {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 0) {
    return "00:00";
  }
  const s = Math.floor(totalSeconds);
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const seconds = s % 60;
  if (hours > 0) {
    return `${hours.toString().padStart(2, "0")}:${minutes
      .toString()
      .padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
  }
  return `${minutes.toString().padStart(2, "0")}:${seconds
    .toString()
    .padStart(2, "0")}`;
}

function currentBook() {
  return bookSelect.value;
}

function ensureBookState(bookName) {
  if (!state[bookName]) {
    state[bookName] = { position: 0, bookmarks: [] };
  }
  if (!Array.isArray(state[bookName].bookmarks)) {
    state[bookName].bookmarks = [];
  }
  return state[bookName];
}

function renderBookmarks() {
  const bookName = currentBook();
  bookmarkList.innerHTML = "";
  if (!bookName) {
    return;
  }

  const book = ensureBookState(bookName);
  const items = [...book.bookmarks].sort((a, b) => a.time - b.time);
  for (const item of items) {
    const li = document.createElement("li");
    li.className = "bookmark-item";

    const meta = document.createElement("div");
    meta.className = "bookmark-meta";

    const title = document.createElement("div");
    title.className = "bookmark-title";
    title.textContent = item.label || `Bookmark @ ${formatTime(item.time)}`;

    const time = document.createElement("div");
    time.className = "bookmark-time";
    time.textContent = formatTime(item.time);

    meta.append(title, time);

    const actions = document.createElement("div");
    actions.className = "bookmark-actions";

    const jumpBtn = document.createElement("button");
    jumpBtn.type = "button";
    jumpBtn.textContent = "Jump";
    jumpBtn.addEventListener("click", () => {
      audio.currentTime = item.time;
      audio.play().catch(() => {});
    });

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "danger";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", () => {
      book.bookmarks = book.bookmarks.filter((b) => b.id !== item.id);
      saveState();
      renderBookmarks();
    });

    actions.append(jumpBtn, deleteBtn);
    li.append(meta, actions);
    bookmarkList.append(li);
  }
}

function syncTimeLabels() {
  currentTimeEl.textContent = formatTime(audio.currentTime);
  durationEl.textContent = formatTime(audio.duration);
}

function saveCurrentPosition() {
  const bookName = currentBook();
  if (!bookName) {
    return;
  }
  const book = ensureBookState(bookName);
  book.position = audio.currentTime || 0;
  saveState();
}

function tryResumePosition() {
  const bookName = currentBook();
  if (!bookName) {
    return;
  }
  if (!Number.isFinite(pendingResumeTime) || pendingResumeTime <= 0) {
    return;
  }
  if (!Number.isFinite(audio.duration) || audio.duration <= 0) {
    return;
  }

  const target = Math.min(pendingResumeTime, Math.max(audio.duration - 0.25, 0));
  if (Math.abs(audio.currentTime - target) > 0.5) {
    audio.currentTime = target;
  }
  pendingResumeTime = null;
}

async function loadBooks() {
  const books = await fetchLibrary();
  library = books;

  bookSelect.innerHTML = "";
  for (const book of books) {
    const opt = document.createElement("option");
    opt.value = book.name;
    opt.textContent = book.name;
    bookSelect.append(opt);
  }

  if (books.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No books found in output/finished";
    bookSelect.append(opt);
    audio.removeAttribute("src");
    renderBookmarks();
    return;
  }

  const lastBook = localStorage.getItem("audiobook-player-last-book");
  if (lastBook && books.some((b) => b.name === lastBook)) {
    bookSelect.value = lastBook;
  } else {
    bookSelect.selectedIndex = 0;
  }
  await loadSelectedBook();
}

async function loadSelectedBook() {
  const bookName = currentBook();
  if (!bookName) {
    return;
  }

  const selected = library.find((book) => book.name === bookName);
  if (!selected || !selected.url) {
    alert("Selected book URL is missing.");
    return;
  }

  localStorage.setItem("audiobook-player-last-book", bookName);
  const book = ensureBookState(bookName);
  pendingResumeTime = Number(book.position) || 0;
  audio.src = selected.url;
  audio.load();
  renderBookmarks();
}

bookSelect.addEventListener("change", () => {
  loadSelectedBook().catch(console.error);
});

reloadBtn.addEventListener("click", () => {
  loadBooks().catch(console.error);
});

audio.addEventListener("loadedmetadata", () => {
  tryResumePosition();
  syncTimeLabels();
});

audio.addEventListener("timeupdate", () => {
  syncTimeLabels();
  saveCurrentPosition();
});

audio.addEventListener("canplay", tryResumePosition);
audio.addEventListener("durationchange", syncTimeLabels);
audio.addEventListener("seeking", saveCurrentPosition);
audio.addEventListener("seeked", saveCurrentPosition);
audio.addEventListener("pause", saveCurrentPosition);
audio.addEventListener("ended", saveCurrentPosition);
window.addEventListener("beforeunload", saveCurrentPosition);
window.addEventListener("pagehide", saveCurrentPosition);

saveBookmarkBtn.addEventListener("click", () => {
  const bookName = currentBook();
  if (!bookName) {
    return;
  }

  const book = ensureBookState(bookName);
  const label = bookmarkLabel.value.trim();
  const bookmark = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    time: audio.currentTime || 0,
    label,
  };
  book.bookmarks.push(bookmark);
  saveState();
  bookmarkLabel.value = "";
  renderBookmarks();
});

loadBooks().catch((error) => {
  console.error(error);
  alert("Failed to load books. Check /api/books (local mode) or /books.json (public mode).");
});

async function fetchLibrary() {
  const api = await fetchJson("/api/books");
  if (api && Array.isArray(api.books) && api.books.length > 0) {
    return api.books;
  }

  const manifest = await fetchJson("/books.json");
  if (manifest && Array.isArray(manifest.books)) {
    return manifest.books;
  }

  if (api && Array.isArray(api.books)) {
    return api.books;
  }

  throw new Error("No library source found");
}

async function fetchJson(url) {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return await response.json();
  } catch {
    return null;
  }
}
