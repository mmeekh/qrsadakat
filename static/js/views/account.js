import { api, signIn } from "../api.js";
import { defineView, go } from "../nav.js";
import { refreshMe, state } from "../state.js";
import { $, emptyState, googleButton, h, toast } from "../ui.js";

defineView("account", {
  render() {
    const body = $("account-body");
    const { user, merchant } = state.me;
    if (!user) {
      body.replaceChildren(emptyState(
        "Cheabby'ye Google hesabınla girersin; şifre yok. Müşteriysen kartların, işletmeysen panelin hesabına bağlı kalır.",
        googleButton("Google ile giriş yap", () => signIn("account"))));
      return;
    }
    body.replaceChildren(
      h("div", { class: "profile" },
        user.picture ? h("img", { src: user.picture, alt: "", referrerpolicy: "no-referrer" }) : h("span", {}, user.name[0]),
        h("div", {}, h("strong", {}, user.name), h("small", {}, user.email))),
      h("div", { class: "account-actions" },
        merchant
          ? h("button", { class: "button secondary full", type: "button", onclick: () => go("setup") }, `${merchant.business_name} · bilgiler ve konum`)
          : h("button", { class: "button secondary full", type: "button", onclick: () => go("setup") }, "İşletmeni ekle"),
        h("button", { class: "button outline full", type: "button", onclick: logout }, "Çıkış yap")));
  },
});

async function logout() {
  try {
    await api("/api/logout", { method: "POST", body: {} });
    await refreshMe();
    await go("home");
  } catch (error) { toast(error.message); }
}
