// Maps: MapLibre GL (vector, self-hosted in /vendor/maplibre) on OpenFreeMap tiles, loaded only
// when a map is first shown. Views work in [lat, lng]; MapLibre wants [lng, lat], converted here.
import { themeFor } from "./qr-themes.js";

// bikıyak's "minimal grey + yellow roads" theme: OpenFreeMap Positron recoloured by
// deploy/build_map_style.py. Tiles, glyphs and sprites still come from OpenFreeMap; the
// attribution (OpenFreeMap, OpenMapTiles, OpenStreetMap) is required.
const STYLE = "/map-style.json";
// Without the visitor's location the map opens at city scale on Istanbul, not the whole country.
export const DEFAULT_VIEW = { center: [41.0082, 28.9784], zoom: 11 };
const LOCATE_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/>' +
  '<path d="M12 2v3m0 14v3M2 12h3m14 0h3"/><circle cx="12" cy="12" r="8"/></svg>';

let loading = null;

export function loadMaps() {
  if (!loading) {
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "/vendor/maplibre/maplibre-gl.css";
    document.head.append(css);
    loading = import("/vendor/maplibre/maplibre-gl.mjs").catch(() => {
      loading = null;
      throw new Error("Harita yüklenemedi.");
    });
  }
  return loading;
}

const lngLat = ([lat, lng]) => [lng, lat];

export function createMap(ml, element) {
  const map = new ml.Map({
    container: element, style: STYLE, center: lngLat(DEFAULT_VIEW.center), zoom: DEFAULT_VIEW.zoom,
    attributionControl: false, dragRotate: false, pitchWithRotate: false, touchPitch: false, cooperativeGestures: false,
  });
  map.touchZoomRotate.disableRotation();
  map.addControl(new ml.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new ml.AttributionControl({ compact: true }), "bottom-left");
  // The credit stays one tap away behind the "i" instead of covering the map on phones.
  map.once("load", () => element.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show"));
  return map;
}

export function moveTo(map, latlng, zoom, animate = true) {
  if (animate) map.flyTo({ center: lngLat(latlng), zoom, speed: 1.6 });
  else map.jumpTo({ center: lngLat(latlng), zoom });
}

function pinElement(category) {
  // Classes, not inline styles: the page's CSP forbids style attributes.
  const theme = themeFor(category);
  const pin = document.createElement("div");
  pin.className = `map-pin pin-${theme.slug}`;
  const drop = document.createElement("span");
  const icon = document.createElement("i");
  icon.textContent = theme.icon;
  drop.append(icon);
  pin.append(drop);
  return pin;
}

export function placeMarker(ml, map, category, latlng, { draggable = false, popup = null } = {}) {
  const marker = new ml.Marker({ element: pinElement(category), anchor: "bottom", draggable })
    .setLngLat(lngLat(latlng)).addTo(map);
  if (popup) {
    // Built when opened, so it shows the current distance and progress.
    const bubble = new ml.Popup({ offset: 40, maxWidth: "300px", closeButton: true });
    bubble.on("open", () => bubble.setDOMContent(popup()));
    marker.setPopup(bubble);
  }
  return marker;
}

export function setMarkerCategory(marker, category) {
  marker.getElement().className = `map-pin pin-${themeFor(category).slug}`;
}

export const markerLatLng = (marker) => { const p = marker.getLngLat(); return [p.lat, p.lng]; };

export function showHere(ml, map, latlng, existing) {
  if (existing) return existing.setLngLat(lngLat(latlng));
  const dot = document.createElement("div");
  dot.className = "here-dot";
  return new ml.Marker({ element: dot }).setLngLat(lngLat(latlng)).addTo(map);
}

// A round "my location" button on the map itself, bottom right, as in Google Maps.
export function addLocateControl(map, onClick) {
  map.addControl({
    onAdd() {
      const box = document.createElement("div");
      box.className = "maplibregl-ctrl";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "locate-control";
      button.title = "Konumumu göster";
      button.setAttribute("aria-label", "Konumumu göster");
      button.innerHTML = LOCATE_ICON;
      button.addEventListener("click", async () => {
        button.classList.add("locating");
        try { await onClick(); } finally { button.classList.remove("locating"); }
      });
      box.append(button);
      return box;
    },
    onRemove() {},
  }, "bottom-right");
}

export function locate() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("Tarayıcın konum paylaşmayı desteklemiyor."));
    navigator.geolocation.getCurrentPosition(
      (position) => resolve([position.coords.latitude, position.coords.longitude]),
      (error) => reject(new Error(error.code === error.PERMISSION_DENIED
        ? "Konum izni verilmedi. Tarayıcı ayarlarından bikıyak.com için Konum'u İzin Ver yapıp tekrar dene."
        : "Konumun şu an alınamadı. Bağlantını kontrol edip tekrar dene.")),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  });
}

export function distanceKm([lat1, lng1], [lat2, lng2]) {
  const rad = Math.PI / 180;
  const a = Math.sin((lat2 - lat1) * rad / 2) ** 2 +
    Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin((lng2 - lng1) * rad / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(a));
}

export const directionsUrl = (lat, lng) => `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
