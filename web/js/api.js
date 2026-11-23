// Thin fetch wrapper over the local CoursePath JSON API (same origin, no network beyond it).

async function call(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.status === 204 ? null : response.json();
}

export const api = {
  catalog: () => call("GET", "/api/catalog"),
  profiles: () => call("GET", "/api/profiles"),
  plan: (params) => call("POST", "/api/plan", params),
  trace: (params) => call("POST", "/api/trace", params),
  check: (body) => call("POST", "/api/builder/check", body),
  suggest: (body) => call("POST", "/api/builder/suggest", body),
  savedPlans: () => call("GET", "/api/plans"),
  savePlan: (params) => call("POST", "/api/plans", params),
  loadPlan: (id) => call("GET", `/api/plans/${id}`),
  deletePlan: (id) => call("DELETE", `/api/plans/${id}`),
};
