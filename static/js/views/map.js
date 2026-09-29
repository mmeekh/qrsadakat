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
    markers = places.map((place) => {
      const marker = placeMarker(ml, map, place.category, [place.lat, place.lng], { popup: () => placePopup(place) });
      // The bubble opens above the pin, so the pin moves low in the frame and the bubble fits.
      marker.getPopup().on("open", () => map.easeTo({ center: [place.lng, place.lat], offset: pinLow() }));
      return marker;
    });
    moveTo(map, here || DEFAULT_VIEW.center, here ? 15 : DEFAULT_VIEW.zoom, false);
    setTimeout(() => map.resize(), 0);
    renderList();
  },
});

function progress(program) {
  if (!program.mine) return "Henüz kartın yok";
  const reward = program.mine.rewards_available ? ` · ${program.mine.rewards_available} ödül hazır` : "";
  return `${program.mine.stamps} / ${program.stamps_required} damga${reward}`;
}

function distanceText(place) {
  return here ? ` · ${distanceKm(here, [place.lat, place.lng]).toFixed(1)} km` : "";
}

// The business photo, or the category icon on its colour when there is none yet.
function photo(place, className) {
  const theme = themeFor(place.category);
  return h("div", { class: `${className} pin-${theme.slug}` }, place.photo
    ? h("img", { src: place.photo, alt: "", loading: "lazy", decoding: "async" })
    : h("span", { "aria-hidden": "true" }, theme.icon));
}

function offers(place, className) {
  return h("ul", { class: className }, place.programs.map((program) => h("li", {},
    h("span", {}, h("b", {}, program.title), h("small", {}, progress(program))),
    program.mine ? h("button", { class: "button primary small", type: "button",
      onclick: (event) => { event.stopPropagation(); go("card", { id: program.id }); } }, "Kartım") : null)));
}

function directions(place) {
  return h("a", { class: "place-directions", href: directionsUrl(place.lat, place.lng), target: "_blank", rel: "noopener",
    onclick: (event) => event.stopPropagation() }, "Yol tarifi");
}

// The bubble on a pin: photo on top, cards, and a line on sample places so nobody walks to one.
function placePopup(place) {
  return h("div", { class: "place-popup" }, photo(place, "place-popup-photo"),
    h("strong", { class: "place-name" }, place.business_name),
    h("small", { class: "place-meta" }, `${place.category}${distanceText(place)}`),
    place.demo ? h("small", { class: "demo-note" }, "Örnek işletme · adreste gerçek dükkân yok") : null,
    offers(place, "place-programs"), directions(place));
}

// A row under the map. Tapping it shows the place on the map; directions and "Kartım" act alone.
function placeRow(place) {
  return h("article", { class: "place-row", tabindex: "0", role: "button", "data-place": place.id,
    "aria-label": `${place.business_name}: haritada göster`,
    onclick: () => showOnMap(place),
    onkeydown: (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); showOnMap(place); } } },
  photo(place, "place-photo"),
  h("div", { class: "place-body" },
    h("div", { class: "place-title" }, h("strong", {}, place.business_name),
      place.demo ? h("span", { class: "demo-chip", title: "Adreste gerçek bir dükkân yok." }, "Örnek işletme") : null),
    h("div", { class: "place-meta-line" }, h("small", { class: "place-meta" }, `${place.category}${distanceText(place)}`),
      directions(place)),
    offers(place, "place-offers")));
}

const pinLow = () => [0, Math.round($("map-canvas").clientHeight * 0.36)];

function showOnMap(place) {
  const index = places.indexOf(place);
  document.querySelectorAll(".place-row.active").forEach((row) => row.classList.remove("active"));
  document.querySelector(`.place-row[data-place="${place.id}"]`)?.classList.add("active");
  $("map-canvas").scrollIntoView({ behavior: "smooth", block: "center" });
  markers.forEach((marker, i) => { if (i !== index && marker.getPopup()?.isOpen()) marker.togglePopup(); });
  if (!markers[index].getPopup().isOpen()) markers[index].togglePopup();
  // After the popup's own pan, so this flight (which also zooms in) is the one that runs.
  map.flyTo({ center: [place.lng, place.lat], zoom: Math.max(map.getZoom(), 15), offset: pinLow(), speed: 1.6 });
}

function renderList() {
  const sorted = here ? [...places].sort((a, b) => distanceKm(here, [a.lat, a.lng]) - distanceKm(here, [b.lat, b.lng])) : places;
  $("place-list").replaceChildren(...(sorted.length
    ? sorted.map(placeRow)
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
