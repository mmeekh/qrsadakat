// Business profile: name, category and the pin on the map. Rewards are cards (program.js).
import { api, signIn } from "../api.js";
import { baseMap, loadLeaflet, locate, locateControl, pinIcon } from "../map-kit.js";
import { defineView, go } from "../nav.js";
import { refreshMe, state } from "../state.js";
import { $, h, toast } from "../ui.js";

const form = $("setup-form");
let L = null;
let map = null;
let pin = null;

defineView("setup", {
  tab: "account",
  async render() {
    if (!state.me.user) return signIn("merchant").catch((error) => toast(error.message));
    const merchant = state.me.merchant;
    $("setup-title").textContent = merchant ? "İşletme bilgileri" : "İşletmeni ekle";
    // Businesses open by invitation; an uninvited account learns which e-mail to pass on.
    const blocked = !merchant && !state.me.can_open_business;
    form.classList.toggle("hidden", blocked);
    $("setup-blocked").classList.toggle("hidden", !blocked);
    if (blocked) {
      $("setup-blocked").replaceChildren(
        h("h2", {}, "İşletmeleri bikıyak ekibi ekliyor"),
        h("p", { class: "empty-state" }, `Bu Google hesabı (${state.me.user.email}) bir işletmeye bağlı değil. `,
          "İşletmeni eklemek için bu e-postayla iletisim@bikıyak.com adresine yaz; eklenince bu hesapla girdiğinde işletme panelin açılır."),
        h("button", { class: "button secondary", type: "button", onclick: () => go("map") }, "Haritaya dön"));
      return;
    }
    form.category.replaceChildren(...state.config.categories.map((name) => h("option", { value: name }, name)));
    for (const field of ["business_name", "category", "address", "lat", "lng"]) {
      form[field].value = merchant?.[field] ?? (field === "category" ? "Kafe" : "");
    }
    $("geocode-results").replaceChildren();
    $("setup-submit").firstChild.textContent = merchant ? "Kaydet " : "İşletmemi oluştur ";
    try { L = await loadLeaflet(); } catch (error) { return toast(error.message); }
    if (!map) {
      map = baseMap(L, $("setup-map"));
      map.on("click", (event) => setPin(event.latlng.lat, event.latlng.lng));
      locateControl(L, map, async () => {
        try { const [lat, lng] = await locate(); setPin(lat, lng); map.setView([lat, lng], 17); }
        catch (error) { toast(error.message); }
      });
    }
    if (pin) { pin.remove(); pin = null; }
    if (merchant?.lat != null) { setPin(merchant.lat, merchant.lng); map.setView([merchant.lat, merchant.lng], 16); }
    $("pin-status").textContent = merchant?.lat != null ? "Konum seçildi ✓" : "Haritaya dokunarak işletmenin yerini seç.";
    setTimeout(() => map.invalidateSize(), 0);
  },
});

function setPin(lat, lng) {
  form.lat.value = lat;
  form.lng.value = lng;
  $("pin-status").textContent = "Konum seçildi ✓ (iğneyi sürükleyerek düzeltebilirsin)";
  if (pin) return pin.setLatLng([lat, lng]);
  pin = L.marker([lat, lng], { icon: pinIcon(L, form.category.value), draggable: true }).addTo(map);
  pin.on("dragend", () => { const p = pin.getLatLng(); form.lat.value = p.lat; form.lng.value = p.lng; });
}

form.category.addEventListener("change", () => { if (pin) pin.setIcon(pinIcon(L, form.category.value)); });

$("geocode-button").addEventListener("click", async () => {
  const results = $("geocode-results");
  try {
    const data = await api(`/api/geocode?q=${encodeURIComponent(form.address.value)}`);
    results.replaceChildren(...(data.results.length ? data.results.map((item) => h("button", {
      type: "button", class: "geocode-item",
      onclick: () => { setPin(item.lat, item.lng); map.setView([item.lat, item.lng], 17); results.replaceChildren(); },
    }, item.label)) : [h("p", { class: "muted" }, "Adres bulunamadı; haritada yerini dokunarak seç.")]));
  } catch (error) { toast(error.message); }
});



form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.lat.value) return toast("Haritada işletmenin yerini seç.");
  $("setup-submit").disabled = true;
  try {
    const isNew = !state.me.merchant;
    await api("/api/merchant", { method: "POST", body: Object.fromEntries(new FormData(form).entries()) });
    await refreshMe();
    toast(isNew ? "İşletmen hazır. Şimdi ilk kartını oluştur." : "Kaydedildi.");
    await go(isNew ? "program" : "programs");
  } catch (error) { toast(error.message); }
  finally { $("setup-submit").disabled = false; }
});
