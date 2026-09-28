// The business's reward cards. Tapping an active card opens its counter QR full screen.
import { api, signIn } from "../api.js";
import { defineView, go } from "../nav.js";
import { themeFor } from "../qr-themes.js";
import { isSetUp, state } from "../state.js";
import { $, emptyState, h, toast } from "../ui.js";

export function requireMerchant() {
  if (!state.me.user) { signIn("merchant").catch((error) => toast(error.message)); return null; }
  if (!isSetUp(state.me.merchant)) { go("setup"); return null; }
  return state.me.merchant;
}

defineView("programs", {
  async render() {
    if (!requireMerchant()) return;
    const { programs, max_active: max } = await api("/api/programs");
    const active = programs.filter((p) => !p.archived);
    const archived = programs.filter((p) => p.archived);
    $("programs-hint").textContent = active.length
      ? `Damga vermek için karta dokun, QR açılsın. Aktif kart: ${active.length} / ${max}.`
      : "Henüz kartın yok. İlk kartını oluştur, müşterilerin damga toplamaya başlasın.";
    $("new-program").disabled = active.length >= max;
    $("program-list").replaceChildren(...(active.length ? active.map(programCard)
      : [emptyState("Kart, müşterine neyi kaç damgada vereceğini söyler: ör. 5 damga topla, 1 kahve bedava.")]));
    $("archived-list").replaceChildren(...(archived.length
      ? [h("h2", { class: "list-title" }, "Arşiv"), ...archived.map(programCard)] : []));
  },
});

function programCard(program) {
  const theme = themeFor(state.me.merchant.category);
  const stats = `${program.customers} müşteri${program.rewards_waiting ? ` · ${program.rewards_waiting} ödül bekliyor` : ""}`;
  return h("div", { class: `program-card pass pass-${theme.slug}${program.archived ? " archived" : ""}` },
    h("button", { class: "program-open", type: "button", disabled: program.archived,
      onclick: () => go("qr", { program }) },
      h("span", { class: `place-icon pin-${theme.slug}` }, theme.icon),
      h("span", { class: "program-text" }, h("strong", {}, program.title),
        h("small", {}, program.archived ? "Arşivde · yeni damga vermez" : stats)),
      program.archived ? null : h("span", { class: "program-qr" }, "QR")),
    h("button", { class: "text-button", type: "button", onclick: () => go("program", { program }) },
      program.archived ? "Geri al / düzenle" : "Düzenle"));
}

$("new-program").addEventListener("click", () => go("program"));
