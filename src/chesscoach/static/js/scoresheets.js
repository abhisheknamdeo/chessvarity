// Photos of a round's paper scoresheet: take or pick photos, keep them beside the round, open them full size.
import { h, icon, mount, toast } from "./dom.js";
import { openDialog } from "./dialogs.js";

const MAX_SIDE = 2200;  // plenty to read handwriting, and a phone photo shrinks to a few hundred KB

/** Shows how many photos a round has on its button. */
export function photoCount(button, list) {
  mount(button, icon("camera"), list.length ? ` ${list.length} photo${list.length === 1 ? "" : "s"}` : " Add photo");
}

/** Resize in the browser and send as JPEG (also turns iPhone HEIC photos into something every browser shows). */
async function shrink(file) {
  let bitmap;
  try { bitmap = await createImageBitmap(file, { imageOrientation: "from-image" }); }
  catch (_) {
    if (/^image\/(jpeg|png|webp)$/.test(file.type)) return file;  // couldn't decode here; the server checks it again
    throw new Error(`“${file.name}” isn't a photo this browser can read. Please use a JPEG or PNG picture.`);
  }
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale); canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close && bitmap.close();
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Could not prepare the photo."))), "image/jpeg", 0.85));
}

/** Shrink one photo and upload it to `url` (a round's or a game's scoresheets). Resolves to the updated photo list. */
export async function uploadPhoto(url, file) {
  const blob = await shrink(file);
  const res = await fetch(url, { method: "POST", body: blob, credentials: "same-origin",
    headers: { "Content-Type": blob.type || "image/jpeg" } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Upload failed (${res.status}).`);
  return data.sheets;
}

/**
 * The photo dialog. target: {title, sheets, uploadUrl, deleteQuery?}. onChange(list) runs whenever photos are added or removed.
 * (A round from the Tournaments page can be passed as it is.)
 */
export function openScoresheets(target, onChange) {
  if (target.round !== undefined && !target.uploadUrl) {
    target = { title: `Round ${target.round} scoresheet`, sheets: target.scoresheets, uploadUrl: `/api/rounds/${target.id}/scoresheets` };
  }
  let list = target.sheets || [];
  return openDialog((done) => {
    const grid = h("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px" });
    const status = h("div", { class: "small muted", role: "status" });
    const input = h("input", { type: "file", accept: "image/*", multiple: true, style: "display:none" });
    const pick = h("button", { class: "btn primary", type: "button", onclick: () => input.click() }, icon("camera"), "Take or choose photos");

    const render = () => {
      mount(grid, list.length ? list.map((s, i) => h("div", { class: "stack-s", style: "gap:4px" },
        h("a", { href: `/api/scoresheets/${s.id}`, target: "_blank", rel: "noopener", title: "Open full size",
          style: "display:block;aspect-ratio:3/4;border-radius:10px;overflow:hidden;border:1px solid var(--line-2);background:var(--surface-2)" },
          h("img", { src: `/api/scoresheets/${s.id}`, alt: `Scoresheet photo ${i + 1}`, loading: "lazy", style: "width:100%;height:100%;object-fit:cover" })),
        h("button", { class: "btn small", type: "button", onclick: async () => {
          if (!confirm("Delete this photo?")) return;
          const res = await fetch(`/api/scoresheets/${s.id}${target.deleteQuery || ""}`, { method: "DELETE", credentials: "same-origin" });
          const data = await res.json().catch(() => ({}));
          if (!res.ok) { toast(data.detail || "Could not delete the photo."); return; }
          list = data.sheets; onChange(list); render();
        } }, icon("trash"), "Delete")))
        : h("p", { class: "muted", style: "margin:0;grid-column:1/-1" }, "No photos yet. Snap the scoresheet after the game so you never lose the paper."));
      pick.disabled = list.length >= 6;
    };

    input.addEventListener("change", async () => {
      const files = [...input.files];
      input.value = "";
      for (const [n, file] of files.entries()) {
        status.textContent = `Uploading ${n + 1} of ${files.length}…`;
        try { list = await uploadPhoto(target.uploadUrl, file); onChange(list); render(); }
        catch (err) { toast(err.message); break; }
      }
      status.textContent = "";
    });

    render();
    return h("div", { class: "stack" },
      h("h2", { style: "margin:0" }, target.title || "Scoresheet photos"),
      h("p", { class: "muted small", style: "margin:0" }, "Photos stay private to you. Up to 6 here; tap one to see it full size."),
      grid, status,
      h("div", { class: "row", style: "justify-content:space-between" }, pick, input, h("button", { class: "btn", type: "button", onclick: () => done(null) }, "Done")));
  });
}
