// The owner's dashboard: registrations, activity and messages. The server only answers for admin accounts.
import { h, icon, mount, toast, uscfUrl } from "../dom.js";
import { api } from "../api.js";
import { openDialog } from "../dialogs.js";

const when = (ts) => (ts ? new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—");
const day = (ts) => new Date(ts * 1000).toLocaleDateString(undefined, { dateStyle: "medium" });
const KINDS = { contact: "Contact form", idea: "Idea", problem: "Problem", praise: "Praise", other: "Other" };

function tile(label, value, detail, ic) {
  return h("div", { class: "card kpi" }, h("div", { class: "kpi-ic" }, icon(ic)), h("div", { class: "l" }, label),
    h("div", { class: "v" }, String(value)), detail ? h("div", { class: "d muted" }, detail) : null);
}

function signupChart(perDay) {
  const top = Math.max(1, ...perDay.map((d) => d.n));
  const bars = perDay.map((d, i) => {
    const label = new Date(`${d.day}T00:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
    return h("div", { style: "flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;min-width:0", title: `${label}: ${d.n} sign-up${d.n === 1 ? "" : "s"}` },
      h("span", { class: "small muted", style: `font-size:.7rem;visibility:${d.n ? "visible" : "hidden"}` }, String(d.n)),
      h("div", { style: `width:100%;max-width:22px;height:${Math.max(2, Math.round((d.n / top) * 120))}px;border-radius:4px 4px 0 0;background:${d.n ? "var(--brand)" : "var(--line-2)"}` }),
      h("span", { class: "small muted", style: `font-size:.66rem;white-space:nowrap;visibility:${i % 5 === 4 || i === perDay.length - 1 ? "visible" : "hidden"}` }, label));
  });
  return h("div", { role: "img", "aria-label": `Sign-ups per day for the last 30 days, ${perDay.reduce((a, d) => a + d.n, 0)} in total`,
    style: "display:flex;align-items:flex-end;gap:3px;height:170px;padding-top:6px" }, bars);
}

let meId = null;

function accountsTable(accounts) {
  if (!accounts.length) return h("p", { class: "muted", style: "margin:0" }, "No accounts yet.");
  return h("div", { style: "overflow-x:auto" }, h("table", {},
    h("thead", {}, h("tr", {}, ["Name", "Email", "State", "Rating", "USCF", "Joined", "Confirmed", "Games", "Shared", "Community", "Last sign-in", ""].map((t) => h("th", {}, t)))),
    h("tbody", {}, accounts.map((a) => h("tr", {},
      h("td", {}, a.name), h("td", {}, h("a", { href: `mailto:${a.email}` }, a.email), a.phone ? h("div", { class: "small muted" }, h("a", { href: `tel:${a.phone.replace(/[^0-9+]/g, "")}` }, a.phone)) : null),
      h("td", {}, a.state || h("span", { class: "muted" }, "—")),
      h("td", { style: "white-space:nowrap" }, a.rating ? `${a.rating}${a.rating_system && a.rating_system !== "USCF" ? ` ${a.rating_system}` : ""}` : h("span", { class: "muted" }, "—")),
      h("td", {}, a.uscf_id ? h("a", { href: uscfUrl(a.uscf_id), target: "_blank", rel: "noopener", title: "USCF profile" }, a.uscf_id) : h("span", { class: "muted" }, "—")),
      h("td", { style: "white-space:nowrap" }, day(a.joined)),
      h("td", {}, a.confirmed ? h("span", { style: "color:var(--good);font-weight:600" }, "✓ Yes") : h("span", { class: "muted" }, "Not yet")),
      h("td", {}, String(a.games)), h("td", {}, String(a.shared || 0)), h("td", { style: "white-space:nowrap" }, a.points ? `${a.level} · ${a.points}` : h("span", { class: "muted" }, "—")), h("td", { style: "white-space:nowrap" }, when(a.last_sign_in)),
      h("td", {}, a.id === meId ? h("span", { class: "muted small" }, "You") : h("button", { class: "btn small", title: "See the app as this person sees it (read-only)", onclick: async () => {
        try { await api(`/api/admin/view-as/${a.id}`, { method: "POST" }); location.hash = "#/"; location.reload(); } catch (err) { toast(err.message); }
      } }, "View as"),
      a.id === meId ? null : h("button", { class: "btn small danger", style: "margin-left:4px", title: "Delete this account and everything in it", onclick: async () => {
        const typed = prompt(`Delete ${a.name}'s account (${a.email}) with all their games, photos and posts? This can't be undone.

Type their email to confirm:`);
        if (typed === null) return;
        try { await api(`/api/admin/accounts/${a.id}/delete`, { method: "POST", body: { confirm_email: typed } }); toast("Account deleted."); location.reload(); }
        catch (err) { toast(err.message); }
      } }, icon("trash"))))))));
}

function messageList(messages) {
  if (!messages.length) return h("p", { class: "muted", style: "margin:0" }, "No feedback or contact messages yet.");
  return h("div", { class: "stack-s" }, messages.map((m) => h("div", { style: "border-top:1px solid var(--line);padding-top:10px" },
    h("div", { class: "row", style: "justify-content:space-between;gap:8px;flex-wrap:wrap" },
      h("b", {}, `${KINDS[m.category] || m.category} · ${m.name || "Someone"}`),
      h("span", { class: "small muted" }, when(m.created_at))),
    h("div", { class: "small" }, h("a", { href: `mailto:${m.email}` }, m.email), m.page ? h("span", { class: "muted" }, ` · ${m.page}`) : null),
    h("p", { style: "margin:6px 0 0;white-space:pre-wrap" }, m.message),
    m.replied_at ? h("div", { class: "callout small", style: "margin-top:8px" }, h("b", {}, `Replied by ${m.replied_by || "an admin"} · ${when(m.replied_at)}`),
      h("div", { style: "white-space:pre-wrap;margin-top:4px" }, m.reply)) : null,
    h("div", { class: "row", style: "margin-top:8px" },
      m.email ? h("button", { class: "btn small primary", onclick: () => replyTo(m) }, icon("message"), m.replied_at ? "Reply again" : "Reply") : null,
      h("button", { class: "btn small danger", onclick: async () => {
        if (!confirm("Delete this message? This can't be undone.")) return;
        try { await api(`/api/admin/messages/${m.id}`, { method: "DELETE" }); toast("Message deleted."); location.reload(); }
        catch (err) { toast(err.message); }
      } }, icon("trash"), "Delete")))));
}

/** Write a reply: it is emailed to the person (they can answer you back) and kept with the message. */
async function replyTo(m) {
  const sent = await openDialog((done) => {
    const text = h("textarea", { class: "textarea", id: "rp-body", rows: 7, maxlength: 5000, required: true, style: "font-family:inherit;font-size:.95rem" });
    const msg = h("div", { class: "alert bad hidden" });
    setTimeout(() => text.focus(), 30);
    return h("form", { class: "stack", onsubmit: async (e) => {
      e.preventDefault();
      if (!text.value.trim()) { text.focus(); return; }
      try { await api(`/api/admin/messages/${m.id}/reply`, { method: "POST", body: { body: text.value } }); done(true); }
      catch (err) { msg.textContent = err.message; msg.classList.remove("hidden"); }
    } },
      h("h2", { style: "margin:0" }, `Reply to ${m.name || m.email}`),
      h("div", { class: "small muted" }, `To ${m.email}. It's sent by email from Chess Varsity, with the original message quoted underneath. Their answer comes back to you.`),
      h("blockquote", { class: "small", style: "margin:0;padding:8px 12px;border-left:3px solid var(--line-2);white-space:pre-wrap;max-height:140px;overflow:auto" }, m.message),
      h("div", { class: "field" }, h("label", { for: "rp-body" }, "Your reply"), text), msg,
      h("div", { class: "row", style: "justify-content:flex-end" }, h("button", { class: "btn", type: "button", onclick: () => done(null) }, "Cancel"),
        h("button", { class: "btn primary", type: "submit" }, "Send reply")));
  });
  if (sent) { toast("Reply sent."); location.reload(); }
}

function adminsCard() {
  const box = h("div", { class: "stack-s" });
  const email = h("input", { class: "input", type: "email", placeholder: "their@email.com", style: "max-width:280px", "aria-label": "New admin's email" });
  const render = (admins) => mount(box, h("div", { style: "overflow-x:auto" }, h("table", {},
    h("thead", {}, h("tr", {}, ["Email", "Name", "Status", ""].map((t) => h("th", {}, t)))),
    h("tbody", {}, admins.map((a) => h("tr", {},
      h("td", {}, a.email), h("td", {}, a.name || h("span", { class: "muted" }, "No account yet")),
      h("td", { class: "small" }, !a.has_account ? "Becomes admin once they sign up and confirm their email"
        : a.confirmed ? h("span", { style: "color:var(--good);font-weight:600" }, "✓ Active") : "Needs to confirm their email (Profile → Send confirmation link)"),
      h("td", {}, a.permanent ? h("span", { class: "pill gray", title: "Set on the server (CHESSCOACH_ADMIN_EMAILS)" }, "Permanent")
        : h("button", { class: "btn small danger", onclick: async () => {
          if (!confirm(`Remove ${a.email} as an admin?`)) return;
          try { render((await api(`/api/admin/admins/${encodeURIComponent(a.email)}`, { method: "DELETE" })).admins); } catch (err) { toast(err.message); }
        } }, "Remove"))))))));
  api("/api/admin/admins").then((r) => render(r.admins));
  const form = h("form", { class: "row", onsubmit: async (e) => {
    e.preventDefault();
    try { render((await api("/api/admin/admins", { method: "POST", body: { email: email.value } })).admins); email.value = ""; toast("Admin added."); }
    catch (err) { toast(err.message); }
  } }, email, h("button", { class: "btn small primary", type: "submit" }, icon("plus"), "Add admin"));
  return h("div", { class: "card stack-s" }, h("h2", {}, "Admins"),
    h("p", { class: "muted small", style: "margin:0" }, "Admins see this dashboard, can view any account read-only, and moderate the community. An admin's email must be confirmed before it works."),
    box, form);
}

function reportsCard() {
  const box = h("div", { class: "stack-s" }, h("p", { class: "muted", style: "margin:0" }, "Loading…"));
  const load = () => api("/api/admin/reports").then(({ reports }) => mount(box, reports.length ? reports.map((r) => h("div", { style: "border-top:1px solid var(--line);padding-top:10px" },
    h("div", { class: "row", style: "justify-content:space-between;gap:8px;flex-wrap:wrap" },
      h("b", {}, `${r.kind === "share" ? "Shared game" : "Comment"} by ${r.target ? r.target.author : "(deleted)"}`),
      h("span", { class: "small muted" }, `Reported by ${r.reporter || "someone"} · ${when(r.created_at)}`)),
    r.reason ? h("div", { class: "small" }, h("span", { class: "muted" }, "Reason: "), r.reason) : null,
    h("p", { style: "margin:6px 0;white-space:pre-wrap" }, r.target ? r.target.text || h("span", { class: "muted" }, "(no text)") : h("span", { class: "muted" }, "Already deleted.")),
    h("div", { class: "row" },
      r.target ? h("a", { class: "btn small", href: `#/community/${r.target.share_id}` }, "Open") : null,
      r.target ? h("button", { class: "btn small danger", onclick: () => act(r, "hide") }, "Hide it") : null,
      h("button", { class: "btn small", onclick: () => act(r, "dismiss") }, "Keep (dismiss report)"))))
    : h("p", { class: "muted", style: "margin:0" }, "Nothing reported. 🎉")));
  const act = async (r, action) => {
    try { await api("/api/admin/moderate", { method: "POST", body: { kind: r.kind, target_id: r.target_id, action } }); toast(action === "hide" ? "Hidden." : "Dismissed."); load(); }
    catch (err) { toast(err.message); }
  };
  load();
  return h("div", { class: "card stack-s" }, h("h2", {}, "Reported content"), box);
}

export async function adminView() {
  document.title = "Admin · Chess Varsity";
  const data = await api("/api/admin/stats");
  meId = (await api("/api/auth/me")).user.id;
  const t = data.totals;
  const pct = (n) => (t.accounts ? `${Math.round((n / t.accounts) * 100)}% of accounts` : "");
  const messageCount = Object.values(t.messages).reduce((a, n) => a + n, 0);
  return h("div", { class: "stack" },
    h("div", { class: "page-h" },
      h("div", {}, h("h1", {}, "Admin dashboard"), h("p", {}, `Registrations and activity across Chess Varsity. Updated ${when(data.generated_at)}.`)),
      h("button", { class: "btn small", onclick: () => location.reload() }, icon("refresh"), "Refresh")),
    h("div", { class: "grid g4" },
      tile("Accounts", t.accounts, `${t.today} today`, "user"),
      tile("New this week", t.last_7_days, `${t.last_30_days} in 30 days`, "chart"),
      tile("Email confirmed", t.confirmed, pct(t.confirmed), "check"),
      tile("Active this week", t.active_7_days, "signed in during the last 7 days", "flame"),
      tile("Added games", t.with_games, pct(t.with_games), "plus"),
      tile("Games", t.games, `${t.games_analysed} analyzed`, "trophy"),
      tile("Community", data.shared_games, data.open_reports ? `${data.open_reports} report${data.open_reports === 1 ? "" : "s"} to review` : "shared games", "users"),
      tile("Messages", messageCount, Object.entries(t.messages).map(([k, n]) => `${n} ${(KINDS[k] || k).toLowerCase()}`).join(", ") || "none yet", "message")),
    h("div", { class: "card stack-s" }, h("h2", {}, "Sign-ups, last 30 days"), signupChart(data.per_day)),
    h("div", { class: "card stack-s" }, h("h2", {}, `Accounts (${t.accounts})`), accountsTable(data.accounts),
      t.accounts > data.accounts.length ? h("p", { class: "small muted", style: "margin:0" }, `Showing the newest ${data.accounts.length}.`) : null),
    reportsCard(),
    h("div", { class: "card stack-s" }, h("h2", {}, "Latest feedback and contact messages"), messageList(data.messages)),
    adminsCard());
}
