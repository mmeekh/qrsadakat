// Boot: load config and the account, then open the view the URL asks for.
import { api } from "./api.js";
import { go, hasView, renderTabs } from "./nav.js";
import { refreshMe, state } from "./state.js";
import { $, toast } from "./ui.js";
import "./views/home.js";
import "./views/card.js";
import "./views/map.js";
import "./views/cards.js";
import "./views/account.js";
import "./views/setup.js";
import "./views/merchant.js";

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
  const slug = params.get("c") || params.get("card");
  const login = params.get("login");
  if (login === "cancelled") toast("Google girişi iptal edildi.");
  if (login === "failed" && !slug) toast("Google girişi tamamlanamadı. Tekrar dene.");
  if (slug) {
    return go("card", { slug, scan: params.get("s") || params.get("scan"), stamp: params.get("stamp"), login })
      .catch((error) => { toast(error.message); go("home"); });
  }
  const wanted = params.get("view");
  const fallback = state.me.merchant ? "qr" : state.me.user ? "cards" : "home";
  const target = wanted === "merchant" ? (state.me.merchant ? "qr" : "setup") : hasView(wanted) ? wanted : fallback;
  go(target).catch((error) => toast(error.message));
})();
