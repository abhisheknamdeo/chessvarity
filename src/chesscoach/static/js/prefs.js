// Board appearance the student can change: colours, size, coordinates. Saved in this browser.
import { h } from "./dom.js";
import { store } from "./state.js";
import { drawBoard } from "./board.js";

export const BOARD_THEMES = [
  ["green", "Green", "#ecebd3", "#769656"],
  ["brown", "Wood", "#f0d9b5", "#b58863"],
  ["blue", "Ocean", "#dee3e6", "#6f8fb0"],
  ["slate", "Slate", "#e8e6e0", "#7b8794"],
  ["purple", "Royal", "#efe9f7", "#8e6fc0"],
  ["walnut", "Walnut", "#f3e4c8", "#8b5a2b"],
  ["coral", "Coral", "#f6e7df", "#d07a63"],
  ["mint", "Mint", "#eef6ee", "#6fae8f"],
  ["ice", "Ice", "#eef4f8", "#8fb3cf"],
  ["sand", "Sand", "#f5ecd9", "#c8a46b"],
  ["cherry", "Cherry", "#f6e4e4", "#b35b66"],
  ["rose", "Rose", "#fbeef2", "#d487a2"],
  ["tournament", "Tournament", "#f4f1e6", "#4f8a5b"],
  ["midnight", "Midnight", "#c9d3e6", "#33415c"],
  ["contrast", "High contrast", "#ffffff", "#4d4d4d"],
];

export function loadPrefs() {
  let saved = {};
  try { saved = JSON.parse(store.get("cc-board") || "{}"); } catch (_) { /* ignore */ }
  return { theme: "green", size: "m", coords: "on", ...saved };
}

export function applyPrefs(prefs = loadPrefs()) {
  const root = document.documentElement;
  root.dataset.board = prefs.theme; root.dataset.size = prefs.size; root.dataset.coords = prefs.coords;
}

function save(patch) {
  const prefs = { ...loadPrefs(), ...patch };
  store.set("cc-board", JSON.stringify(prefs));
  applyPrefs(prefs);
  return prefs;
}

/** The "Board options" dialog, with a live preview. */
export function openBoardOptions() {
  const dialog = h("dialog", { class: "modal", "aria-label": "Board options" });
  const preview = h("div", { class: "board", style: "max-width:200px" });
  const drawPreview = () => drawBoard(preview, "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4", { arrows: [{ from: "f3", to: "g5", kind: "best" }], lastMove: "f3g5" });
  const body = h("div", { class: "stack" });

  function render() {
    const prefs = loadPrefs();
    body.replaceChildren(
      h("div", { class: "row spread" }, h("h2", { style: "margin:0" }, "Board options"), h("button", { class: "btn small", onclick: () => dialog.close() }, "Done")),
      h("div", { class: "row", style: "align-items:flex-start" }, preview,
        h("div", { class: "stack-s", style: "flex:1;min-width:180px" },
          h("b", { class: "small" }, "Colours", h("span", { class: "muted", style: "font-weight:500" }, ` · ${(BOARD_THEMES.find(([k]) => k === prefs.theme) || BOARD_THEMES[0])[1]}`)),
          h("div", { class: "swatches" }, BOARD_THEMES.map(([key, label, light, dark]) => {
            const b = h("button", { class: "swatch", title: label, "aria-label": label, "aria-pressed": prefs.theme === key ? "true" : "false", onclick: () => { save({ theme: key }); render(); } },
              h("i", { style: `background:${light}` }), h("i", { style: `background:${dark}` }), h("i", { style: `background:${dark}` }), h("i", { style: `background:${light}` }));
            return b;
          })))),
      h("div", { class: "stack-s" }, h("b", { class: "small" }, "Board size"),
        h("div", { class: "tabs" }, [["s", "Small"], ["m", "Medium"], ["l", "Large"]].map(([k, t]) =>
          h("button", { "aria-selected": prefs.size === k ? "true" : "false", onclick: () => { save({ size: k }); render(); } }, t)))),
      h("div", { class: "stack-s" }, h("b", { class: "small" }, "Coordinates (a-h, 1-8)"),
        h("div", { class: "tabs" }, [["on", "Show"], ["off", "Hide"]].map(([k, t]) =>
          h("button", { "aria-selected": prefs.coords === k ? "true" : "false", onclick: () => { save({ coords: k }); render(); } }, t)))));
    drawPreview();
  }
  dialog.append(body);
  dialog.addEventListener("close", () => dialog.remove());
  dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
  document.body.append(dialog);
  render();
  dialog.showModal();
}
