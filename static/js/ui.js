export const $ = (id) => document.getElementById(id);

// Small element builder; strings become text nodes, never HTML.
export function h(tag, props = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") element.className = value;
    else if (key.startsWith("on")) element.addEventListener(key.slice(2), value);
    else if (value !== false && value != null) element.setAttribute(key, value === true ? "" : value);
  }
  element.append(...children.flat().filter((child) => child != null && child !== false));
  return element;
}

let toastTimer = null;
export function toast(message) {
  const box = $("toast");
  box.textContent = message;
  box.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => box.classList.add("hidden"), 4200);
}

export function googleButton(label, onClick) {
  const button = $("google-button-template").content.firstElementChild.cloneNode(true);
  button.querySelector("span").textContent = label;
  button.addEventListener("click", async () => {
    button.disabled = true;
    try { await onClick(); } catch (error) { toast(error.message); button.disabled = false; }
  });
  return button;
}

export function stampDots(stamps, required) {
  return h("div", { class: "card-stamps" }, Array.from({ length: required }, (_, i) => {
    const last = i === required - 1;
    const filled = i < stamps;
    return h("span", { class: `stamp ${filled ? "filled" : last ? "gift" : ""}` }, filled ? "✓" : last ? "✦" : "");
  }));
}

export function emptyState(text, ...actions) {
  return h("div", { class: "empty-block" }, h("p", { class: "empty-state" }, text), ...actions);
}
