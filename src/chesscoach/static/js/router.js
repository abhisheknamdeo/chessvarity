// A minimal hash router: "#/game/12/5?tab=moves" -> handler({id:"12", ply:"5"}, {tab:"moves"}).
const routes = [];
let notFound = () => {};
let onChange = () => {};

export function route(pattern, handler) {
  const parts = pattern.split("/").filter(Boolean).map((p) => {
    const optional = p.endsWith("?");
    const name = optional ? p.slice(1, -1) : p.slice(1);
    return p.startsWith(":") ? { name, optional } : { literal: p };
  });
  routes.push({ pattern, parts, handler });
}

export const setNotFound = (fn) => { notFound = fn; };
export const setOnChange = (fn) => { onChange = fn; };

export function parse(hash = location.hash) {
  const raw = hash.replace(/^#/, "") || "/";
  const [path, queryString = ""] = raw.split("?");
  const query = Object.fromEntries(new URLSearchParams(queryString));
  return { path, segments: path.split("/").filter(Boolean).map(decodeURIComponent), query };
}

export function match() {
  const { path, segments, query } = parse();
  for (const r of routes) {
    const params = {};
    let ok = true;
    r.parts.forEach((part, i) => {
      const seg = segments[i];
      if (part.literal !== undefined) { if (seg !== part.literal) ok = false; }
      else if (seg === undefined) { if (!part.optional) ok = false; }
      else params[part.name] = seg;
    });
    if (segments.length > r.parts.length) ok = false;
    if (ok) return { handler: r.handler, params, query, path };
  }
  return { handler: notFound, params: {}, query, path };
}

export function go(path, { replace = false } = {}) {
  const target = `#${path}`;
  if (replace) history.replaceState(null, "", target);
  else if (location.hash !== target) location.hash = target;
  else run();
}

export function run() {
  const found = match();
  onChange(found);
  return found.handler(found.params, found.query);
}

export const start = () => {
  window.addEventListener("hashchange", run);
  return run();
};
