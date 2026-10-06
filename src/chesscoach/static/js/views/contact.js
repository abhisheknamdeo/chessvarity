// Contact: the owner's details and a form that emails them. Used signed in (inside the app) and signed out (on the sign-in pages).
import { h, icon } from "../dom.js";
import { api } from "../api.js";
import { state } from "../state.js";

export function contactForm() {
  const me = state.user;
  const box = h("div", { class: "alert hidden", role: "status" });
  const name = h("input", { class: "input", id: "ct-name", maxlength: 80, required: true, autocomplete: "name", value: me ? me.display_name : "" });
  const email = h("input", { class: "input", id: "ct-email", type: "email", maxlength: 254, required: true, autocomplete: "email", value: me ? me.email : "" });
  const message = h("textarea", { class: "textarea", id: "ct-message", rows: 6, maxlength: 4000, required: true, style: "font-family:inherit;font-size:.95rem",
    placeholder: "How can we help? Questions, problems, ideas or anything else." });
  // Hidden from people (and from screen readers); bots that fill every field give themselves away.
  const website = h("input", { name: "website", tabindex: "-1", autocomplete: "off", "aria-hidden": "true", style: "position:absolute;left:-9999px;width:1px;height:1px;opacity:0" });
  const submit = h("button", { class: "btn primary", type: "submit" }, "Send message");
  const address = h("p", { class: "muted small hidden", style: "margin:0" });
  api("/api/contact", { quiet401: true }).then((info) => {
    if (!info.email) return;
    address.replaceChildren("Or email us at ", h("a", { href: `mailto:${info.email}` }, info.email), ".");
    address.classList.remove("hidden");
  }).catch(() => {});

  const form = h("form", { class: "stack", style: "position:relative", onsubmit: async (e) => {
    e.preventDefault();
    submit.disabled = true;
    try {
      const r = await api("/api/contact", { method: "POST", quiet401: true,
        body: { name: name.value, email: email.value, message: message.value, website: website.value } });
      box.className = "alert good"; box.textContent = r.message;
      message.value = "";
    } catch (err) { box.className = "alert bad"; box.textContent = err.message; }
    submit.disabled = false;
  } },
    h("div", { class: "form-grid" },
      h("div", { class: "field" }, h("label", { for: "ct-name" }, "Your name"), name),
      h("div", { class: "field" }, h("label", { for: "ct-email" }, "Your email"), email, h("span", { class: "small muted" }, "We reply to this address."))),
    h("div", { class: "field" }, h("label", { for: "ct-message" }, "Message"), message),
    website, box, h("div", {}, submit), address);
  return form;
}

export async function contactView() {
  document.title = "Contact us · Chess Varsity";
  return h("div", { class: "stack", style: "max-width:720px" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Contact us"), h("p", {}, "Questions, problems or ideas? Write to the people who make Chess Varsity."))),
    h("div", { class: "card stack-s" }, h("h2", { class: "row", style: "gap:8px" }, icon("message"), "Send us a message"), contactForm()));
}
