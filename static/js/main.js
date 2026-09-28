// Boot: load config and the account, then open the view the URL asks for.
import { api } from "./api.js";
import { go, hasView, renderTabs } from "./nav.js";
import { isSetUp, refreshMe, state } from "./state.js";
import { $, toast } from "./ui.js";
import "./views/home.js";
import "./views/card.js";
import "./views/map.js";
import "./views/cards.js";
import "./views/account.js";
import "./views/setup.js";
import "./views/merchant.js";
import "./views/programs.js";
import "./views/program.js";

$("brand-home").addEventListener("click", (event) => {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  go("home");
});
$("top-account").addEventListener("click", () => go("account"));

(async () => {
  const params = new URLSearchParams(location.search);
  try { state.config = await api("/api/config"); } catch { /* defaults keep the page usable */ }
  try { await refreshMe(); } catch { /* treated as signed out */ }
  renderTabs();
  const cardId = params.get("k");
  const login = params.get("login");
  if (login === "cancelled") toast("Google girişi iptal edildi.");
  if (login === "failed" && !cardId) toast("Google girişi tamamlanamadı. Tekrar dene.");
  if (cardId) {
    return go("card", { id: cardId, scan: params.get("s"), stamp: params.get("stamp"), login })
      .catch((error) => { toast(error.message); go("home"); });
  }
  const wanted = params.get("view");
  const business = state.me.merchant ? (isSetUp(state.me.merchant) ? "programs" : "setup") : null;
  const fallback = business || (state.me.user ? "cards" : "home");
  // Signing in from the home page comes back as ?view=cards; a business owner lands on the
  // business side instead, and on setup while the operator-added business is still empty.
  const target = wanted === "merchant" ? business || "setup"
    : business && (wanted === "cards" || business === "setup") ? business
    : hasView(wanted) ? wanted : fallback;
  go(target).catch((error) => toast(error.message));
})();
