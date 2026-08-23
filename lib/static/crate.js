// Crate view: flip through dividers and albums like a record bin.
(function crate() {
  const data = JSON.parse(document.getElementById("crate-data").textContent);
  const entries = data.entries;
  const n = entries.length;
  if (!n) return;

  const stage = document.getElementById("crate-stage");
  const tabs = document.getElementById("crate-tabs");
  const info = document.getElementById("crate-info");
  const backstrip = document.getElementById("crate-back");
  const modal = document.getElementById("modal");
  const DEPTH = 4; // cards visible behind the front one

  let idx = ((data.start % n) + n) % n;
  const hash = location.hash.match(/^#at-(\d+)$/);
  if (hash) idx = ((+hash[1] % n) + n) % n;
  let animating = false;

  const at = (i) => entries[((i % n) + n) % n];

  const sectionAt = (i) => {
    for (let k = 0; k <= n; k++) {
      const e = at(i - k);
      if (e.type === "divider") return e;
    }
    return null;
  };
  const nextDividerIndex = (i) => {
    for (let k = 1; k <= n; k++) {
      if (at(i + k).type === "divider") return ((i + k) % n + n) % n;
    }
    return i;
  };

  function card(e, depth) {
    const el = document.createElement("div");
    el.className = `crate-card depth-${depth}` + (e.type === "divider" ? " is-divider" : "");
    if (e.type === "album") {
      const cover = document.createElement(e.cover ? "img" : "div");
      cover.className = "crate-cover" + (e.cover ? "" : " noimg");
      if (e.cover) {
        cover.src = e.cover;
        cover.alt = "";
        cover.draggable = false;
      }
      el.appendChild(cover);
      if (depth === 0) {
        const label = document.createElement("img");
        label.className = "crate-label";
        label.src = `/labels/sleeve/${e.instance_id}.png`;
        label.alt = `label: ${e.title}`;
        label.title = "open album details";
        label.dataset.instance = e.instance_id;
        label.draggable = false;
        el.appendChild(label);
      }
    } else {
      el.style.background = e.color;
      const tab = document.createElement("div");
      tab.className = `crate-divider-tab tab-${["left", "center", "right"][e.folder_id % 3]}`;
      tab.style.background = e.color;
      const label = document.createElement("img");
      label.className = "crate-divider-label";
      label.src = `/labels/divider/${e.folder_id}.png`;
      label.alt = `divider: ${e.name}`;
      label.title = "open folder details";
      label.dataset.folder = e.folder_id;
      label.draggable = false;
      tab.appendChild(label);
      el.appendChild(tab);
    }
    return el;
  }

  function render() {
    stage.innerHTML = "";
    for (let d = DEPTH; d >= 0; d--) {
      stage.appendChild(card(at(idx + d), d));
    }
    const e = at(idx);
    const section = sectionAt(idx);
    info.textContent =
      `${((idx % n) + n) % n + 1} / ${n}` +
      (section ? ` · ${section.name}` : "") +
      (e.type === "album" ? ` · ${e.artist} — ${e.title}` : "");

    tabs.innerHTML = "";
    if (section) {
      tabs.appendChild(tab(section, "current"));
    }
    const nd = at(nextDividerIndex(idx));
    if (nd && nd !== section) tabs.appendChild(tab(nd, "next"));
  }

  function tab(divider, kind) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `crate-tab btn-plain crate-tab-${kind}`;
    b.style.background = divider.color;
    b.textContent = kind === "next" ? `${divider.name} ›` : divider.name;
    b.title = kind === "next" ? "jump to next section" : "open folder details";
    b.dataset.folder = divider.folder_id;
    b.dataset.kind = kind;
    return b;
  }

  function advance() {
    if (animating) return;
    animating = true;
    const front = stage.querySelector(".depth-0");
    if (front) front.classList.add("flip");
    setTimeout(() => {
      idx = ((idx + 1) % n + n) % n;
      animating = false;
      render();
    }, 240);
  }

  function back() {
    if (animating) return;
    idx = ((idx - 1) % n + n) % n;
    render();
  }

  stage.addEventListener("click", (e) => {
    const label = e.target.closest(".crate-label");
    if (label) {
      window.openItem(label.dataset.instance);
      return;
    }
    const divLabel = e.target.closest(".crate-divider-label");
    if (divLabel) {
      openModal(`/folder/${divLabel.dataset.folder}/details`).catch(() => {});
      return;
    }
    advance();
  });
  backstrip.addEventListener("click", back);
  tabs.addEventListener("click", (e) => {
    const t = e.target.closest(".crate-tab");
    if (!t) return;
    if (t.dataset.kind === "next") {
      idx = nextDividerIndex(idx);
      render();
    } else {
      openModal(`/folder/${t.dataset.folder}/details`).catch(() => {});
    }
  });
  document.addEventListener("keydown", (e) => {
    if (!modal.hidden) return;
    if (e.key === "ArrowRight" || e.key === " ") {
      e.preventDefault();
      advance();
    }
    if (e.key === "ArrowLeft") back();
  });

  render();
})();
