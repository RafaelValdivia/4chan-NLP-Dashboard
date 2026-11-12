// Role: thin fetch wrapper with per-view AbortController.
// Connects to: state.js, main.js, views/*.
//
// Changing a filter while a request is in flight aborts the old one: the
// slow answer can never overwrite the fresh one.

const inflight = new Map();

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isAbort(error) {
  return error?.name === "AbortError";
}

function toQuery(params = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    if (Array.isArray(value)) {
      if (value.length) search.set(key, value.join(","));
    } else {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function request(key, path, options = {}) {
  inflight.get(key)?.abort();
  const controller = new AbortController();
  inflight.set(key, controller);
  try {
    const response = await fetch(path, {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const payload = await response.json();
        detail = payload.detail || detail;
      } catch {
        // The server may return HTML for an unexpected error.
      }
      throw new ApiError(detail, response.status);
    }
    return await response.json();
  } finally {
    if (inflight.get(key) === controller) inflight.delete(key);
  }
}

export function get(key, path, params = {}) {
  return request(key, `${path}${toQuery(params)}`);
}

export function post(key, path, body) {
  return request(key, path, { method: "POST", body: JSON.stringify(body) });
}
