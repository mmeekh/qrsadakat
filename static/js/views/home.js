import { api, signIn } from "../api.js";
import { defineView, go } from "../nav.js";
import { refreshMe, state } from "../state.js";
import { $, toast } from "../ui.js";

defineView("home", {
  render() {
    $("demo-button").classList.toggle("hidden", !state.config.demo_enabled);
  },
});

$("demo-button").addEventListener("click", async () => {
  $("demo-button").disabled = true;
  try {
    await api("/api/demo/login", { method: "POST", body: {} });
    await refreshMe();
    await go("programs");
  } catch (error) { toast(error.message); }
  finally { $("demo-button").disabled = false; }
});

$("start-button").addEventListener("click", () => {
  if (state.me.user) return go(state.me.merchant ? "programs" : "setup");
  signIn("merchant").catch((error) => toast(error.message));
});

$("explore-button").addEventListener("click", () => go("map"));
