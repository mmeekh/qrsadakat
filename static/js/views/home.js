// Home: what bikıyak is, dynamic action buttons, and merchant inquiry interactions.
import { signIn } from "../api.js";
import { defineView, go } from "../nav.js";
import { state } from "../state.js";
import { $, googleButton, h } from "../ui.js";

function setupInteractions() {
  const modal = $("merchant-modal");
  const modalClose = $("modal-close");
  const modalSuccessClose = $("modal-success-close");
  const form = $("merchant-inquiry-form");
  const successBox = $("modal-success");

  function openModal() {
    if (!modal) return;
    modal.classList.remove("hidden");
    if (form) form.classList.remove("hidden");
    if (successBox) successBox.classList.add("hidden");
    document.body.style.overflow = "hidden";
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.style.overflow = "";
  }

  // Open modal buttons
  document.querySelectorAll(".btn-open-merchant").forEach((btn) => {
    btn.onclick = (e) => { e.preventDefault(); openModal(); };
  });

  if (modalClose) modalClose.onclick = closeModal;
  if (modalSuccessClose) modalSuccessClose.onclick = closeModal;
  if (modal) {
    modal.onclick = (e) => {
      if (e.target === modal) closeModal();
    };
  }

  // Form submission
  if (form) {
    form.onsubmit = (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const name = fd.get("m_name") || "";
      const cat = fd.get("m_category") || "";
      const city = fd.get("m_city") || "";
      const owner = fd.get("m_owner") || "";
      const phone = fd.get("m_phone") || "";
      const email = fd.get("m_email") || "";
      const reward = fd.get("m_reward") || "";

      // Construct mailto link
      const subject = encodeURIComponent(`İşletme Başvurusu: ${name} (${city})`);
      const body = encodeURIComponent(
        `İşletme Adı: ${name}\nKategori: ${cat}\nŞehir/İlçe: ${city}\nYetkili: ${owner}\nTelefon: ${phone}\nE-posta: ${email}\nKampanya Düşüncesi: ${reward}\n\n(bikıyak 2 Ay Ücretsiz Başvuru Formu)`
      );
      const mailtoUrl = `mailto:iletisim@xn--bikyak-r9a.com?subject=${subject}&body=${body}`;

      // Open email client in background
      const a = document.createElement("a");
      a.href = mailtoUrl;
      a.target = "_blank";
      a.click();

      // Show success in modal
      form.classList.add("hidden");
      successBox.classList.remove("hidden");
    };
  }

  // Map explore buttons
  const btnExplore = $("btn-hero-explore");
  if (btnExplore) btnExplore.onclick = () => go("map");

  const btnShowcaseMap = $("btn-showcase-map");
  if (btnShowcaseMap) btnShowcaseMap.onclick = () => go("map");

  const btnNavMap = $("nav-btn-map");
  if (btnNavMap) btnNavMap.onclick = () => go("map");

  const btnFooterMap = $("footer-btn-map");
  if (btnFooterMap) btnFooterMap.onclick = () => go("map");

  // Wire horizontal sliders (Value cards & Showcase cards)
  function wireSlider(sliderId, dotsId) {
    const slider = $(sliderId);
    const dotsWrap = $(dotsId);
    if (!slider || !dotsWrap) return;
    const dots = dotsWrap.querySelectorAll(".s-dot");
    const cards = slider.children;

    dots.forEach((dot, idx) => {
      dot.onclick = () => {
        if (cards[idx]) {
          cards[idx].scrollIntoView({ behavior: "smooth", inline: "start", block: "nearest" });
        }
      };
    });

    let timeout;
    slider.addEventListener("scroll", () => {
      clearTimeout(timeout);
      timeout = setTimeout(() => {
        const scrollLeft = slider.scrollLeft;
        let activeIdx = 0;
        let minDiff = Infinity;
        Array.from(cards).forEach((card, idx) => {
          const diff = Math.abs(card.offsetLeft - slider.offsetLeft - scrollLeft);
          if (diff < minDiff) {
            minDiff = diff;
            activeIdx = idx;
          }
        });
        dots.forEach((d, i) => d.classList.toggle("active", i === activeIdx));
      }, 50);
    }, { passive: true });
  }

  wireSlider("value-slider", "value-dots");
  wireSlider("showcase-slider", "showcase-dots");

}

let initialized = false;

defineView("home", {
  render() {
    const { user, merchant } = state.me;
    $("home-actions").replaceChildren(user
      ? h("button", { class: "button primary", type: "button", onclick: () => go(merchant ? "programs" : "cards") },
        "Kartlarıma git ", h("span", {}, "→"))
      : googleButton("Google ile giriş yap", () => signIn("cards")));

    if (!initialized) {
      setupInteractions();
      initialized = true;
    }
  },
});
