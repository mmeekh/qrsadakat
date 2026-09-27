// View switching and the bottom tab bar. Each view module calls defineView() with
// render (and optionally leave, tab); adding a screen never touches the others.
import { state } from "./state.js";
import { $, h } from "./ui.js";

const views = new Map();
let current = null;

const ICONS = {
  home: "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  map: "M12 21s-7-6.1-7-11.5A7 7 0 0 1 19 9.5C19 14.9 12 21 12 21zm0-9a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
  cards: "M4 6h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1zm-1 4h18",
  qr: "M4 4h6v6H4zm10 0h6v6h-6zM4 14h6v6H4zm10 0h2v2h-2zm4 0h2v2h-2zm-4 4h2v2h-2zm4 0h2v2h-2zm-2-2h2v2h-2z",
  dashboard: "M4 20V10m6 10V4m6 16v-7m4 7H3",
  account: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm-8 9a8 8 0 0 1 16 0",
};

function tabs() {
  if (state.me.merchant) {
    return [["qr", "QR"], ["dashboard", "Panel"], ["map", "Harita"], ["cards", "Kartlarım"], ["account", "Hesap"]];
  }
  if (state.me.user) return [["map", "Harita"], ["cards", "Kartlarım"], ["account", "Hesap"]];
  return [["home", "Keşfet"], ["map", "Harita"], ["account", "Giriş"]];
}

export function renderTabs() {
  const active = views.get(current)?.tab || current;
  $("tabbar").replaceChildren(...tabs().map(([name, label]) => {
    const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.setAttribute("viewBox", "0 0 24 24");
    icon.setAttribute("aria-hidden", "true");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", ICONS[name]);
    icon.append(path);
    return h("button", { type: "button", class: "tab", "aria-current": name === active ? "page" : false,
      onclick: () => go(name) }, icon, h("span", {}, label));
  }));
  const avatar = $("top-account");
  avatar.classList.toggle("hidden", !state.me.user);
  if (state.me.user) {
    avatar.replaceChildren(state.me.user.picture
      ? h("img", { src: state.me.user.picture, alt: "", referrerpolicy: "no-referrer" })
      : h("span", {}, state.me.user.name.slice(0, 1).toUpperCase()));
  }
}

export function defineView(name, spec) {
  views.set(name, spec);
}

export const hasView = (name) => views.has(name);

export async function go(name, options = {}) {
  if (!views.has(name)) name = "home";
  if (current && current !== name) views.get(current).leave?.();
  current = name;
  document.querySelectorAll("main > .view").forEach((section) => {
    section.classList.toggle("hidden", section.id !== `${name}-view`);
  });
  history.replaceState({}, "", name === "home" ? "/" : `/?view=${name}`);
  renderTabs();
  window.scrollTo(0, 0);
  await views.get(name).render?.(options);
}
