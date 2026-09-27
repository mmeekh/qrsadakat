// The reward part of the card form: free item, percent or amount discount, or own text.
// The server builds the final wording (programs.reward_title on the server); this mirrors it for the preview.
import { $ } from "../ui.js";

const form = $("program-form");
const kind = () => form.querySelector("input[name=reward_type]:checked").value;

export function rewardText() {
  const required = form.stamps_required.value || "?";
  const text = {
    free: `${required} damga topla, ${form.reward_item.value.trim() || "…"} bedava`,
    percent: `${required} damga topla, %${form.reward_percent.value || "…"} indirim kazan`,
    amount: `${required} damga topla, ${form.reward_money.value || "…"} ₺ indirim kazan`,
    custom: form.reward_title.value.trim() || "…",
  };
  return text[kind()];
}

function refresh() {
  // Hidden fields are disabled so the browser neither validates nor submits them.
  form.querySelectorAll("[data-reward]").forEach((label) => {
    const active = label.dataset.reward === kind();
    label.classList.toggle("hidden", !active);
    label.querySelector("input").disabled = !active;
  });
  $("reward-preview").textContent = rewardText();
}

export function fillReward(program) {
  const type = program?.reward_type || "free";
  form.querySelector(`input[name=reward_type][value="${type}"]`).checked = true;
  form.reward_item.value = program?.reward_item || "";
  form.reward_percent.value = type === "percent" ? program.reward_amount : 20;
  form.reward_money.value = type === "amount" ? program.reward_amount : 50;
  form.reward_title.value = type === "custom" ? program?.title || "" : "";
  refresh();
}

export function rewardFields() {
  const type = kind();
  return {
    reward_type: type,
    reward_item: form.reward_item.value,
    reward_amount: type === "percent" ? form.reward_percent.value : type === "amount" ? form.reward_money.value : 0,
    reward_title: form.reward_title.value,
  };
}

form.addEventListener("input", refresh);
form.addEventListener("change", refresh);
