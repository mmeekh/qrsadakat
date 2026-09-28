import { api } from "./api.js";

// What every view may read: server config and the signed-in account (user, business, cards).
export const state = {
  config: { demo_enabled: false, google_enabled: false, categories: [] },
  me: { user: null, merchant: null, cards: [] },
};

// A business the operator added by e-mail alone has no name or pin yet: its owner sets it up first.
export const isSetUp = (merchant) => Boolean(merchant?.business_name && merchant.lat != null);

export async function refreshMe() {
  state.me = await api("/api/me");
  return state.me;
}
