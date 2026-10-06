// Small modal dialogs (asking for a name, or a choice) so we never rely on the browser's plain prompts.
import { h } from "./dom.js";

export function openDialog(build) { return open(build); }

function open(build) {
  return new Promise((resolve) => {
    const dialog = h("dialog", { class: "modal" });
    const done = (value) => { dialog.close(); resolve(value); };
    dialog.append(build(done));
    dialog.addEventListener("close", () => { dialog.remove(); resolve(null); });
    dialog.addEventListener("click", (e) => { if (e.target === dialog) done(null); });
    document.body.append(dialog);
    dialog.showModal();
  });
}

/** Ask for a line of text. Resolves to the text, or null if cancelled. */
export function askText({ title, label, value = "", confirmLabel = "Save", maxlength = 60 }) {
  return open((done) => {
    const input = h("input", { class: "input", value, maxlength, "aria-label": label, autofocus: true });
    const form = h("form", { class: "stack", onsubmit: (e) => { e.preventDefault(); if (input.value.trim()) done(input.value.trim()); } },
      h("h2", { style: "margin:0" }, title), h("div", { class: "field" }, h("label", {}, label), input),
      h("div", { class: "row", style: "justify-content:flex-end" }, h("button", { class: "btn", type: "button", onclick: () => done(null) }, "Cancel"), h("button", { class: "btn primary", type: "submit" }, confirmLabel)));
    setTimeout(() => { input.focus(); input.select(); }, 30);
    return form;
  });
}

/**
 * Ask for several details at once. fields: [{name, label, type?, value?, options?: [[value, text]], placeholder?, maxlength?, required?}].
 * Resolves to {name: value} (numbers for type "number"), or null if cancelled.
 */
export function askForm({ title, fields, confirmLabel = "Save", intro = "" }) {
  return open((done) => {
    const start = (f) => (f.value === undefined || f.value === null ? "" : f.value);
    const inputs = fields.map((f) => f.checks
      ? h("div", { class: "checks", id: `af-${f.name}`, role: "group", "aria-label": f.label }, f.checks.map(([v, t]) => h("label", { class: "check" }, h("input", { type: "checkbox", value: v, checked: (f.value || []).map(String).includes(String(v)) }), t)))
      : f.options
        ? h("select", { class: "select", id: `af-${f.name}`, "aria-label": f.label }, f.options.map(([v, t]) => h("option", { value: v, selected: String(v) === String(start(f)) }, t)))
        : h("input", { class: "input", id: `af-${f.name}`, type: f.type || "text", value: start(f), placeholder: f.placeholder || "", maxlength: f.maxlength || 100, "aria-label": f.label }));
    const read = (f, i) => (f.checks ? [...inputs[i].querySelectorAll("input:checked")].map((x) => +x.value)
      : f.type === "number" ? (inputs[i].value === "" ? null : +inputs[i].value) : inputs[i].value.trim());
    const form = h("form", { class: "stack", onsubmit: (e) => {
      e.preventDefault();
      const out = {};
      fields.forEach((f, i) => { out[f.name] = read(f, i); });
      const missing = fields.findIndex((f) => f.required && out[f.name] === "");
      if (missing >= 0) { inputs[missing].focus(); return; }
      done(out);
    } },
      h("h2", { style: "margin:0" }, title), intro ? h("p", { class: "muted small", style: "margin:0" }, intro) : null,
      fields.map((f, i) => h("div", { class: "field" }, h("label", { for: `af-${f.name}` }, f.label), inputs[i])),
      h("div", { class: "row", style: "justify-content:flex-end" }, h("button", { class: "btn", type: "button", onclick: () => done(null) }, "Cancel"), h("button", { class: "btn primary", type: "submit" }, confirmLabel)));
    setTimeout(() => inputs[0].focus(), 30);
    return form;
  });
}

/** The feedback form. Resolves to {category, message}, or null if cancelled. */
export function askFeedback() {
  return open((done) => {
    const category = h("select", { class: "select", id: "fb-category" },
      [["idea", "An idea or wish"], ["problem", "Something is not working"], ["praise", "Something I like"], ["other", "Something else"]]
        .map(([v, t]) => h("option", { value: v }, t)));
    const message = h("textarea", { class: "textarea", id: "fb-message", rows: 6, style: "font-family:inherit;font-size:.95rem", maxlength: 4000, required: true,
      placeholder: "Tell us what you think. If something went wrong, what were you doing when it happened?" });
    const form = h("form", { class: "stack", onsubmit: (e) => {
      e.preventDefault();
      if (!message.value.trim()) { message.focus(); return; }
      done({ category: category.value, message: message.value.trim() });
    } },
      h("h2", { style: "margin:0" }, "Send feedback"),
      h("p", { class: "muted small", style: "margin:0" }, "It goes straight to the people who make Chess Varsity. We may reply to your email. For anything else, see ", h("a", { href: "#/contact", onclick: () => done(null) }, "Contact us"), "."),
      h("div", { class: "field" }, h("label", { for: "fb-category" }, "What is it about?"), category),
      h("div", { class: "field" }, h("label", { for: "fb-message" }, "Your message"), message),
      h("div", { class: "row", style: "justify-content:flex-end" }, h("button", { class: "btn", type: "button", onclick: () => done(null) }, "Cancel"), h("button", { class: "btn primary", type: "submit" }, "Send")));
    setTimeout(() => message.focus(), 30);
    return form;
  });
}

/** Ask the student to pick one of several actions. options: [{value, label, tone}]. Resolves to a value or null. */
export function askChoice({ title, message, options }) {
  return open((done) => h("div", { class: "stack" },
    h("h2", { style: "margin:0" }, title), h("p", { class: "muted", style: "margin:0" }, message),
    h("div", { class: "stack-s" }, options.map((o) => h("button", { class: `btn ${o.tone || ""}`, style: "justify-content:flex-start", onclick: () => done(o.value) }, o.label))),
    h("div", { class: "row", style: "justify-content:flex-end" }, h("button", { class: "btn small", onclick: () => done(null) }, "Cancel"))));
}
