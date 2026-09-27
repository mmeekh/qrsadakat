export async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let value = {};
  try { value = await response.json(); } catch { /* empty or non-JSON body */ }
  if (!response.ok) {
    const error = new Error(value.error || "Bir hata oluştu.");
    error.status = response.status;
    throw error;
  }
  return value;
}

// Starts a Google sign-in; `intent` says where to land afterwards (see bikiyak/auth.py).
export function startLogin(intent, extra = {}) {
  return api("/api/auth/start", { method: "POST", body: { intent, ...extra } });
}

export async function signIn(intent, extra) {
  location.href = (await startLogin(intent, extra)).url;
}
