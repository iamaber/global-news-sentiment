export class ApiError extends Error {
  constructor(status, body) {
    super(body?.detail ?? `The server answered with status ${status}.`);
    this.status = status;
    this.body = body;
  }
}

export async function getJson(path) {
  let response;
  try {
    response = await fetch(path, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError(0, { detail: "The server could not be reached. Check your connection and try again." });
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, body);
  return body;
}

const cache = new Map();

export function getCached(path) {
  if (!cache.has(path)) {
    const pending = getJson(path);
    cache.set(path, pending);
    pending.catch(() => cache.delete(path));
  }
  return cache.get(path);
}

export const clearCache = () => cache.clear();

export function describeError(error) {
  if (error.status === 429) return "Too many requests from this browser. Wait a minute, then try again.";
  return error.message;
}
