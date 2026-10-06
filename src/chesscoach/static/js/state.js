// App-wide state: who is signed in (one account is one student) and their games, filed by month.
import { api } from "./api.js";

export const state = { user: null, player: null, sections: [], folders: { folders: [], unfiled: [] } };
const listeners = new Map();

export function on(event, fn) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(fn);
  return () => listeners.get(event).delete(fn);
}
export function emit(event, data) {
  for (const fn of listeners.get(event) || []) fn(data);
}

const store = {
  get(key) { try { return localStorage.getItem(key); } catch (_) { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch (_) { /* private mode */ } },
};
export { store };

export async function loadMe() {
  try {
    const data = await api("/api/auth/me", { quiet401: true });
    state.user = data.user;
    state.player = data.player;
  } catch (_) {
    state.user = null;
    state.player = null;
  }
  return state.user;
}

export const currentPlayer = () => state.player;

export const monthKey = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
export const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

let pollTimer = null;
export async function loadSections() {
  if (!state.player) { state.sections = []; emit("games-changed"); return []; }
  try {
    const [sections, folders] = await Promise.all([
      api(`/api/players/${state.player.id}/library`),
      api(`/api/players/${state.player.id}/folders`),
    ]);
    state.sections = sections;
    state.folders = folders;
  } catch (_) { return state.sections; }
  emit("games-changed");
  const busy = state.sections.some((s) => s.games.some((g) => g.status === "queued" || g.status === "analyzing"));
  clearTimeout(pollTimer);
  if (busy) pollTimer = setTimeout(loadSections, 2500);
  return state.sections;
}

export function clearSession() {
  state.user = null; state.player = null; state.sections = []; state.folders = { folders: [], unfiled: [] };
  clearTimeout(pollTimer);
}
