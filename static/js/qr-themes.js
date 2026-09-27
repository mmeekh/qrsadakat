// Counter QR themed by business category. Scanners need dark modules on a light field,
// a 4-module quiet zone and intact finder patterns, so the themed picture lives in the
// frame around the code; inside it only module shapes, colours and the finder "eyes" change.
const SVG = "http://www.w3.org/2000/svg";

export const THEMES = {
  "Kafe": { slug: "kafe", icon: "☕", frame: "cup", dot: "round", eye: "bean", ink: "#3b2416", eyeInk: "#24130a",
    crease: "#6b4430", paper: "#fffaf1", body: "#8a5a3b", trim: "#5b3a26", soft: "#c9a488", label: "#fff5e6" },
  "Restoran": { slug: "restoran", icon: "🍽️", frame: "plate", dot: "round", eye: "dot", ink: "#4a1d17", eyeInk: "#33120d",
    paper: "#fffdf8", body: "#f3e7da", trim: "#c49a7c", soft: "#8f949c", label: "#4a1d17" },
  "Fırın & pastane": { slug: "firin", icon: "🥐", frame: "loaf", dot: "round", eye: "dot", ink: "#5a3510", eyeInk: "#3f2408",
    paper: "#fffaf0", body: "#d49a4a", trim: "#a86b25", soft: "#f6dfb1", label: "#fff4de" },
  "Market": { slug: "market", icon: "🛒", frame: "bag", dot: "square", eye: "square", ink: "#17432a", eyeInk: "#0f2f1d",
    paper: "#fbfff8", body: "#5e9e5a", trim: "#3f7a3e", soft: "#2c5a31", label: "#f4fff0" },
  "Berber & kuaför": { slug: "berber", icon: "✂️", frame: "pole", dot: "square", eye: "square", ink: "#1b2742", eyeInk: "#111a30",
    paper: "#fbfcff", body: "#24345a", trim: "#c8363a", soft: "#2f58a8", label: "#eef2ff" },
  "Diğer": { slug: "diger", icon: "✦", frame: "card", dot: "square", eye: "square", ink: "#0B1433", eyeInk: "#0B1433",
    paper: "#FFFFFF", body: "#2447F5", trim: "#1B38D6", soft: "#FFC933", label: "#FFFFFF" },
};

export const themeFor = (category) => THEMES[category] || THEMES["Diğer"];

const n3 = (value) => Math.round(value * 1000) / 1000;

function node(tag, attrs, parent) {
  const element = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, typeof value === "number" ? n3(value) : value);
  if (parent) parent.append(element);
  return element;
}

function modules(text) {
  const holder = document.createElement("div");
  const code = new QRCode(holder, { text, width: 64, height: 64, correctLevel: QRCode.CorrectLevel.Q });
  const model = code._oQRCode;
  return { size: model.getModuleCount(), dark: (row, col) => model.isDark(row, col) };
}

const circle = (cx, cy, r) => `M${n3(cx - r)} ${n3(cy)}a${r} ${r} 0 1 0 ${n3(2 * r)} 0a${r} ${r} 0 1 0 ${n3(-2 * r)} 0`;

function roundRect(x, y, w, h, r) {
  const a = `a${r} ${r} 0 0 1`;
  return `M${n3(x + r)} ${n3(y)}h${n3(w - 2 * r)}${a} ${r} ${r}v${n3(h - 2 * r)}${a} ${-r} ${r}` +
    `h${n3(2 * r - w)}${a} ${-r} ${-r}v${n3(2 * r - h)}${a} ${r} ${-r}z`;
}

function drawEye(group, theme, x, y) {
  node("path", { d: roundRect(x, y, 7, 7, 1.8) + roundRect(x + 1, y + 1, 5, 5, 1.1), "fill-rule": "evenodd", fill: theme.eyeInk }, group);
  if (theme.eye === "bean") {
    node("ellipse", { cx: x + 3.5, cy: y + 3.5, rx: 1.62, ry: 1.3, fill: theme.eyeInk,
      transform: `rotate(-35 ${n3(x + 3.5)} ${n3(y + 3.5)})` }, group);
    // The crease stays dark enough to read as "dark" to a scanner.
    node("path", { d: `M${n3(x + 2.6)} ${n3(y + 4.5)}c.5-.2.6-.9.9-1.2s.7-.6 1-.9`, fill: "none",
      stroke: theme.crease, "stroke-width": 0.26, "stroke-linecap": "round" }, group);
  } else if (theme.eye === "dot") {
    node("path", { d: circle(x + 3.5, y + 3.5, 1.55), fill: theme.eyeInk }, group);
  } else {
    node("path", { d: roundRect(x + 2, y + 2, 3, 3, 0.8), fill: theme.eyeInk }, group);
  }
}

function drawCode(group, qr, theme, x0, y0) {
  const n = qr.size;
  node("rect", { x: x0, y: y0, width: n + 8, height: n + 8, rx: 2.2, fill: theme.paper }, group);
  const inEye = (r, c) => (r < 7 && c < 7) || (r < 7 && c >= n - 7) || (r >= n - 7 && c < 7);
  let d = "";
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      if (!qr.dark(r, c) || inEye(r, c)) continue;
      const x = x0 + 4 + c, y = y0 + 4 + r;
      d += theme.dot === "round" ? circle(x + 0.5, y + 0.5, 0.47) : roundRect(x + 0.05, y + 0.05, 0.9, 0.9, 0.26);
    }
  }
  node("path", { d, fill: theme.ink }, group);
  for (const [r, c] of [[0, 0], [0, n - 7], [n - 7, 0]]) drawEye(group, theme, x0 + 4 + c, y0 + 4 + r);
}

// Each frame draws its picture and says where the code square and the label go.
const FRAMES = {
  cup(g, S, t) {
    const pad = 2.4, L = S * 0.15, steam = S * 0.3, w = S + 2 * pad, h = S + 2 * pad + L, top = steam, r = w * 0.2;
    const q = steam * 0.13, a = S * 0.045;
    for (const k of [0.3, 0.5, 0.7]) {
      node("path", { d: `M${n3(w * k)} ${n3(top - 2)}c${-a} ${-q} ${a} ${-2 * q} 0 ${-3 * q}s${-a} ${-2 * q} 0 ${-3 * q}`,
        fill: "none", stroke: t.soft, "stroke-width": S * 0.03, "stroke-linecap": "round" }, g);
    }
    node("circle", { cx: w + S * 0.04, cy: top + h * 0.36, r: S * 0.15, fill: "none", stroke: t.body, "stroke-width": S * 0.07 }, g);
    node("path", { d: `M0 ${n3(top)}H${n3(w)}V${n3(top + h - r)}Q${n3(w)} ${n3(top + h)} ${n3(w - r)} ${n3(top + h)}` +
      `H${n3(r)}Q0 ${n3(top + h)} 0 ${n3(top + h - r)}Z`, fill: t.body }, g);
    node("rect", { x: -1, y: top - 1.2, width: w + 2, height: 2.4, rx: 1.2, fill: t.trim }, g);
    node("ellipse", { cx: w / 2, cy: top + h + 1.3, rx: w * 0.64, ry: 2, fill: t.trim }, g);
    return { code: [pad, top + pad], label: [w / 2, top + pad + S + L * 0.62, L * 0.42],
      box: [-S * 0.12, 0, w + S * 0.37, top + h + 3.8] };
  },
  plate(g, S, t) {
    // The plate hugs the code square (half its diagonal is 0.707 S) so the code stays large.
    const R = S * 0.72, u = S * 0.11, cx = u + R, cy = R + 1, L = S * 0.13;
    node("circle", { cx, cy, r: R, fill: t.body, stroke: t.trim, "stroke-width": 0.8 }, g);
    node("circle", { cx, cy, r: R * 0.93, fill: "none", stroke: t.trim, "stroke-width": 0.35 }, g);
    const fx = u * 0.45, top = cy - S * 0.42;
    for (const dx of [-1.1, 0, 1.1]) node("rect", { x: fx + dx - 0.3, y: top, width: 0.6, height: S * 0.16, rx: 0.3, fill: t.soft }, g);
    node("path", { d: roundRect(fx - 1.4, top + S * 0.14, 2.8, 1.6, 0.6), fill: t.soft }, g);
    node("path", { d: roundRect(fx - 0.8, top + S * 0.15, 1.6, S * 0.66, 0.8), fill: t.soft }, g);
    const kx = cx + R + u * 0.55;
    node("path", { d: `M${n3(kx - 0.9)} ${n3(top + S * 0.36)}V${n3(top + 2)}Q${n3(kx + 1.4)} ${n3(top)} ${n3(kx + 1)} ${n3(top + S * 0.36)}Z`, fill: t.soft }, g);
    node("path", { d: roundRect(kx - 0.9, top + S * 0.36, 1.8, S * 0.46, 0.9), fill: t.soft }, g);
    return { code: [cx - S / 2, cy - S / 2], label: [cx, cy + R + L * 0.8, L * 0.5], box: [0, 0, 2 * (u + R), 2 * R + L + 2] };
  },
  loaf(g, S, t) {
    const pad = 2.4, L = S * 0.15, D = S * 0.3, w = S + 2 * pad, h = D + S + 2 * pad + L;
    node("path", { d: `M0 ${n3(D)}a${n3(w / 2)} ${n3(D)} 0 0 1 ${n3(w)} 0V${n3(h - 2)}q0 2-2 2H2q-2 0-2-2Z`, fill: t.body }, g);
    for (const k of [0.27, 0.45, 0.63]) {
      node("path", { d: `M${n3(w * k)} ${n3(D * 0.82)}q${n3(S * 0.05)} ${n3(-D * 0.38)} ${n3(S * 0.13)} ${n3(-D * 0.32)}`,
        fill: "none", stroke: t.soft, "stroke-width": S * 0.028, "stroke-linecap": "round" }, g);
    }
    node("rect", { x: 0, y: h - L - 0.6, width: w, height: 0.5, fill: t.trim }, g);
    return { code: [pad, D + pad * 0.4], label: [w / 2, h - L * 0.36, L * 0.42], box: [-1, -1, w + 2, h + 2] };
  },
  bag(g, S, t) {
    const pad = 2.4, L = S * 0.15, H = S * 0.22, w = S + 2 * pad, h = S + 2 * pad + L + 2;
    node("path", { d: `M${n3(w * 0.28)} ${n3(H + 1)}c0 ${n3(-H * 1.25)} ${n3(w * 0.44)} ${n3(-H * 1.25)} ${n3(w * 0.44)} 0`,
      fill: "none", stroke: t.soft, "stroke-width": S * 0.045, "stroke-linecap": "round" }, g);
    node("rect", { x: 0, y: H, width: w, height: h, rx: 1.6, fill: t.body }, g);
    node("rect", { x: 0, y: H, width: w, height: 2, fill: t.trim }, g);
    return { code: [pad, H + 2 + pad * 0.6], label: [w / 2, H + h - L * 0.36, L * 0.42], box: [-1, 0, w + 2, H + h + 1] };
  },
  pole(g, S, t) {
    const pad = 2.4, L = S * 0.15, P = S * 0.11, w = S + 2 * pad, h = S + 2 * pad + L, id = "pole" + Math.random().toString(36).slice(2);
    const pattern = node("pattern", { id, width: 4.5, height: 4.5, patternUnits: "userSpaceOnUse", patternTransform: "rotate(35)" },
      node("defs", {}, g));
    [["#ffffff", 0], [t.trim, 1.5], [t.soft, 3]].forEach(([fill, x]) => node("rect", { x, y: 0, width: 1.5, height: 4.5, fill }, pattern));
    for (const x of [-P - 1, w + 1]) {
      node("rect", { x, y: 1.5, width: P, height: h - 3, rx: P / 2, fill: `url(#${id})`, stroke: "#c9ccd6", "stroke-width": 0.4 }, g);
      node("rect", { x: x - 0.4, y: 0, width: P + 0.8, height: 2, rx: 1, fill: "#c9ccd6" }, g);
      node("rect", { x: x - 0.4, y: h - 2, width: P + 0.8, height: 2, rx: 1, fill: "#c9ccd6" }, g);
    }
    node("rect", { x: 0, y: 0, width: w, height: h, rx: 2.4, fill: t.body }, g);
    return { code: [pad, pad], label: [w / 2, pad + S + L * 0.62, L * 0.42], box: [-P - 2, -0.5, w + 2 * P + 4, h + 1] };
  },
  card(g, S, t) {
    const pad = 2.4, L = S * 0.15, w = S + 2 * pad, h = S + 2 * pad + L;
    node("rect", { x: 0, y: 0, width: w, height: h, rx: 3, fill: t.body }, g);
    return { code: [pad, pad], label: [w / 2, pad + S + L * 0.62, L * 0.42], box: [-0.5, -0.5, w + 1, h + 1] };
  },
};

export function renderThemedQr(target, text, category, label) {
  const theme = themeFor(category);
  const qr = modules(text);
  const S = qr.size + 8;
  const svg = node("svg", { role: "img", "aria-label": `${label} QR kodu`, class: `themed-qr qr-${theme.slug}` });
  const layout = FRAMES[theme.frame](node("g", {}, svg), S, theme);
  drawCode(node("g", {}, svg), qr, theme, ...layout.code);
  const [x, y, size] = layout.label;
  const caption = node("text", { x, y, "font-size": size, fill: theme.label, "text-anchor": "middle",
    "font-family": "Sora, 'Plus Jakarta Sans', sans-serif", "font-weight": 700 }, svg);
  caption.textContent = `${theme.icon} ${label.length > 26 ? label.slice(0, 25) + "…" : label}`;
  svg.setAttribute("viewBox", layout.box.map(n3).join(" "));
  target.replaceChildren(svg);
}
