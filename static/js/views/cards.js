import { signIn } from "../api.js";
import { defineView, go } from "../nav.js";
import { refreshMe, state } from "../state.js";
import { $, emptyState, googleButton, h, stampDots } from "../ui.js";
import { themeFor } from "../qr-themes.js";

defineView("cards", {
  async render() {
    await refreshMe().catch(() => {});
    const { user, cards } = state.me;
    const list = $("cards-list");
    if (!cards.length) {
      list.replaceChildren(emptyState(user
        ? "Henüz kartın yok. Anlaşmalı bir işletmede kasadaki QR'ı okut."
        : "Kasadaki QR'ı okutunca kartın burada görünür; ilk damga için giriş gerekmez.",
      h("button", { class: "button secondary", type: "button", onclick: () => go("map") }, "Haritada işletmeleri gör"),
      user ? null : googleButton("Hesabım var, Google ile giriş yap", () => signIn("cards"))));
      return;
    }
    const save = user ? null : h("div", { class: "save-banner" },
      h("p", {}, "Kartın yalnız bu telefonda. Kaybolmasın ve ödülünü kullanabilesin diye Google ile kaydet."),
      googleButton("Google ile kaydet", () => signIn("cards")));
    list.replaceChildren(...[save, ...cards.map(miniCard)].filter(Boolean));
  },
});

function miniCard(card) {
  const theme = themeFor(card.category);
  return h("button", { class: "mini-card", type: "button", onclick: () => go("card", { slug: card.slug }) },
    h("div", { class: "place-head" }, h("span", { class: `place-icon pin-${theme.slug}` }, theme.icon),
      h("div", {}, h("strong", {}, card.business_name), h("small", {}, card.reward_title))),
    stampDots(card.stamps, card.stamps_required),
    h("small", { class: "mini-card-foot" }, card.rewards_available
      ? `${card.rewards_available} ödül hazır` : `${card.stamps} / ${card.stamps_required} damga`));
}
