// Every business that takes bikıyak stamps, on a map and as a list sorted by distance.
import { api } from "../api.js";
import { addLocateControl, createMap, DEFAULT_VIEW, directionsUrl, distanceKm, loadMaps, locate, moveTo, placeMarker,
  showHere } from "../map-kit.js";
import { defineView, go } from "../nav.js";
import { themeFor } from "../qr-themes.js";
import { $, h, toast } from "../ui.js";

let ml = null;
let map = null;
let markers = [];
let places = [];
let here = null;
let hereMarker = null;
let askedForLocation = false;

defineView("map", {
  async render() {
    let data;
    try { [ml, data] = await Promise.all([loadMaps(), api("/api/places")]); }
    catch (error) { toast(error.message); return; }
    places = data.places;
    if (!map) {
      map = createMap(ml, $("map-canvas"));
      addLocateControl(map, () => findMe(true));
    }
    markers.forEach((marker) => marker.remove());
    markers = places.map((place) => placeMarker(ml, map, place.category, [place.lat, place.lng],
      { popup: () => placeCard(place, true) }));
    moveTo(map, here || DEFAULT_VIEW.center, here ? 15 : DEFAULT_VIEW.zoom, false);
    setTimeout(() => map.resize(), 0);
    renderList();
    // First visit: ask once for the location so the map opens around the visitor.
    if (!here && !askedForLocation) {
      askedForLocation = true;
      findMe(false);
    }
  },
});

function progress(program) {
  if (!program.mine) return "Henüz kartın yok";
  const reward = program.mine.rewards_available ? ` · ${program.mine.rewards_available} ödül hazır` : "";
  return `${program.mine.stamps} / ${program.stamps_required} damga${reward}`;
}

function placeCard(place, compact = false) {
  const theme = themeFor(place.category);
  const distance = here ? ` · ${distanceKm(here, [place.lat, place.lng]).toFixed(1)} km` : "";
  return h("div", { class: compact ? "place-popup" : "place-card" },
    h("div", { class: "place-head" }, h("span", { class: `place-icon pin-${theme.slug}` }, theme.icon),
      h("div", {}, h("strong", {}, place.business_name), h("small", {}, `${place.category}${distance}`))),
    h("ul", { class: "place-programs" }, place.programs.map((program) => h("li", {},
      h("span", {}, h("b", {}, program.title), h("small", {}, progress(program))),
      program.mine ? h("button", { class: "button primary small", type: "button",
        onclick: () => go("card", { id: program.id }) }, "Kartım") : null))),
    h("div", { class: "place-actions" },
      h("a", { class: "button secondary small", href: directionsUrl(place.lat, place.lng), target: "_blank", rel: "noopener" }, "Yol tarifi")));
}

function renderList() {
  const sorted = here ? [...places].sort((a, b) => distanceKm(here, [a.lat, a.lng]) - distanceKm(here, [b.lat, b.lng])) : places;
  $("place-list").replaceChildren(...(sorted.length
    ? sorted.map((place) => placeCard(place))
    : [h("p", { class: "empty-state" }, "Henüz haritada işletme yok.")]));
}

async function findMe(userAsked) {
  try {
    here = await locate();
    hereMarker = showHere(ml, map, here, hereMarker);
    moveTo(map, here, 15);
    renderList();
  } catch (error) {
    // Only a tap on the button deserves an error; the automatic first try stays quiet.
    if (userAsked) toast(error.message);
  }
}
