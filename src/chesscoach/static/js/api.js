// Thin fetch wrapper: JSON in, JSON out, friendly errors, and a hook for "please sign in".

let onUnauthorized = () => {};
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

export async function api(path, { method = "GET", body, quiet401 = false } = {}) {
  const options = { method, headers: {}, credentials: "same-origin" };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, options);
  } catch (_) {
    throw new ApiError("Could not reach the server. Check your connection and try again.", 0);
  }
  if (res.status === 401 && !quiet401) onUnauthorized();
  let data = null;
  try { data = await res.json(); } catch (_) { /* empty body */ }
  if (!res.ok) {
    const detail = data && data.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail) && detail[0] && detail[0].msg ? detail[0].msg : `Something went wrong (${res.status}).`;
    throw new ApiError(message, res.status);
  }
  return data;
}
