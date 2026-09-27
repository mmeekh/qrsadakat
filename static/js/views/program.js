// Create or edit one reward card. The stamp goal is set once; the reward can change later.
import { api } from "../api.js";
import { defineView, go } from "../nav.js";
import { $, toast } from "../ui.js";
import { requireMerchant } from "./programs.js";
import { fillReward, rewardFields } from "./reward-picker.js";

const form = $("program-form");
let editing = null;

defineView("program", {
  tab: "programs",
  render({ program } = {}) {
    if (!requireMerchant()) return;
    editing = program || null;
    $("program-title").textContent = editing ? "Kartı düzenle" : "Yeni kart";
    form.stamps_required.value = editing?.stamps_required ?? 5;
    form.stamps_required.disabled = Boolean(editing);
    $("stamps-hint").classList.toggle("hidden", !editing);
    fillReward(editing);
    $("program-submit").firstChild.textContent = editing ? "Kaydet " : "Kartı oluştur ";
    const archive = $("program-archive");
    archive.classList.toggle("hidden", !editing);
    archive.textContent = editing?.archived ? "Arşivden çıkar" : "Kartı arşivle";
  },
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  $("program-submit").disabled = true;
  try {
    const body = { ...rewardFields(), stamps_required: form.stamps_required.value };
    await api(editing ? `/api/programs/${editing.id}` : "/api/programs", { method: "POST", body });
    toast(editing ? "Kart kaydedildi." : "Kart hazır. Dokun, QR açılsın.");
    await go("programs");
  } catch (error) { toast(error.message); }
  finally { $("program-submit").disabled = false; }
});

$("program-archive").addEventListener("click", async () => {
  const archiving = !editing.archived;
  if (archiving && !confirm("Kart arşivlensin mi? Yeni damga vermez; müşterilerin kazandığı ödüller yine kullanılabilir.")) return;
  try {
    await api(`/api/programs/${editing.id}/archive`, { method: "POST", body: { archived: archiving } });
    toast(archiving ? "Kart arşivlendi." : "Kart yeniden aktif.");
    await go("programs");
  } catch (error) { toast(error.message); }
});

$("program-back").addEventListener("click", () => go("programs"));
