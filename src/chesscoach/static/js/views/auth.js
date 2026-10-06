import { h, mount, icon } from "../dom.js";
import { api } from "../api.js";
import { drawBoard } from "../board.js";
import { contactForm } from "./contact.js";

// The end of Morphy's Opera Game (Paris, 1858): White has just played Rd8 and it is checkmate.
const OPERA_END = "1n1Rkb1r/p4ppp/4q3/4p1B1/4P3/8/PPP2PPP/2K5 b k - 1 17";

function art() {
  const board = h("div", { class: "board" });
  drawBoard(board, OPERA_END, { orient: "white", lastMove: "b8d8" });
  return h("div", { class: "art" },
    h("div", { class: "brand", style: "padding:0" }, h("span", { class: "logo" }, h("img", { src: "/static/logo.svg", alt: "" })), "Chess Varsity", h("span", { class: "beta" }, "BETA")),
    h("h1", {}, "Get better with every game you play."),
    h("p", { style: "font-size:1.05rem;max-width:38ch" }, "Add every game you play. The coach finds the habits that cost you points, keeps your tournaments and training in one place, and sets the practice that fixes them."),
    h("ul", { class: "clean" },
      h("li", {}, icon("target"), h("span", {}, h("b", {}, "See what went wrong"), "Threats you missed, attacks you skipped, wins that slipped away.")),
      h("li", {}, icon("flag"), h("span", {}, h("b", {}, "Plan the season"), "Tournaments, registration and hotel flags, classes and a calendar.")),
      h("li", {}, icon("puzzle"), h("span", {}, h("b", {}, "Practice what matters"), "Puzzles from your own games, model games, and an opening library.")),
      h("li", {}, icon("star"), h("span", {}, h("b", {}, "Coming soon: AI coaching"), "We're bringing AI to Chess Varsity: explanations of your games and positions in plain words, at your level."))),
    h("figure", { class: "diagram" }, board, h("figcaption", {}, "Morphy v. Duke of Brunswick and Count Isouard, Paris 1858. White mates with 17.Rd8#.")));
}

const TITLES = {
  login: "Sign in", register: "Create account", check: "Check your email", forgot: "Forgot password",
  reset: "Choose a new password", verify: "Confirm your email", contact: "Contact us",
};

function field(id, label, input, hint) {
  return h("div", { class: "field" }, h("label", { for: id }, label), input, hint ? h("span", { class: "small muted" }, hint) : null);
}

function alertBox(kind = "bad") { return h("div", { class: `alert ${kind} hidden`, role: kind === "bad" ? "alert" : "status" }); }
function say(box, kind, text) { box.className = `alert ${kind}`; box.textContent = text; }
// Official marks, drawn inline (the page's security policy allows no outside images).
const SVG_NS = "http://www.w3.org/2000/svg";
function mark(paths, fill) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("width", "18"); svg.setAttribute("height", "18"); svg.setAttribute("aria-hidden", "true");
  for (const [d, color] of paths) {
    const p = document.createElementNS(SVG_NS, "path");
    p.setAttribute("d", d); p.setAttribute("fill", color || fill);
    svg.append(p);
  }
  return svg;
}
const GOOGLE_MARK = [
  ["M23.5 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.45a5.52 5.52 0 01-2.39 3.62v3h3.87c2.26-2.09 3.57-5.16 3.57-8.81z", "#4285F4"],
  ["M12 24c3.24 0 5.96-1.07 7.95-2.92l-3.87-3c-1.08.72-2.45 1.15-4.08 1.15-3.13 0-5.79-2.12-6.74-4.97H1.26v3.1A12 12 0 0012 24z", "#34A853"],
  ["M5.26 14.26A7.2 7.2 0 014.88 12c0-.79.14-1.55.38-2.26v-3.1H1.26A12 12 0 000 12c0 1.94.46 3.77 1.26 5.36l4-3.1z", "#FBBC05"],
  ["M12 4.77c1.76 0 3.34.61 4.59 1.8l3.43-3.43C17.95 1.19 15.24 0 12 0A12 12 0 001.26 6.64l4 3.1C6.21 6.89 8.87 4.77 12 4.77z", "#EA4335"],
];
const APPLE_MARK = [["M16.37 12.75c-.02-2.2 1.8-3.26 1.88-3.31-1.03-1.5-2.62-1.7-3.19-1.73-1.35-.14-2.65.8-3.34.8-.69 0-1.75-.78-2.88-.76a4.27 4.27 0 00-3.6 2.19c-1.54 2.67-.39 6.62 1.1 8.79.73 1.06 1.6 2.24 2.74 2.2 1.1-.05 1.51-.71 2.84-.71 1.32 0 1.7.71 2.86.69 1.18-.02 1.93-1.08 2.65-2.14a9.4 9.4 0 001.2-2.47 3.83 3.83 0 01-2.26-3.35zM14.2 6.28A3.8 3.8 0 0015.08 3.5a3.87 3.87 0 00-2.5 1.29 3.62 3.62 0 00-.9 2.72 3.2 3.2 0 002.52-1.23z"]];

const OAUTH_ERRORS = {
  session: "That sign-in took too long, or was started in another browser. Please try again.",
  cancelled: "Sign-in was cancelled.",
  unverified: "Your {p} email address isn't verified yet. Verify it with {p}, or sign up with email below.",
  no_email: "We need an email address to make your account. Please allow {p} to share your email.",
  closed: "New sign-ups are closed on this site.",
  taken: "That {p} account is already connected to a different Chess Varsity account.",
  busy: "Too many new accounts from this network. Please try again later.",
};
export function oauthErrorText(code, provider) {
  const p = provider === "apple" ? "Apple" : "Google";
  return (OAUTH_ERRORS[code] || "Something went wrong signing in with {p}. Please try again.").replaceAll("{p}", p);
}

/** "Continue with Google / Apple" buttons for the providers this site has switched on (none: nothing shown). */
export function socialButtons(register) {
  const wrap = h("div", { class: "stack-s hidden" });
  api("/api/auth/providers", { quiet401: true }).then((on) => {
    const verb = register ? "Sign up" : "Continue";
    const buttons = [];
    if (on.google) buttons.push(h("a", { class: "btn block", href: "/api/auth/oauth/google/start",
      style: "background:#fff;color:#1f1f1f;border:1px solid #747775;gap:10px" }, mark(GOOGLE_MARK), `${verb} with Google`));
    if (on.apple) buttons.push(h("a", { class: "btn block", href: "/api/auth/oauth/apple/start",
      style: "background:#000;color:#fff;border:1px solid #000;gap:10px" }, mark(APPLE_MARK, "#fff"), `${verb} with Apple`));
    if (!buttons.length) return;
    wrap.replaceChildren(...buttons, h("div", { class: "row muted small", style: "gap:10px;align-items:center;margin:4px 0" },
      h("span", { style: "flex:1;border-top:1px solid var(--line-2)" }), register ? "or sign up with email" : "or use your email",
      h("span", { style: "flex:1;border-top:1px solid var(--line-2)" })));
    wrap.classList.remove("hidden");
  }).catch(() => {});
  return wrap;
}

const footer = (...kids) => h("p", { class: "muted small", style: "margin:0;text-align:center" }, ...kids);
const heading = (title, text) => h("div", {}, h("h2", {}, title), text ? h("p", { class: "muted" }, text) : null);

/** Sends another confirmation email; used on the "check your email" screen and after a blocked sign-in. */
function resendButton(getEmail, box) {
  const btn = h("button", { class: "btn block", type: "button" }, "Send the link again");
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      const r = await api("/api/auth/resend-verification", { method: "POST", body: { email: getEmail() }, quiet401: true });
      say(box, "good", r.message);
    } catch (err) { say(box, "bad", err.message); }
    setTimeout(() => { btn.disabled = false; }, 20000);  // a pause between resends
  });
  return btn;
}

function checkEmailForm(email) {
  const box = alertBox("good");
  return h("div", { class: "stack" },
    heading("Check your email", null),
    h("p", {}, "We sent a link to ", h("b", {}, email), ". Open it to confirm your address and sign in. It works for 48 hours."),
    h("p", { class: "muted small", style: "margin:0" }, "Nothing there after a few minutes? Look in your spam or promotions folder, or send it again."),
    box, resendButton(() => email, box),
    footer(h("a", { href: "#/login" }, "Back to sign in")));
}

function signInForm(register, query = {}) {
  const error = alertBox();
  if (query.error) say(error, "bad", oauthErrorText(query.error, query.provider));
  const email = h("input", { class: "input", type: "email", autocomplete: "email", required: true, id: "email" });
  const password = h("input", { class: "input", type: "password", required: true, id: "password", minlength: 8, autocomplete: register ? "new-password" : "current-password" });
  const name = h("input", { class: "input", id: "name", autocomplete: "given-name", required: true, maxlength: 60, placeholder: "e.g. Alex" });
  const submit = h("button", { class: "btn primary block", type: "submit" }, register ? "Create my account" : "Sign in");
  const extra = h("div", { class: "stack-s" });

  async function onSubmit(e) {
    e.preventDefault();
    error.classList.add("hidden");
    extra.replaceChildren();
    submit.disabled = true;
    try {
      const body = register ? { email: email.value, password: password.value, display_name: name.value } : { email: email.value, password: password.value };
      const r = await api(`/api/auth/${register ? "register" : "login"}`, { method: "POST", body, quiet401: true });
      if (r.verification_required) { show(checkEmailForm(r.email)); return; }
      location.hash = register ? "#/add" : "#/";
      location.reload();
    } catch (err) {
      say(error, "bad", err.message);
      // 403 on sign-in means the password was right but the email is not confirmed yet.
      if (!register && err.status === 403) {
        const note = alertBox("good");
        extra.append(note, resendButton(() => email.value, note));
      }
      submit.disabled = false;
    }
  }

  return h("form", { class: "stack", onsubmit: onSubmit },
    heading(register ? "Create your account" : "Welcome back", register ? "Just for you: your games and your progress stay private." : "Sign in to see your games and progress."),
    socialButtons(register),
    register ? field("name", "Your name", name, "Use the name you play under. It is how Chess Varsity finds your side in game files.") : null,
    field("email", "Email", email),
    field("password", register ? "Password (at least 8 characters)" : "Password", password),
    register ? null : h("div", { style: "text-align:right;margin-top:-6px" }, h("a", { class: "small", href: "#/forgot" }, "Forgot password?")),
    error, extra, submit,
    footer(register ? "Already have an account? " : "New here? ",
      h("a", { href: register ? "#/login" : "#/register" }, register ? "Sign in" : "Create an account"),
      " · ", h("a", { href: "#/contact" }, "Contact us")));
}

function contactPanel() {
  return h("div", { class: "stack" },
    heading("Contact us", "Questions, problems or ideas? Write to the people who make Chess Varsity. You don't need an account."),
    contactForm(), footer(h("a", { href: "#/login" }, "Back to sign in")));
}

function forgotForm() {
  const box = alertBox();
  const email = h("input", { class: "input", type: "email", autocomplete: "email", required: true, id: "email" });
  const submit = h("button", { class: "btn primary block", type: "submit" }, "Email me a reset link");
  return h("form", { class: "stack", onsubmit: async (e) => {
    e.preventDefault();
    submit.disabled = true;
    try {
      const r = await api("/api/auth/forgot", { method: "POST", body: { email: email.value }, quiet401: true });
      say(box, "good", `${r.message} The link works for 1 hour.`);
    } catch (err) { say(box, "bad", err.message); }
    setTimeout(() => { submit.disabled = false; }, 20000);
  } },
    heading("Forgot your password?", "Enter the email you signed up with and we'll send you a link to choose a new one."),
    field("email", "Email", email), box, submit,
    footer(h("a", { href: "#/login" }, "Back to sign in")));
}

function resetForm(token) {
  const box = alertBox();
  const password = h("input", { class: "input", type: "password", required: true, id: "password", minlength: 8, autocomplete: "new-password" });
  const again = h("input", { class: "input", type: "password", required: true, id: "password2", minlength: 8, autocomplete: "new-password" });
  const submit = h("button", { class: "btn primary block", type: "submit" }, "Save my new password");
  if (!token) return h("div", { class: "stack" }, heading("This link is not complete", "Open the link from your email again, or ask for a new one."), footer(h("a", { href: "#/forgot" }, "Ask for a new link")));
  return h("form", { class: "stack", onsubmit: async (e) => {
    e.preventDefault();
    if (password.value !== again.value) { say(box, "bad", "The two passwords are not the same."); return; }
    submit.disabled = true;
    try {
      await api("/api/auth/reset", { method: "POST", body: { token, password: password.value }, quiet401: true });
      show(h("div", { class: "stack" }, heading("Password changed", "Your new password is saved, and you've been signed out everywhere else."),
        h("a", { class: "btn primary block", href: "#/login" }, "Sign in")));
    } catch (err) { say(box, "bad", err.message); submit.disabled = false; }
  } },
    heading("Choose a new password", "At least 8 characters. You'll use it to sign in from now on."),
    field("password", "New password", password), field("password2", "New password again", again), box, submit,
    footer(h("a", { href: "#/forgot" }, "Need a new link?")));
}

function verifyScreen(token) {
  const box = h("div", { class: "stack" }, heading("Confirming your email…", null));
  (async () => {
    try {
      if (!token) throw new Error("This link is not complete. Open the link from your email again.");
      await api("/api/auth/verify", { method: "POST", body: { token }, quiet401: true });
      box.replaceChildren(heading("Email confirmed", "Welcome to Chess Varsity! Taking you in…"));
      setTimeout(() => { location.hash = "#/add"; location.reload(); }, 900);
    } catch (err) {
      box.replaceChildren(heading("We couldn't confirm your email", err.message),
        h("a", { class: "btn primary block", href: "#/login" }, "Sign in to get a new link"));
    }
  })();
  return box;
}

let panel = null;
function show(node) { if (panel) panel.replaceChildren(node); }

export function authPage(mode, query = {}) {
  const forms = {
    login: () => signInForm(false, query), register: () => signInForm(true, query), forgot: forgotForm,
    reset: () => resetForm(query.token), verify: () => verifyScreen(query.token), contact: contactPanel,
  };
  panel = h("div", { class: "card" }, (forms[mode] || forms.login)());
  return h("div", { class: "auth" }, art(), h("div", { class: "form" }, panel));
}

export function renderAuth(mode, query = {}) {
  document.title = `${TITLES[mode] || TITLES.login} · Chess Varsity`;
  mount(document.getElementById("root"), authPage(mode, query));
}
