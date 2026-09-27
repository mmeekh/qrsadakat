import { api } from "./api.js";

// What every view may read: server config and the signed-in account (user, business, cards).
export const state = {
  config: { demo_enabled: false, google_enabled: false, categories: [] },
  me: { user: null, merchant: null, cards: [] },
};

export async function refreshMe() {
  state.me = await api("/api/me");
  return state.me;
}
