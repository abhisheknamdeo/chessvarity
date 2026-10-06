// Sharing a game: a private link anyone can open, and/or making it public in the community (with an optional question).
import { h, icon, toast, mount } from "./dom.js";
import { api } from "./api.js";
import { openDialog } from "./dialogs.js";

const fullUrl = (path) => `${location.origin}${path}`;

async function copy(text) {
  try { await navigator.clipboard.writeText(text); return true; }
  catch (_) {
    // Older browsers, or no permission: select the text so it can be copied by hand.
    return false;
  }
}

/** The "link" part: create, copy, change what it shows, turn off. */
function linkSection(gameId, initial) {
  let link = initial;
  const box = h("div", { class: "stack-s" });
  const showOpp = h("input", { type: "checkbox", checked: link ? link.show_opponent : false });
  const setLink = async (body) => {
    try { link = (await api(`/api/games/${gameId}/link`, { method: "POST", body })).link; render(); return link; }
    catch (err) { toast(err.message); return null; }
  };
  showOpp.addEventListener("change", () => { if (link) setLink({ show_opponent: showOpp.checked }); });

  function render() {
    if (!link) {
      mount(box,
        h("p", { class: "muted small", style: "margin:0" }, "Make a private link to this game. Anyone you send it to can replay it with the coach's analysis, without an account. You can turn it off at any time."),
        h("div", {}, h("button", { class: "btn primary small", type: "button", onclick: async () => {
          const made = await setLink({ show_opponent: showOpp.checked });
          if (made && await copy(fullUrl(made.path))) toast("Link created and copied. Paste it anywhere to share.");
        } }, icon("link"), "Create a link and copy it")));
      return;
    }
    const url = h("input", { class: "input", readonly: true, value: fullUrl(link.path), "aria-label": "Share link", onclick: (e) => e.target.select() });
    mount(box,
      h("div", { class: "row", style: "gap:8px;flex-wrap:nowrap" }, url,
        h("button", { class: "btn small primary", type: "button", onclick: async () => {
          if (await copy(url.value)) toast("Link copied.");
          else { url.select(); toast("Press Ctrl+C (or ⌘C) to copy the selected link."); }
        } }, icon("copy"), "Copy")),
      h("div", { class: "row small muted", style: "justify-content:space-between;gap:8px;flex-wrap:wrap" },
        h("span", {}, `Opened ${link.views} time${link.views === 1 ? "" : "s"}`),
        h("button", { class: "btn small danger", type: "button", onclick: async () => {
          if (!confirm("Turn this link off? Anyone who has it won't be able to open the game any more.")) return;
          try { await api(`/api/games/${gameId}/link`, { method: "DELETE" }); link = null; render(); toast("The link is off."); }
          catch (err) { toast(err.message); }
        } }, "Turn the link off")));
  }
  render();
  return h("div", { class: "stack-s" },
    h("h3", { style: "margin:0" }, icon("link"), " Share a link"),
    box,
    h("label", { class: "small", style: "display:flex;gap:8px;align-items:center;cursor:pointer" }, showOpp, "Show my opponent's name and the tournament on the link"));
}

/** The "community" part: public to signed-in members, with an optional question. */
function communitySection(gameId, share, done) {
  const question = h("textarea", { class: "textarea", id: "sh-q", rows: 3, maxlength: 500, style: "font-family:inherit;font-size:.95rem;min-height:80px",
    placeholder: "Optional: ask the community something, e.g. \"Where did it go wrong?\" or \"Was 18.Nxe5 a good idea?\"" }, share ? share.question : "");
  const showOpp = h("input", { type: "checkbox", id: "sh-opp", checked: share ? share.show_opponent : false });
  const msg = h("div", { class: "alert bad hidden" });
  const save = async (e) => {
    e.preventDefault();
    try {
      const r = await api(`/api/games/${gameId}/share`, { method: "PUT", body: { question: question.value, show_opponent: showOpp.checked } });
      toast(share ? "Updated." : "Shared with the community.");
      done(r.share);
    } catch (err) { msg.textContent = err.message; msg.classList.remove("hidden"); }
  };
  const unshare = async () => {
    if (!confirm("Remove this game from the community? Comments on it will be removed.")) return;
    try { await api(`/api/games/${gameId}/share`, { method: "DELETE" }); toast("Removed from the community."); done(null); }
    catch (err) { msg.textContent = err.message; msg.classList.remove("hidden"); }
  };
  return h("form", { class: "stack-s", onsubmit: save },
    h("h3", { style: "margin:0" }, icon("users"), share ? " In the community" : " Share with the community"),
    share && share.status === "hidden" ? h("div", { class: "alert bad" }, "An admin has hidden this game from the community.") : null,
    h("p", { class: "muted small", style: "margin:0" }, "Chess Varsity members can replay it, comment and answer your question. They see your display name, never your email."),
    h("div", { class: "field" }, h("label", { for: "sh-q" }, "Your question (optional)"), question),
    h("label", { class: "small", style: "display:flex;gap:8px;align-items:flex-start;cursor:pointer" }, showOpp,
      h("span", {}, "Show my opponent's name and the tournament", h("br"), h("span", { class: "muted" }, "Off: they appear as “Opponent”, and the tournament is not shown."))),
    msg,
    h("div", { class: "row", style: "justify-content:space-between" },
      share ? h("button", { class: "btn small danger", type: "button", onclick: unshare }, "Remove from community") : h("span"),
      h("div", { class: "row" },
        share ? h("a", { class: "btn small", href: `#/community/${share.id}`, onclick: () => done(share) }, "View in community") : null,
        h("button", { class: "btn small primary", type: "submit" }, share ? "Save" : "Share in the community"))));
}

/** The "Share this game" dialog for one of my games. Resolves once it's closed. */
export async function openShareDialog(gameId) {
  let share, link;
  try {
    [share, link] = await Promise.all([api(`/api/games/${gameId}/share`).then((r) => r.share), api(`/api/games/${gameId}/link`).then((r) => r.link)]);
  } catch (err) { toast(err.message); return null; }
  return openDialog((done) => h("div", { class: "stack" },
    h("div", { class: "row", style: "justify-content:space-between" }, h("h2", { style: "margin:0" }, "Share this game"),
      h("button", { class: "icon-btn", type: "button", "aria-label": "Close", onclick: () => done(share) }, icon("x"))),
    linkSection(gameId, link),
    h("hr", { style: "border:0;border-top:1px solid var(--line);margin:0" }),
    communitySection(gameId, share, done)));
}
