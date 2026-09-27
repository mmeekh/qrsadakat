const $ = (id) => document.getElementById(id);
const views = ["home", "auth", "dashboard", "card"];
let merchant = null;
let authMode = "register";
const initialParams = new URLSearchParams(location.search);
let cardSlug = initialParams.get("card");
let scanToken = initialParams.get("scan");
let qrTimer = null;
let qrTicker = null;
let qrDeadline = 0;
let qrGeneration = 0;
let effectTimer = null;

function show(view) {
  if (view !== "dashboard") {
    qrGeneration++;
    clearTimeout(qrTimer);
    clearInterval(qrTicker);
    qrTimer = null;
    qrTicker = null;
  }
  views.forEach((name) => $(`${name}-view`).classList.toggle("hidden", name !== view));
  $("nav-home").classList.toggle("hidden", view === "home");
  $("nav-dashboard").classList.toggle("hidden", !merchant || view === "dashboard");
  $("nav-logout").classList.toggle("hidden", !merchant);
  window.scrollTo(0, 0);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "Bir hata oluştu.");
  return value;
}

function cardUrl(slug) {
  return `${location.origin}/?card=${encodeURIComponent(slug)}`;
}

async function refreshQr() {
  const generation = ++qrGeneration;
  clearTimeout(qrTimer);
  clearInterval(qrTicker);
  if ($("dashboard-view").classList.contains("hidden") || !merchant) return;
  try {
    const data = await api("/api/merchant/qr");
    if (generation !== qrGeneration || $("dashboard-view").classList.contains("hidden")) return;
    const url = `${cardUrl(merchant.slug)}&scan=${encodeURIComponent(data.scan_token)}`;
    $("qr-code").replaceChildren();
    new QRCode($("qr-code"), { text: url, width: 220, height: 220, colorDark: "#174f3a", colorLight: "#ffffff", correctLevel: QRCode.CorrectLevel.M });
    qrDeadline = performance.now() + data.refresh_in_ms;
    const tick = () => {
      const seconds = Math.max(0, Math.ceil((qrDeadline - performance.now()) / 1000));
      $("qr-countdown").textContent = seconds ? `${seconds} sn sonra yeni QR` : "QR yenileniyor…";
    };
    tick();
    qrTicker = setInterval(tick, 1000);
    qrTimer = setTimeout(refreshQr, Math.max(1000, data.refresh_in_ms + 250));
  } catch (error) {
    if (generation !== qrGeneration || $("dashboard-view").classList.contains("hidden")) return;
    $("qr-countdown").textContent = "QR yüklenemedi; yeniden deneniyor…";
    qrTimer = setTimeout(refreshQr, 5000);
  }
}

function setAuthMode(mode) {
  authMode = mode;
  const register = mode === "register";
  $("register-fields").classList.toggle("hidden", !register);
  $("register-fields").querySelectorAll("input").forEach((field) => { field.disabled = !register; });
  $("auth-title").textContent = register ? "İşletmeni kaydet" : "Tekrar hoş geldin";
  $("auth-subtitle").textContent = register ? "İlk sadakat kartını hemen oluşturalım." : "Kartını ve müşteri ziyaretlerini gör.";
  $("auth-submit").firstChild.textContent = register ? "Kartımı oluştur " : "Giriş yap ";
  $("auth-toggle").textContent = register ? "Zaten hesabın var mı? Giriş yap" : "Hesabın yok mu? İşletmeni kaydet";
  $("auth-error").classList.add("hidden");
  show("auth");
}

async function loadDashboard() {
  const data = await api("/api/dashboard");
  merchant = data.merchant;
  show("dashboard");
  $("dashboard-title").textContent = merchant.business_name;
  ["customers", "returning", "visits", "redeemed"].forEach((key) => {
    $(`metric-${key}`).textContent = data.metrics[key];
  });
  renderRecent(data.recent);
  renderRedemptions(data.redemptions);
  await refreshQr();
}

function renderRecent(visits) {
  const list = $("recent-list");
  list.replaceChildren();
  if (!visits.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "Henüz damga yok. QR kodunu kasada göster.";
    list.append(empty);
    return;
  }
  for (const item of visits) {
    const row = document.createElement("div");
    row.className = "request-row";
    const info = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = `Kart #${item.card_id} · Damga işlendi`;
    const detail = document.createElement("small");
    detail.textContent = new Date(item.approved_at).toLocaleString("tr-TR");
    info.append(label, detail);
    const icon = document.createElement("span");
    icon.className = "recent-stamp";
    icon.textContent = "✳";
    row.append(info, icon);
    list.append(row);
  }
}

function renderRedemptions(requests) {
  const list = $("redemption-list");
  list.replaceChildren();
  if (!requests.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "Henüz kullanılmayı bekleyen ödül yok.";
    list.append(empty);
    return;
  }
  for (const item of requests) {
    const row = document.createElement("div");
    row.className = "request-row";
    const info = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = `Kart #${item.card_id}`;
    const detail = document.createElement("small");
    detail.textContent = `${new Date(item.created_at).toLocaleString("tr-TR")} · Ödül hazır`;
    info.append(label, detail);
    const button = document.createElement("button");
    button.textContent = "Ödülü teslim ettim";
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await api(`/api/redemptions/${item.id}/approve`, { method: "POST", body: {} });
        await loadDashboard();
      } catch (error) { alert(error.message); button.disabled = false; }
    });
    row.append(info, button);
    list.append(row);
  }
}

async function loadCard() {
  if (!cardSlug) return;
  const data = await api(`/api/card/${encodeURIComponent(cardSlug)}`);
  show("card");
  $("customer-card").classList.toggle("cafe-photo", data.merchant.slug === "nora-cafe-demo");
  $("card-business").textContent = data.merchant.business_name;
  $("card-reward").textContent = data.merchant.reward_title;
  $("card-id").textContent = `Kart #${data.card.id}`;
  $("card-progress").textContent = `${data.card.stamps} / ${data.merchant.stamps_required} damga`;
  $("card-available").textContent = `${data.card.rewards_available} ödül hazır`;
  $("card-progress-bar").style.width = `${100 * data.card.stamps / data.merchant.stamps_required}%`;
  const stamps = $("card-stamps");
  stamps.replaceChildren();
  for (let i = 0; i < data.merchant.stamps_required; i++) {
    const stamp = document.createElement("span");
    stamp.className = `stamp ${i < data.card.stamps ? "filled" : i === data.merchant.stamps_required - 1 ? "gift" : ""}`;
    stamp.textContent = i === data.merchant.stamps_required - 1 ? "✦" : "✳";
    stamps.append(stamp);
  }
  $("redeem-button").classList.toggle("hidden", data.card.rewards_available < 1);
  $("redeem-button").disabled = data.redemption_pending;
  $("redeem-button").textContent = data.redemption_pending ? "Ödül onayı bekleniyor" : "Ödülümü kullan";
  $("card-status").textContent = data.redemption_pending ? "Ödül teslimi işletme onayı bekliyor." : "";
}

function showStampEffect(earnedReward) {
  clearTimeout(effectTimer);
  const effect = $("stamp-effect");
  $("stamp-effect-title").textContent = earnedReward ? "Ödülün hazır!" : "Damga eklendi!";
  effect.classList.toggle("reward", earnedReward);
  effect.classList.remove("hidden", "play");
  void effect.offsetWidth;
  effect.classList.add("play");
  if (!earnedReward) {
    const filled = $("card-stamps").querySelectorAll(".stamp.filled");
    if (filled.length) filled[filled.length - 1].classList.add("stamp-new");
  }
  effectTimer = setTimeout(() => effect.classList.add("hidden"), 2300);
}

async function processScan() {
  const token = scanToken;
  scanToken = null;
  history.replaceState({}, "", `/?card=${encodeURIComponent(cardSlug)}`);
  try {
    const result = await api(`/api/card/${encodeURIComponent(cardSlug)}/scan`, {
      method: "POST", body: { scan_token: token },
    });
    await loadCard();
    showStampEffect(result.earned_reward);
    $("card-status").textContent = result.earned_reward ? "Harika! Ödülünü kullanabilirsin." : "Damgan kartına işlendi.";
  } catch (error) {
    await loadCard();
    $("card-status").textContent = error.message;
  }
}

$("start-button").addEventListener("click", () => setAuthMode("register"));
$("demo-button").addEventListener("click", async () => {
  $("demo-button").disabled = true;
  try {
    merchant = (await api("/api/demo/login", { method: "POST", body: {} })).merchant;
    await loadDashboard();
  } catch (error) { alert(error.message); }
  finally { $("demo-button").disabled = false; }
});
$("login-button").addEventListener("click", () => setAuthMode("login"));
$("auth-toggle").addEventListener("click", () => setAuthMode(authMode === "register" ? "login" : "register"));
$("back-home").addEventListener("click", () => show("home"));
function goHome() {
  if (location.search) history.replaceState({}, "", "/");
  cardSlug = null;
  scanToken = null;
  show("home");
}
$("brand-home").addEventListener("click", (event) => {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  goHome();
});
$("nav-home").addEventListener("click", goHome);
$("nav-dashboard").addEventListener("click", () => loadDashboard().catch((error) => alert(error.message)));
$("nav-logout").addEventListener("click", async () => { await api("/api/logout", { method: "POST", body: {} }); merchant = null; show("home"); });
$("refresh-dashboard").addEventListener("click", () => loadDashboard().catch((error) => alert(error.message)));
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && !$("dashboard-view").classList.contains("hidden")) refreshQr();
});
$("auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const data = Object.fromEntries(form.entries());
  $("auth-error").classList.add("hidden");
  $("auth-submit").disabled = true;
  try {
    const result = await api(authMode === "register" ? "/api/register" : "/api/login", { method: "POST", body: data });
    merchant = result.merchant;
    await loadDashboard();
  } catch (error) {
    $("auth-error").textContent = error.message;
    $("auth-error").classList.remove("hidden");
  } finally { $("auth-submit").disabled = false; }
});
$("redeem-button").addEventListener("click", async () => {
  $("redeem-button").disabled = true;
  try { await api(`/api/card/${encodeURIComponent(cardSlug)}/redeem`, { method: "POST", body: {} }); await loadCard(); }
  catch (error) { $("card-status").textContent = error.message; $("redeem-button").disabled = false; }
});
$("refresh-card").addEventListener("click", () => loadCard().catch((error) => { $("card-status").textContent = error.message; }));

(async () => {
  try {
    const config = await api("/api/config");
    $("demo-button").classList.toggle("hidden", !config.demo_enabled);
  } catch { /* The normal account flow still works. */ }
  if (cardSlug) {
    try {
      if (scanToken) await processScan();
      else await loadCard();
    } catch (error) { show("home"); alert(error.message); }
  } else {
    try { merchant = (await api("/api/me")).merchant; await loadDashboard(); }
    catch { show("home"); }
  }
})();
