// Business profile: name, category and the pin on the map. Rewards are cards (program.js).
import { api, signIn } from "../api.js";
import { addLocateControl, createMap, loadMaps, locate, markerLatLng, moveTo, placeMarker, setMarkerCategory } from "../map-kit.js";
import { defineView, go } from "../nav.js";
import { isSetUp, refreshMe, state } from "../state.js";
import { $, h, toast } from "../ui.js";

const form = $("setup-form");
let ml = null;
let map = null;
let pin = null;

defineView("setup", {
  tab: "account",
  async render() {
    if (!state.me.user) return signIn("merchant").catch((error) => toast(error.message));
    const merchant = state.me.merchant;
    const ready = isSetUp(merchant);
    $("setup-title").textContent = ready ? "İşletme bilgileri" : merchant ? "İşletmeni kur" : "İşletmeni ekle";
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
      // An operator-added business starts empty ('' and null), so both fall back to the defaults.
      form[field].value = merchant?.[field] || (field === "category" ? "Kafe" : "");
    }
    $("geocode-results").replaceChildren();
    $("setup-submit").firstChild.textContent = ready ? "Kaydet " : merchant ? "İşletmemi kur " : "İşletmemi oluştur ";
    try { ml = await loadMaps(); } catch (error) { return toast(error.message); }
    if (!map) {
      map = createMap(ml, $("setup-map"));
      map.on("click", (event) => setPin(event.lngLat.lat, event.lngLat.lng));
      addLocateControl(map, async () => {
        try { const [lat, lng] = await locate(); setPin(lat, lng); moveTo(map, [lat, lng], 17); }
        catch (error) { toast(error.message); }
      });
    }
    if (pin) { pin.remove(); pin = null; }
    if (merchant?.lat != null) { setPin(merchant.lat, merchant.lng); moveTo(map, [merchant.lat, merchant.lng], 16, false); }
    $("pin-status").textContent = merchant?.lat != null ? "Konum seçildi ✓" : "Haritaya dokunarak işletmenin yerini seç.";
    setTimeout(() => map.resize(), 0);
  },
});

function setPin(lat, lng) {
  form.lat.value = lat;
  form.lng.value = lng;
  $("pin-status").textContent = "Konum seçildi ✓ (iğneyi sürükleyerek düzeltebilirsin)";
  if (pin) return pin.setLngLat([lng, lat]);
  pin = placeMarker(ml, map, form.category.value, [lat, lng], { draggable: true });
  pin.on("dragend", () => { [form.lat.value, form.lng.value] = markerLatLng(pin); });
}

form.category.addEventListener("change", () => { if (pin) setMarkerCategory(pin, form.category.value); });

$("geocode-button").addEventListener("click", async () => {
  const results = $("geocode-results");
  try {
    const data = await api(`/api/geocode?q=${encodeURIComponent(form.address.value)}`);
    results.replaceChildren(...(data.results.length ? data.results.map((item) => h("button", {
      type: "button", class: "geocode-item",
      onclick: () => { setPin(item.lat, item.lng); moveTo(map, [item.lat, item.lng], 17); results.replaceChildren(); },
    }, item.label)) : [h("p", { class: "muted" }, "Adres bulunamadı; haritada yerini dokunarak seç.")]));
  } catch (error) { toast(error.message); }
});



form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.lat.value) return toast("Haritada işletmenin yerini seç.");
  $("setup-submit").disabled = true;
  try {
    const isNew = !isSetUp(state.me.merchant);
    await api("/api/merchant", { method: "POST", body: Object.fromEntries(new FormData(form).entries()) });
    await refreshMe();
    toast(isNew ? "İşletmen hazır. Şimdi ilk kartını oluştur." : "Kaydedildi.");
    await go(isNew ? "program" : "programs");
  } catch (error) { toast(error.message); }
  finally { $("setup-submit").disabled = false; }
});
