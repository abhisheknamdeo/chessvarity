import { h, icon, toast } from "../dom.js";
import { api } from "../api.js";
import { state, clearSession } from "../state.js";
import { uscfCard } from "./uscf.js";
import { oauthErrorText } from "./auth.js";

export async function profileView(_params, query = {}) {
  document.title = "My profile · Chess Varsity";
  const me = await api("/api/auth/me");
  const player = me.player;

  const name = h("input", { class: "input", value: me.user.display_name, maxlength: 60, id: "pf-name" });
  const email = h("input", { class: "input", type: "email", value: me.user.email, id: "pf-email" });
  const rating = h("input", { class: "input", type: "number", min: 0, max: 3500, id: "pf-rating", value: player.rating === null ? "" : player.rating, placeholder: "Optional" });
  const phone = h("input", { class: "input", type: "tel", id: "pf-phone", autocomplete: "tel", maxlength: 30, value: me.user.phone || "", placeholder: "Optional" });
  const stateSel = h("select", { class: "select", id: "pf-state", autocomplete: "address-level1" },
    h("option", { value: "" }, "Choose…"), (me.states || []).map((st) => h("option", { value: st.code, selected: st.code === me.user.state }, st.name)));
  const fromUscf = h("span", { class: "small muted" });
  const showSource = (p) => { fromUscf.textContent = p.uscf_id && p.rating_system === "USCF" && p.rating !== null ? "Filled in from your USCF ID" : ""; };
  showSource(player);
  const system = h("select", { class: "select", id: "pf-system" }, ["USCF", "FIDE", "Lichess", "Chess.com", "Other"].map((s) => h("option", { selected: s === player.rating_system }, s)));
  const msg = h("div", { class: "alert hidden" });
  const emailStatus = me.user.email_verified
    ? h("span", { class: "small", style: "color:var(--good);font-weight:600" }, "✓ Confirmed")
    : h("span", { class: "small muted" }, "Not confirmed yet · ", h("button", { class: "btn small", type: "button", style: "padding:2px 8px", onclick: async (e) => {
        e.target.disabled = true;
        try { const r = await api("/api/auth/send-verification", { method: "POST" }); toast(r.message); }
        catch (err) { toast(err.message); e.target.disabled = false; }
      } }, "Send confirmation link"));
  const profile = h("form", { class: "stack-s", onsubmit: async (e) => {
    e.preventDefault();
    try {
      const r = await api("/api/auth/me", { method: "PATCH", body: { display_name: name.value, email: email.value, rating: rating.value === "" ? null : +rating.value, rating_system: system.value, phone: phone.value, state: stateSel.value } });
      state.user = r.user; state.player = r.player; showSource(r.player);
      msg.className = "alert good"; msg.textContent = "Saved.";
      if (r.verification_sent) {
        msg.textContent = `Saved. We sent a link to ${r.user.email}: open it to confirm your new email and sign in again.`;
        setTimeout(() => { location.hash = "#/login"; location.reload(); }, 6000);
      }
    } catch (err) { msg.className = "alert bad"; msg.textContent = err.message; }
  } },
    h("div", { class: "form-grid" },
      h("div", { class: "field" }, h("label", { for: "pf-name" }, "My name"), name, h("span", { class: "small muted" }, "The name you play under. It is how games are matched to you.")),
      h("div", { class: "field" }, h("label", { for: "pf-email" }, "Email"), email, emailStatus),
      h("div", { class: "field" }, h("label", { for: "pf-rating" }, "My rating"), rating, fromUscf),
      h("div", { class: "field" }, h("label", { for: "pf-system" }, "Rating system"), system),
      h("div", { class: "field" }, h("label", { for: "pf-phone" }, "Phone number"), phone),
      h("div", { class: "field" }, h("label", { for: "pf-state" }, "State"), stateSel)),
    h("p", { class: "small muted", style: "margin:0" }, "Your phone number and state are private: only you and the site's admins can see them."),
    msg, h("div", {}, h("button", { class: "btn primary small", type: "submit" }, "Save")));

  const hasPassword = me.user.has_password;
  const methods = signInMethods(me, query);
  const cur = h("input", { class: "input", type: "password", autocomplete: "current-password", id: "pw-cur" });
  const nw = h("input", { class: "input", type: "password", autocomplete: "new-password", minlength: 8, id: "pw-new" });
  const pwMsg = h("div", { class: "alert hidden" });
  const password = h("form", { class: "stack-s", onsubmit: async (e) => {
    e.preventDefault();
    try {
      await api("/api/auth/password", { method: "POST", body: { current: cur.value, new: nw.value } });
      pwMsg.className = "alert good"; pwMsg.textContent = hasPassword ? "Password changed. Other devices were signed out." : "Password set. You can now also sign in with your email and this password.";
      cur.value = nw.value = "";
      if (!hasPassword) setTimeout(() => location.reload(), 1500);
    }
    catch (err) { pwMsg.className = "alert bad"; pwMsg.textContent = err.message; }
  } }, hasPassword ? null : h("p", { class: "muted", style: "margin:0" }, "You sign in with Google or Apple. Add a password if you'd also like to sign in with your email."),
    h("div", { class: "form-grid" }, hasPassword ? h("div", { class: "field" }, h("label", { for: "pw-cur" }, "Current password"), cur) : null,
      h("div", { class: "field" }, h("label", { for: "pw-new" }, "New password (8+ characters)"), nw)),
    pwMsg, h("div", {}, h("button", { class: "btn small", type: "submit" }, hasPassword ? "Change password" : "Set a password")));

  const delPw = hasPassword
    ? h("input", { class: "input", type: "password", placeholder: "Your password", style: "max-width:260px", "aria-label": "Your password" })
    : h("input", { class: "input", type: "email", placeholder: "Type your email to confirm", style: "max-width:260px", "aria-label": "Type your email to confirm" });
  const delMsg = h("div", { class: "alert bad hidden" });
  const del = h("div", { class: "stack-s" }, h("p", { class: "muted small", style: "margin:0" }, "Deleting your profile removes your account, all of your games and analysis, your photos and your community posts for good."),
    h("div", { class: "row" }, delPw, h("button", { class: "btn small danger", onclick: async () => {
      if (!confirm("Delete your profile with all of your games, photos and posts? This cannot be undone.")) return;
      try { await api("/api/auth/delete", { method: "POST", body: { password: delPw.value } }); clearSession(); location.hash = "#/register"; location.reload(); }
      catch (err) { delMsg.textContent = err.message; delMsg.classList.remove("hidden"); } } }, icon("trash"), "Delete my profile")), delMsg);

  return h("div", { class: "stack", style: "max-width:820px" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "My profile"), h("p", {}, "Your details, your password and your data. ", h("a", { href: "#/profile", onclick: (e) => { e.preventDefault(); document.getElementById("delete-profile").scrollIntoView({ behavior: "smooth" }); } }, "Delete my profile")))),
    h("div", { class: "card stack-s" }, h("h2", {}, "About me"), profile),
    await uscfCard({ onSaved: (u) => {
      if (u.player_rating !== null && u.player_rating !== undefined) { rating.value = u.player_rating; system.value = u.player_rating_system; }
      showSource({ uscf_id: u.uscf_id, rating: u.player_rating, rating_system: u.player_rating_system });
    } }),
    h("div", { class: "card stack-s" }, h("h2", {}, "My games"), h("p", { class: "muted", style: "margin:0" }, "Download every game you have added as one PGN file, to keep or to use in other chess programs."),
      h("div", {}, h("a", { class: "btn small", href: `/api/players/${player.id}/export.pgn`, download: "" }, icon("download"), "Download my games (PGN)"))),
    methods,
    h("div", { class: "card stack-s" }, h("h2", {}, "Password"), password),
    h("div", { class: "card stack-s" }, h("h2", {}, "Contact us"), h("p", { class: "muted", style: "margin:0" }, "Questions, problems or ideas? We read every message."),
      h("div", {}, h("a", { class: "btn small", href: "#/contact" }, icon("message"), "Write to us"))),
    h("div", { class: "card stack-s", id: "delete-profile" }, h("h2", {}, "Delete my profile"), del));
}

/** Google / Apple accounts connected to this one, with buttons to connect or disconnect. Hidden if neither is switched on. */
function signInMethods(me, query) {
  const names = { google: "Google", apple: "Apple" };
  const on = Object.keys(names).filter((p) => me.providers && me.providers[p]);
  const linked = Object.fromEntries((me.user.identities || []).map((i) => [i.provider, i.email]));
  if (!on.length && !Object.keys(linked).length) return null;
  const msg = h("div", { class: "alert hidden" });
  if (query.linked) { msg.className = "alert good"; msg.textContent = `${names[query.linked] || "Account"} connected. You can use it to sign in from now on.`; }
  if (query.error) { msg.className = "alert bad"; msg.textContent = oauthErrorText(query.error, query.provider); }
  const rows = Object.keys(names).filter((p) => on.includes(p) || linked[p]).map((p) => h("div", { class: "row", style: "justify-content:space-between;gap:10px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:10px" },
    h("div", {}, h("b", {}, names[p]), h("div", { class: "small muted" }, linked[p] ? `Connected${linked[p] ? ` · ${linked[p]}` : ""}` : "Not connected")),
    linked[p]
      ? h("button", { class: "btn small", onclick: async (e) => {
          e.target.disabled = true;
          try { await api(`/api/auth/identities/${p}/disconnect`, { method: "POST" }); toast(`${names[p]} disconnected.`); location.hash = "#/profile"; location.reload(); }
          catch (err) { msg.className = "alert bad"; msg.textContent = err.message; e.target.disabled = false; }
        } }, "Disconnect")
      : h("a", { class: "btn small primary", href: `/api/auth/oauth/${p}/start?link=1` }, `Connect ${names[p]}`)));
  return h("div", { class: "card stack-s" }, h("h2", {}, "Sign-in methods"),
    h("p", { class: "muted", style: "margin:0" }, `Sign in with ${me.user.has_password ? "your email and password, or " : ""}any account connected here.`),
    msg, ...rows);
}
