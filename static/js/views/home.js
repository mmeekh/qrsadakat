// Home: what bikıyak is, and one way in (Google). Businesses are added by the operator,
// so there is no "open a business" entry here.
import { signIn } from "../api.js";
import { defineView, go } from "../nav.js";
import { state } from "../state.js";
import { $, googleButton, h } from "../ui.js";

defineView("home", {
  render() {
    const { user, merchant } = state.me;
    $("home-actions").replaceChildren(user
      ? h("button", { class: "button primary", type: "button", onclick: () => go(merchant ? "programs" : "cards") },
        "Kartlarıma git ", h("span", {}, "→"))
      : googleButton("Google ile giriş yap", () => signIn("cards")));
  },
});
