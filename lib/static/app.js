async function api(path, payload) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    let msg = `HTTP ${resp.status}`;
    try {
      msg = (await resp.json()).error || msg;
    } catch {}
    throw new Error(msg);
  }
  return resp.json();
}

let fieldsSaved = false;

// Shared modal: item detail (title click) and folder detail, esc / backdrop / ✕ closes.
async function openModal(url) {
  const modal = document.getElementById("modal");
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  modal.querySelector(".modal-body").innerHTML = await resp.text();
  modal.hidden = false;
}

(function modalWiring() {
  const modal = document.getElementById("modal");
  if (!modal) return;
  const prevBtn = document.getElementById("modal-prev");
  const nextBtn = document.getElementById("modal-next");
  const rowIds = [...document.querySelectorAll("tr[data-instance]")].map(
    (r) => r.dataset.instance
  );
  let currentId = null;

  const updateNav = () => {
    const idx = currentId === null ? -1 : rowIds.indexOf(currentId);
    prevBtn.hidden = idx <= 0;
    nextBtn.hidden = idx === -1 || idx >= rowIds.length - 1;
  };

  const openItem = (id) =>
    openModal(`/item/${id}?partial=1`)
      .then(() => {
        currentId = String(id);
        updateNav();
      })
      .catch(() => (window.location = `/item/${id}`));
  window.openItem = openItem;

  const step = (delta) => {
    const idx = rowIds.indexOf(currentId);
    const target = rowIds[idx + delta];
    if (idx !== -1 && target) openItem(target);
  };
  prevBtn.addEventListener("click", () => step(-1));
  nextBtn.addEventListener("click", () => step(1));

  const close = () => {
    modal.hidden = true;
    currentId = null;
    modal.querySelector(".modal-body").innerHTML = "";
    if (fieldsSaved) location.reload();
  };

  document.querySelectorAll("td.title a").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      openItem(a.closest("tr").dataset.instance);
    });
  });
  // whole row is clickable, except interactive parts
  document.querySelectorAll("table.items tbody tr[data-instance]").forEach((row) => {
    row.addEventListener("click", (e) => {
      if (e.target.closest("a, input, button, select, td.dragcell")) return;
      openItem(row.dataset.instance);
    });
  });
  const details = document.getElementById("folder-details");
  if (details) {
    details.addEventListener("click", () => {
      openModal(details.dataset.url)
        .then(() => {
          currentId = null;
          updateNav();
        })
        .catch((err) => alert(err.message));
    });
  }

  modal.addEventListener("click", (e) => {
    if (e.target === modal || e.target.closest(".modal-close")) close();
  });
  document.addEventListener("keydown", (e) => {
    if (modal.hidden) return;
    if (e.key === "Escape") close();
    if (e.target.closest?.("input, textarea, select")) return;
    if (e.key === "ArrowLeft") step(-1);
    if (e.key === "ArrowRight") step(1);
  });

  // deep links: #item-123 opens that item's modal, #folder-details the folder's
  const hash = location.hash.match(/^#item-(\d+)$/);
  if (hash) openItem(hash[1]);
  else if (location.hash === "#folder-details" && details) details.click();
})();

// Mark fields with unsaved edits (label changes visually until saved).
function markDirty(e) {
  const el = e.target.closest(".edit");
  if (!el || !("orig" in el.dataset)) return;
  const field = el.closest(".field");
  if (field) field.classList.toggle("dirty", el.value.trim() !== el.dataset.orig);
}
document.addEventListener("input", markDirty);
document.addEventListener("change", markDirty);

// Save edited fields (delegated: the form lives in the modal or the item page).
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("#save-fields");
  if (!btn) return;
  const fields = btn.closest(".fields");
  const status = fields.querySelector(".save-status");
  const changed = [...fields.querySelectorAll(".edit")].filter(
    (el) => el.value.trim() !== el.dataset.orig
  );
  if (!changed.length) {
    status.textContent = "nothing changed";
    return;
  }
  btn.disabled = true;
  try {
    for (const el of changed) {
      status.textContent = `saving ${el.name}…`;
      if (el.name === "folder") {
        await api("/api/move", {
          instance_id: fields.dataset.instance,
          to_folder_id: el.value,
        });
      } else if (el.name === "paid_price") {
        await api("/api/paid", {
          instance_id: fields.dataset.instance,
          value: el.value.trim(),
        });
      } else {
        await api("/api/field", {
          instance_id: fields.dataset.instance,
          field: el.name,
          value: el.value.trim(),
        });
      }
      el.dataset.orig = el.value.trim();
      const field = el.closest(".field");
      if (field) field.classList.remove("dirty");
    }
    status.textContent = "saved ✓";
    fieldsSaved = true;
    const preview = fields.closest(".detail")?.querySelector("img.labelpreview");
    if (preview) preview.src = preview.src.split("?")[0] + "?t=" + Date.now();
  } catch (err) {
    status.textContent = `error: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
});

// AI folder suggestion: sets the dropdown (unsaved until Save).
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("#suggest-folder");
  if (!btn) return;
  const fields = btn.closest(".fields");
  const reason = fields.querySelector(".suggest-reason");
  btn.disabled = true;
  reason.textContent = "thinking…";
  try {
    const s = await api("/api/suggest_folder", { instance_id: fields.dataset.instance });
    const select = fields.querySelector("[name=folder]");
    select.value = s.folder_id;
    select.dispatchEvent(new Event("change", { bubbles: true }));
    reason.textContent = `suggests ${s.folder}: ${s.reason}`;
  } catch (err) {
    reason.textContent = err.message;
  } finally {
    btn.disabled = false;
  }
});

// Drag an album cover onto a sidebar folder to move the item.
(function dragDrop() {
  let dragged = null;
  document.querySelectorAll("td.dragcell").forEach((cell) => {
    const row = cell.closest("tr");
    cell.addEventListener("dragstart", (e) => {
      dragged = row;
      row.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", row.dataset.instance);
      const img = cell.querySelector("img.thumb");
      if (img) e.dataTransfer.setDragImage(img, 24, 24);
    });
    cell.addEventListener("dragend", () => {
      row.classList.remove("dragging");
      dragged = null;
    });
  });
  document.querySelectorAll(".sidebar a[data-folder]").forEach((target) => {
    target.addEventListener("dragover", (e) => {
      if (!dragged) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      target.classList.add("dragover");
    });
    target.addEventListener("dragleave", () => target.classList.remove("dragover"));
    target.addEventListener("drop", async (e) => {
      e.preventDefault();
      target.classList.remove("dragover");
      const instance = e.dataTransfer.getData("text/plain");
      if (!instance) return;
      try {
        await api("/api/move", { instance_id: instance, to_folder_id: target.dataset.folder });
        location.reload();
      } catch (err) {
        alert(`move failed: ${err.message}`);
      }
    });
  });
})();

// Sync button in the topbar.
(function syncNow() {
  const btn = document.getElementById("sync-now");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "syncing…";
    try {
      await api("/api/sync", {});
      location.reload();
    } catch (err) {
      alert(`sync failed: ${err.message}`);
      btn.disabled = false;
      btn.textContent = "Sync";
    }
  });
})();

// Folder create (sidebar button).
(function folderCreate() {
  const create = document.getElementById("new-folder");
  if (!create) return;
  create.addEventListener("click", async () => {
    const name = prompt("New folder name:");
    if (!name || !name.trim()) return;
    try {
      await api("/api/folders", { name: name.trim() });
      location.reload();
    } catch (err) {
      alert(`create failed: ${err.message}`);
    }
  });
})();

// Folder rename (inside the folder details modal).
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("#rename-folder");
  if (!btn || btn.disabled) return;
  const fields = btn.closest(".fields");
  const input = fields.querySelector("#folder-name");
  const status = fields.querySelector(".save-status");
  const name = input.value.trim();
  if (!name || name === input.dataset.orig) {
    status.textContent = "nothing changed";
    return;
  }
  btn.disabled = true;
  try {
    await api(`/api/folders/${btn.dataset.folder}/rename`, { name });
    location.href = `/folder/${btn.dataset.folder}`;
  } catch (err) {
    status.textContent = `error: ${err.message}`;
    btn.disabled = false;
  }
});

// Folder color palette (in the folder details modal). Saves immediately.
document.addEventListener("click", async (e) => {
  const swatch = e.target.closest(".palette button");
  if (!swatch) return;
  const palette = swatch.closest(".palette");
  try {
    await api(`/api/folders/${palette.dataset.folder}/color`, {
      color: swatch.dataset.color || null,
    });
    palette.querySelectorAll("button").forEach((b) => {
      b.classList.remove("selected");
      b.setAttribute("aria-pressed", "false");
    });
    swatch.classList.add("selected");
    swatch.setAttribute("aria-pressed", "true");
    fieldsSaved = true; // reload on modal close so swatches/chips repaint
  } catch (err) {
    alert(`color failed: ${err.message}`);
  }
});

// Folder delete: reveal destination chooser, then confirm.
document.addEventListener("click", async (e) => {
  if (e.target.closest("#delete-folder-start")) {
    const row = e.target.closest(".actions-row");
    row.querySelector(".delete-confirm").hidden = false;
    e.target.closest("#delete-folder-start").hidden = true;
    return;
  }
  if (e.target.closest("#delete-folder-cancel")) {
    const row = e.target.closest(".actions-row");
    row.querySelector(".delete-confirm").hidden = true;
    row.querySelector("#delete-folder-start").hidden = false;
    return;
  }
  const confirmBtn = e.target.closest("#delete-folder-confirm");
  if (!confirmBtn) return;
  const row = confirmBtn.closest(".actions-row");
  const status = row.querySelector(".delete-status");
  confirmBtn.disabled = true;
  status.textContent = "moving items + deleting…";
  try {
    await api(`/api/folders/${confirmBtn.dataset.folder}/delete`, {
      move_to: row.querySelector("#delete-move-to").value,
    });
    location.href = "/";
  } catch (err) {
    status.textContent = `error: ${err.message}`;
    confirmBtn.disabled = false;
  }
});

// Multi-select + bulk actions.
(function bulkActions() {
  const bar = document.getElementById("bulkbar");
  if (!bar) return;
  const countEl = document.getElementById("bulk-count");
  const action = document.getElementById("bulk-action");
  const apply = document.getElementById("bulk-apply");
  const status = bar.querySelector(".bulk-status");
  const all = document.getElementById("sel-all");
  const boxes = () => [...document.querySelectorAll("input.sel")];
  const selected = () => boxes().filter((b) => b.checked).map((b) => b.dataset.instance);

  const refresh = () => {
    const n = selected().length;
    bar.hidden = n === 0;
    countEl.textContent = `${n} selected`;
    all.checked = n > 0 && n === boxes().length;
  };
  document.addEventListener("change", (e) => {
    if (e.target === all) {
      boxes().forEach((b) => (b.checked = all.checked));
    }
    if (e.target === all || e.target.classList.contains("sel")) refresh();
  });

  apply.addEventListener("click", async () => {
    const ids = selected();
    const act = action.value;
    if (!ids.length || !act) return;
    apply.disabled = true;
    try {
      if (act.startsWith("move:")) {
        const folder = act.slice(5);
        for (let i = 0; i < ids.length; i++) {
          status.textContent = `moving ${i + 1}/${ids.length}…`;
          await api("/api/move", { instance_id: ids[i], to_folder_id: folder });
        }
      } else if (act === "print") {
        if (!confirm(`Print ${ids.length} sleeve labels?`)) return;
        status.textContent = "printing…";
        const result = await api("/api/print", { type: "sleeves", ids });
        status.textContent = result.pdf ? `wrote ${result.printed} to ${result.pdf} ✓` : `printed ${result.printed} ✓`;
        return;
      } else if (act === "enrich") {
        if (!confirm(`Generate and save Style + Summary for ${ids.length} item(s)? This overwrites existing values on Discogs.`)) return;
        for (let i = 0; i < ids.length; i++) {
          status.textContent = `enriching ${i + 1}/${ids.length}…`;
          const draft = await api("/api/generate", { instance_id: ids[i] });
          await api("/api/field", { instance_id: ids[i], field: "style", value: draft.style });
          await api("/api/field", { instance_id: ids[i], field: "summary", value: draft.summary });
        }
      } else if (act === "resync") {
        status.textContent = "resyncing from Discogs…";
        await api("/api/sync", {});
      }
      location.reload();
    } catch (err) {
      status.textContent = `error: ${err.message}`;
    } finally {
      apply.disabled = false;
    }
  });
})();

// AI draft for style + summary: fills the edit fields, user reviews then saves.
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("#generate-ai");
  if (!btn) return;
  const fields = btn.closest(".fields");
  const status = fields.querySelector(".save-status");
  btn.disabled = true;
  status.textContent = "generating…";
  try {
    const draft = await api("/api/generate", { instance_id: fields.dataset.instance });
    fields.querySelector("[name=style]").value = draft.style;
    fields.querySelector("[name=summary]").value = draft.summary;
    status.textContent = `draft from ${draft.source} — review, then Save`;
  } catch (err) {
    status.textContent = `error: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
});

// "Show paid price" toggles the sleeve preview (and what gets printed).
document.addEventListener("change", (e) => {
  if (e.target.id !== "label-paid") return;
  const preview = document.getElementById("sleeve-preview");
  if (preview) {
    preview.src =
      preview.dataset.base + (e.target.checked ? "?paid=1&" : "?") + "t=" + Date.now();
  }
});

// Label printing (delegated: buttons live in the folder panel and the modal).
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("#print-divider, #print-sleeves, #print-sleeve");
  if (!btn) return;
  let payload;
  if (btn.id === "print-divider") {
    payload = { type: "divider", id: btn.dataset.folder };
  } else if (btn.id === "print-sleeves") {
    if (!confirm(`Print ${btn.dataset.count} sleeve labels?`)) return;
    payload = { type: "sleeves", id: btn.dataset.folder };
  } else {
    payload = { type: "sleeve", id: btn.dataset.instance };
    const paidToggle = document.getElementById("label-paid");
    if (paidToggle && paidToggle.checked) payload.paid = true;
  }
  const status = btn.parentElement.querySelector(".print-status");
  btn.disabled = true;
  try {
    const result = await api("/api/print", payload);
    const msg = result.pdf
      ? `wrote ${result.printed} label${result.printed === 1 ? "" : "s"} to ${result.pdf} ✓`
      : `printed ${result.printed} label${result.printed === 1 ? "" : "s"} ✓`;
    if (status) status.textContent = msg;
    else alert(msg);
  } catch (err) {
    if (status) status.textContent = err.message;
    else alert(`print failed: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
});

// Backfill missing/stale prices one at a time (the server throttles Discogs calls).
(async function backfillPrices() {
  const cells = document.querySelectorAll("td.price[data-stale='1']");
  for (const cell of cells) {
    try {
      const resp = await fetch(`/api/price/${cell.dataset.release}`);
      if (!resp.ok) break;
      const data = await resp.json();
      if (data.price != null) {
        cell.textContent = "$" + Math.round(data.price).toLocaleString();
      }
      cell.dataset.stale = "0";
    } catch {
      break;
    }
  }
})();
