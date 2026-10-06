// Connect the student's USCF ID: look it up, save it, and import tournaments and results from USCF.
import { h, icon, toast, uscfUrl } from "../dom.js";
import { api } from "../api.js";
import { state } from "../state.js";

const ratingText = (r) => Object.entries(r || {}).map(([k, v]) => `${k[0].toUpperCase()}${k.slice(1)} ${v}`).join(" · ");

export async function uscfCard({ onImported, onSaved } = {}) {
  let info = await api("/api/uscf");
  const box = h("div", { class: "card stack-s", id: "uscf-card" });

  const remember = (next) => {
    info = next;
    state.player = { ...state.player, uscf_id: next.uscf_id, uscf_name: next.name, rating: next.player_rating, rating_system: next.player_rating_system };
    if (onSaved) onSaved(next);
    paint();
  };

  function explain() {
    return h("p", { class: "muted small", style: "margin:0" },
      "USCF publishes each player's tournaments and results, but not the moves of the games. Importing fills in every tournament and round (opponent, color, result) and the results table. ",
      "You then add the moves of each game to its round so the coach can study it. Only the ID is sent to USCF: to look up the name and rating when you save it, and to import when you press the button.");
  }

  function idForm(editing) {
    const input = h("input", { class: "input", id: "us-id", inputmode: "numeric", maxlength: 12, placeholder: "8-digit USCF ID", value: info.uscf_id || "", "aria-label": "USCF ID", style: "max-width:220px" });
    const result = h("div", { class: "alert info hidden", role: "status" });
    const say = (kind, text) => { result.className = `alert ${kind}`; result.textContent = text; };
    const check = h("button", { class: "btn", type: "button", id: "us-check", onclick: async () => {
      check.disabled = true; say("info", "Looking that ID up at USCF…");
      try {
        const m = await api(`/api/uscf/lookup?id=${encodeURIComponent(input.value)}`);
        say("good", `${m.name}${m.status ? ` (${m.status})` : ""}${ratingText(m.ratings) ? ` · ${ratingText(m.ratings)}` : ""}. Is this the right player? If so, press Save ID.`);
      } catch (e) { say("bad", e.message); }
      check.disabled = false;
    } }, icon("search"), "Check the ID");
    const save = h("button", { class: "btn primary", type: "button", id: "us-save", onclick: async () => {
      try {
        const next = await api("/api/uscf/id", { method: "PUT", body: { uscf_id: input.value } });
        remember(next);
        toast(next.uscf_id && next.ratings && next.ratings.regular ? `USCF ID saved · rating ${next.ratings.regular}` : "USCF ID saved");
      }
      catch (e) { say("bad", e.message); }
    } }, "Save ID");
    return h("div", { class: "stack-s" },
      h("div", { class: "row" }, input, check, save, editing ? h("button", { class: "btn small", type: "button", onclick: () => paint() }, "Cancel") : null), result);
  }

  function connected() {
    const status = h("div", { class: "alert info hidden", role: "status", id: "us-status" });
    const say = (kind, text) => { status.className = `alert ${kind}`; status.textContent = text; };
    const sync = h("button", { class: "btn small primary", type: "button", id: "us-sync", onclick: async () => {
      sync.disabled = true; say("info", "Contacting USCF. A long history can take up to a minute…");
      try {
        const r = await api("/api/uscf/sync", { method: "POST" });
        info = r.status; state.player = { ...state.player, uscf_name: info.name, rating: info.player_rating, rating_system: info.player_rating_system };
        if (onSaved) onSaved(info);
        const bits = [`${r.events_added} new tournament${r.events_added === 1 ? "" : "s"}`, `${r.games_added} new round${r.games_added === 1 ? "" : "s"}`];
        if (r.games_updated) bits.push(`${r.games_updated} result${r.games_updated === 1 ? "" : "s"} corrected`);
        say("good", `Imported ${bits.join(", ")}. USCF listed ${r.games_seen} game${r.games_seen === 1 ? "" : "s"} in all.`);
        toast("USCF import finished");
        if (onImported) await onImported(r);
        paintHeader();
      } catch (e) { say("bad", e.message); }
      sync.disabled = false;
    } }, icon("refresh"), "Import my games from USCF");
    const header = h("div", {});
    const paintHeader = () => header.replaceChildren(
      h("div", { class: "row", style: "gap:10px;align-items:center" },
        h("h2", { style: "margin:0;display:flex;gap:10px;align-items:baseline;font-variant-numeric:tabular-nums" }, "USCF ID",
          h("a", { href: uscfUrl(info.uscf_id), target: "_blank", rel: "noopener", title: "Open this USCF profile", style: "letter-spacing:.5px" }, info.uscf_id)),
        h("span", { class: "pill good" }, "Connected")),
      h("div", { class: "muted small" }, [ratingText(info.ratings), info.synced_at ? `Last imported ${new Date(info.synced_at * 1000).toLocaleDateString()}` : "Not imported yet"].filter(Boolean).join(" · ")));
    paintHeader();
    // The ID on the left; the three actions on the right, the import standing out by colour.
    return h("div", { class: "stack-s" },
      h("div", { class: "row spread", style: "align-items:flex-start;gap:16px" }, header,
        h("div", { class: "row", style: "gap:6px;justify-content:flex-end" }, sync,
          h("button", { class: "btn small", type: "button", onclick: () => paint(true) }, "Change ID"),
          h("button", { class: "btn small danger", type: "button", onclick: async () => {
            if (!confirm("Forget this USCF ID? Tournaments already imported stay.")) return;
            remember(await api("/api/uscf/id", { method: "PUT", body: { uscf_id: "" } }));
          } }, "Forget ID"))),
      status);
  }

  function paint(editing = false) {
    box.replaceChildren(...[
      info.uscf_id && !editing ? null : h("div", { class: "row spread" }, h("h2", { style: "margin:0" }, "USCF ID"), h("span", { class: "pill gray" }, "Not connected")),
      info.uscf_id && !editing ? connected() : h("div", { class: "stack-s" }, h("p", { style: "margin:0" }, "Enter the USCF ID once and it is remembered. Your USCF rating is then used across the app (your roadmap level too). Find the ID on the membership card or at uschess.org."), idForm(editing)),
      explain()].filter(Boolean));
  }
  paint();
  return box;
}
