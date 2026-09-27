// The customer's stamp card for one business. Reached by scanning the counter QR
// (/?c=<slug>&s=<token>); a signed-out customer signs in with Google first.
import { api, signIn, startLogin } from "../api.js";
import { defineView } from "../nav.js";
import { refreshMe, state } from "../state.js";
import { $, googleButton, stampDots } from "../ui.js";

const STAMP_MESSAGES = {
  ok: "Damgan kartına işlendi.",
  reward: "Harika! Ödülünü kullanabilirsin.",
  wait: "Bu kartın damgası zaten işlendi. Yeni damga için bir saat bekle.",
};
let slug = null;
let effectTimer = null;

defineView("card", {
  tab: "cards",
  async render({ slug: next, scan, stamp, login }) {
    slug = next;
    history.replaceState({}, "", `/?c=${encodeURIComponent(slug)}`);
    status("");
    if (scan && state.me.user) return scanNow(scan);
    await load();
    if (!state.me.user) await showGate(scan);
    if (stamp) {
      showEffect(stamp);
      status(STAMP_MESSAGES[stamp] || "");
      refreshMe().catch(() => {});
    }
    if (login === "failed") status("Google girişi tamamlanamadı. Tekrar dene.");
  },
});

const status = (text) => { $("card-status").textContent = text; };

async function load() {
  const data = await api(`/api/card/${encodeURIComponent(slug)}`);
  const { merchant, card } = data;
  $("customer-card").classList.toggle("cafe-photo", merchant.category === "Kafe");
  $("card-business").textContent = merchant.business_name;
  $("card-reward").textContent = merchant.reward_title;
  const stamps = card ? card.stamps : 0;
  $("card-stamps").replaceWith(Object.assign(stampDots(stamps, merchant.stamps_required), { id: "card-stamps" }));
  $("card-progress").textContent = `${stamps} / ${merchant.stamps_required} damga`;
  $("card-available").textContent = card ? `${card.rewards_available} ödül hazır` : "";
  $("card-progress-bar").style.width = `${100 * stamps / merchant.stamps_required}%`;
  $("card-id").textContent = card ? `Kart #${card.id}` : "";
  $("card-gate").classList.toggle("hidden", Boolean(card));
  $("refresh-card").classList.toggle("hidden", !card);
  const redeem = $("redeem-button");
  redeem.classList.toggle("hidden", !card || card.rewards_available < 1);
  redeem.disabled = data.redemption_pending;
  redeem.textContent = data.redemption_pending ? "Ödül onayı bekleniyor" : "Ödülümü kullan";
  if (data.redemption_pending) status("Ödül teslimi işletme onayı bekliyor.");
}

async function showGate(scan) {
  $("gate-text").textContent = scan
    ? "Damganı almak için Google ile devam et. Kartın hesabına kaydedilir, telefon değişse de kaybolmaz."
    : "Kartını görmek için Google ile giriş yap.";
  let url = null;
  $("gate-action").replaceChildren(googleButton(scan ? "Google ile devam et" : "Google ile giriş yap",
    () => (url ? (location.href = url) : signIn("card", { slug }))));
  if (!scan) return;
  try {
    // Started right away: the QR is checked while fresh, the stamp lands after sign-in.
    const started = await startLogin("card", { slug, scan_token: scan });
    url = started.url;
    if (!started.scan_ok) status("QR'ın süresi dolmuş. Giriş yaptıktan sonra kasadaki güncel QR'ı yeniden okut.");
  } catch (error) { status(error.message); }
}

async function scanNow(token) {
  try {
    const result = await api(`/api/card/${encodeURIComponent(slug)}/scan`, { method: "POST", body: { scan_token: token } });
    await load();
    const kind = result.earned_reward ? "reward" : "ok";
    showEffect(kind);
    status(STAMP_MESSAGES[kind]);
    refreshMe().catch(() => {});
  } catch (error) {
    await load();
    status(error.message);
  }
}

function showEffect(kind) {
  if (kind === "wait") return;
  clearTimeout(effectTimer);
  const effect = $("stamp-effect");
  $("stamp-effect-title").textContent = kind === "reward" ? "Ödülün hazır!" : "Damga eklendi!";
  effect.classList.toggle("reward", kind === "reward");
  effect.classList.remove("hidden", "play");
  void effect.offsetWidth;
  effect.classList.add("play");
  const filled = $("card-stamps").querySelectorAll(".stamp.filled");
  if (kind === "ok" && filled.length) filled[filled.length - 1].classList.add("stamp-new");
  effectTimer = setTimeout(() => effect.classList.add("hidden"), 2300);
}

$("redeem-button").addEventListener("click", async () => {
  $("redeem-button").disabled = true;
  try { await api(`/api/card/${encodeURIComponent(slug)}/redeem`, { method: "POST", body: {} }); await load(); }
  catch (error) { status(error.message); $("redeem-button").disabled = false; }
});

$("refresh-card").addEventListener("click", () => load().catch((error) => status(error.message)));
