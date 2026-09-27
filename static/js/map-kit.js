// Leaflet + OpenStreetMap tiles, loaded only when a map is first shown.
import { themeFor } from "./qr-themes.js";

let loading = null;

export function loadLeaflet() {
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "/vendor/leaflet/leaflet.css";
      document.head.append(css);
      const script = document.createElement("script");
      script.src = "/vendor/leaflet/leaflet.js";
      script.onload = () => resolve(window.L);
      script.onerror = () => { loading = null; reject(new Error("Harita yüklenemedi.")); };
      document.head.append(script);
    });
  }
  return loading;
}

// Without the visitor's location the map opens at city scale on Istanbul, not the whole country.
export const DEFAULT_VIEW = { center: [41.0082, 28.9784], zoom: 11 };
const LOCATE_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/>' +
  '<path d="M12 2v3m0 14v3M2 12h3m14 0h3"/><circle cx="12" cy="12" r="8"/></svg>';

export function baseMap(L, element) {
  const map = L.map(element, { zoomControl: true }).setView(DEFAULT_VIEW.center, DEFAULT_VIEW.zoom);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  return map;
}

export function pinIcon(L, category) {
  const theme = themeFor(category);
  // Classes, not inline styles: the page's CSP forbids style attributes.
  return L.divIcon({ className: `map-pin pin-${theme.slug}`, html: `<span><i>${theme.icon}</i></span>`,
    iconSize: [42, 42], iconAnchor: [21, 40], popupAnchor: [0, -36] });
}

// A round "my location" button on the map itself, bottom right, as in Google Maps.
export function locateControl(L, map, onClick) {
  const Control = L.Control.extend({
    options: { position: "bottomright" },
    onAdd() {
      const button = L.DomUtil.create("button", "locate-control");
      button.type = "button";
      button.title = "Konumumu göster";
      button.setAttribute("aria-label", "Konumumu göster");
      button.innerHTML = LOCATE_ICON;
      L.DomEvent.disableClickPropagation(button);
      L.DomEvent.on(button, "click", async (event) => {
        L.DomEvent.preventDefault(event);
        button.classList.add("locating");
        try { await onClick(); } finally { button.classList.remove("locating"); }
      });
      return button;
    },
  });
  return new Control().addTo(map);
}

export function hereDot(L, map, latlng, existing) {
  if (existing) return existing.setLatLng(latlng);
  return L.circleMarker(latlng, { radius: 8, color: "#fff", weight: 3, fillColor: "#2447F5", fillOpacity: 1 }).addTo(map);
}

export function locate() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("Tarayıcın konum paylaşmayı desteklemiyor."));
    navigator.geolocation.getCurrentPosition(
      (position) => resolve([position.coords.latitude, position.coords.longitude]),
      () => reject(new Error("Konum izni verilmedi.")),
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
