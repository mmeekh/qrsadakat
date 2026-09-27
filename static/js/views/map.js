// Every business that takes Cheabby stamps, on a map and as a list sorted by distance.
import { api } from "../api.js";
import { baseMap, directionsUrl, distanceKm, loadLeaflet, locate, pinIcon } from "../map-kit.js";
import { defineView, go } from "../nav.js";
import { themeFor } from "../qr-themes.js";
import { $, h, toast } from "../ui.js";

let L = null;
let map = null;
let layer = null;
let places = [];
let here = null;
let hereMarker = null;

defineView("map", {
  async render() {
    let data;
    try { [L, data] = await Promise.all([loadLeaflet(), api("/api/places")]); }
    catch (error) { toast(error.message); return; }
    places = data.places;
    if (!map) {
      map = baseMap(L, $("map-canvas"));
      layer = L.layerGroup().addTo(map);
    }
    layer.clearLayers();
    for (const place of places) {
      L.marker([place.lat, place.lng], { icon: pinIcon(L, place.category), title: place.business_name })
        .bindPopup(() => placeCard(place, true)).addTo(layer);
    }
    if (here) map.setView(here, 14);
    else if (places.length) map.fitBounds(L.latLngBounds(places.map((p) => [p.lat, p.lng])).pad(0.3), { maxZoom: 15 });
    setTimeout(() => map.invalidateSize(), 0);
    renderList();
  },
});

function progress(place) {
  if (!place.mine) return "Henüz kartın yok";
  const reward = place.mine.rewards_available ? ` · ${place.mine.rewards_available} ödül hazır` : "";
  return `${place.mine.stamps} / ${place.stamps_required} damga${reward}`;
}

function placeCard(place, compact = false) {
  const theme = themeFor(place.category);
  const distance = here ? ` · ${distanceKm(here, [place.lat, place.lng]).toFixed(1)} km` : "";
  return h("div", { class: compact ? "place-popup" : "place-card" },
    h("div", { class: "place-head" }, h("span", { class: `place-icon pin-${theme.slug}` }, theme.icon),
      h("div", {}, h("strong", {}, place.business_name), h("small", {}, `${place.category}${distance}`))),
    h("p", { class: "place-reward" }, place.reward_title),
    h("p", { class: "place-progress" }, progress(place)),
    h("div", { class: "place-actions" },
      h("a", { class: "button secondary small", href: directionsUrl(place.lat, place.lng), target: "_blank", rel: "noopener" }, "Yol tarifi"),
      place.mine ? h("button", { class: "button primary small", type: "button",
        onclick: () => go("card", { slug: place.slug }) }, "Kartım") : null));
}

function renderList() {
  const sorted = here ? [...places].sort((a, b) => distanceKm(here, [a.lat, a.lng]) - distanceKm(here, [b.lat, b.lng])) : places;
  $("place-list").replaceChildren(...(sorted.length
    ? sorted.map((place) => placeCard(place))
    : [h("p", { class: "empty-state" }, "Henüz haritada işletme yok.")]));
}

$("locate-button").addEventListener("click", async () => {
  try {
    here = await locate();
    if (hereMarker) hereMarker.setLatLng(here);
    else hereMarker = L.circleMarker(here, { radius: 8, color: "#fff", weight: 3, fillColor: "#2f6fd6", fillOpacity: 1 }).addTo(map);
    map.setView(here, 14);
    renderList();
  } catch (error) { toast(error.message); }
});
