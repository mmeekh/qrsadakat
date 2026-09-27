// The business side: the counter QR (refreshed every minute) and the dashboard.
import { api, signIn } from "../api.js";
import { defineView, go } from "../nav.js";
import { renderThemedQr } from "../qr-themes.js";
import { state } from "../state.js";
import { $, h, toast } from "../ui.js";

let qrTimer = null;
let qrTicker = null;
let generation = 0;
let wakeLock = null;

function requireMerchant() {
  if (!state.me.user) { signIn("merchant").catch((error) => toast(error.message)); return null; }
  if (!state.me.merchant) { go("setup"); return null; }
  return state.me.merchant;
}

defineView("qr", {
  async render() {
    const merchant = requireMerchant();
    if (!merchant) return;
    $("qr-business").textContent = merchant.business_name;
    await refreshQr();
    // Keeps the counter screen awake while the QR is shown, where the browser allows it.
    try { wakeLock = await navigator.wakeLock?.request("screen"); } catch { wakeLock = null; }
  },
  leave() {
    generation++;
    clearTimeout(qrTimer);
    clearInterval(qrTicker);
    wakeLock?.release().catch(() => {});
    wakeLock = null;
  },
});

async function refreshQr() {
  const mine = ++generation;
  clearTimeout(qrTimer);
  clearInterval(qrTicker);
  const merchant = state.me.merchant;
  try {
    const data = await api("/api/merchant/qr");
    if (mine !== generation) return;
    const url = `${location.origin}/?c=${encodeURIComponent(merchant.slug)}&s=${encodeURIComponent(data.scan_token)}`;
    renderThemedQr($("qr-stage"), url, merchant.category, merchant.business_name);
    const deadline = performance.now() + data.refresh_in_ms;
    const tick = () => {
      const seconds = Math.max(0, Math.ceil((deadline - performance.now()) / 1000));
      $("qr-countdown").textContent = seconds ? `${seconds} sn sonra yeni QR` : "QR yenileniyor…";
    };
    tick();
    qrTicker = setInterval(tick, 1000);
    qrTimer = setTimeout(refreshQr, Math.max(1000, data.refresh_in_ms + 250));
  } catch {
    if (mine !== generation) return;
    $("qr-countdown").textContent = "QR yüklenemedi; yeniden deneniyor…";
    qrTimer = setTimeout(refreshQr, 5000);
  }
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && !$("qr-view").classList.contains("hidden")) refreshQr();
});

defineView("dashboard", { render: loadDashboard });

async function loadDashboard() {
  if (!requireMerchant()) return;
  const data = await api("/api/dashboard");
  $("dashboard-title").textContent = data.merchant.business_name;
  for (const key of ["customers", "returning", "visits", "redeemed"]) $(`metric-${key}`).textContent = data.metrics[key];
  $("location-banner").classList.toggle("hidden", data.merchant.lat != null);
  fillList($("recent-list"), data.recent, "Henüz damga yok. QR kodunu kasada göster.", (item) => [
    h("div", {}, h("strong", {}, `${item.customer} · Damga işlendi`),
      h("small", {}, `${new Date(item.approved_at).toLocaleString("tr-TR")} · ${item.visits}. ziyaret`)),
    h("span", { class: "recent-stamp" }, "✳")]);
  fillList($("redemption-list"), data.redemptions, "Henüz kullanılmayı bekleyen ödül yok.", (item) => [
    h("div", {}, h("strong", {}, item.customer), h("small", {}, `${new Date(item.created_at).toLocaleString("tr-TR")} · Ödül hazır`)),
    h("button", { type: "button", onclick: (event) => approve(event.currentTarget, item.id) }, "Ödülü teslim ettim")]);
}

function fillList(list, items, emptyText, row) {
  list.replaceChildren(...(items.length
    ? items.map((item) => h("div", { class: "request-row" }, ...row(item)))
    : [h("p", { class: "empty-state" }, emptyText)]));
}

async function approve(button, id) {
  button.disabled = true;
  try { await api(`/api/redemptions/${id}/approve`, { method: "POST", body: {} }); await loadDashboard(); }
  catch (error) { toast(error.message); button.disabled = false; }
}

$("refresh-dashboard").addEventListener("click", () => loadDashboard().catch((error) => toast(error.message)));
$("location-banner").addEventListener("click", () => go("setup"));
