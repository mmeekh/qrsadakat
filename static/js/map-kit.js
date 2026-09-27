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

export function baseMap(L, element) {
  const map = L.map(element, { zoomControl: true }).setView([39.0, 35.0], 6);
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
