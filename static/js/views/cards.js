import { signIn } from "../api.js";
import { defineView, go } from "../nav.js";
import { refreshMe, state } from "../state.js";
import { $, emptyState, googleButton, h, stampDots } from "../ui.js";
import { themeFor } from "../qr-themes.js";

defineView("cards", {
  async render() {
    const list = $("cards-list");
    if (!state.me.user) {
      list.replaceChildren(emptyState("Kartlarını görmek için giriş yap.",
        googleButton("Google ile giriş yap", () => signIn("cards"))));
      return;
    }
    await refreshMe().catch(() => {});
    if (!state.me.cards.length) {
      list.replaceChildren(emptyState("Henüz kartın yok. Anlaşmalı bir işletmede kasadaki QR'ı okut.",
        h("button", { class: "button secondary", type: "button", onclick: () => go("map") }, "Haritada işletmeleri gör")));
      return;
    }
    list.replaceChildren(...state.me.cards.map((card) => {
      const theme = themeFor(card.category);
      return h("button", { class: "mini-card", type: "button", onclick: () => go("card", { slug: card.slug }) },
        h("div", { class: "place-head" }, h("span", { class: `place-icon pin-${theme.slug}` }, theme.icon),
          h("div", {}, h("strong", {}, card.business_name), h("small", {}, card.reward_title))),
        stampDots(card.stamps, card.stamps_required),
        h("small", { class: "mini-card-foot" }, card.rewards_available
          ? `${card.rewards_available} ödül hazır` : `${card.stamps} / ${card.stamps_required} damga`));
    }));
  },
});
