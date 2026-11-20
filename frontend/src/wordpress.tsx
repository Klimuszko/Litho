import {createRoot} from "react-dom/client";
import {LithophaneGenerator, Params, LithophaneGenerateResult} from "./LithophaneConfigurator";
import "./wordpress.css";

type WooConfig = {
  restUrl: string;
  nonce: string;
  csrf: string;
  productId: number;
  housingColors: Record<string, string>;
  ledColors: Record<string, string>;
  messages: Record<string, string>;
};

declare global {
  interface Window { LithoConfig?: WooConfig; }
}

let mounted = false;

function mountConfigurator() {
  if (mounted) return;
  const mount = document.getElementById("litho-configurator-mount");
  const config = window.LithoConfig;
  if (!mount || !config) return;
  mounted = true;
  const apiRoot = config.restUrl.replace(/\/$/, "");
  const fixed = {width_mm: 200, height_mm: 150};
  const initial: Params = {
    width_mm: fixed.width_mm, height_mm: fixed.height_mm, min_thickness_mm: 1, max_thickness_mm: 4,
    gamma: 1, brightness: 1, contrast: 1.25, nozzle_diameter_mm: .4, quality_profile: "maximum",
    orientation: "landscape", fit_mode: "cover", border_width_mm: 0, border_height_mm: 4,
    border_widths_mm: null, mounting_flange: true, invert: false, mirror: false, rotation_degrees: 0,
    crop: {x: 0, y: 0, width: 1, height: 1},
  };
  const cartButton = document.querySelector<HTMLButtonElement>("form.cart button.single_add_to_cart_button");
  const projectIdInput = document.querySelector<HTMLInputElement>("#litho-project-id");
  const signatureInput = document.querySelector<HTMLInputElement>("#litho-project-signature");
  const status = document.querySelector<HTMLElement>("#litho-status");

  const setCart = (enabled: boolean) => { if (cartButton) cartButton.disabled = !enabled; };
  const setStatus = (message: string, type = "") => {
    if (status) { status.textContent = message; status.className = `litho-status ${type}`.trim(); }
  };
  const clearProject = () => {
    if (projectIdInput) projectIdInput.value = "";
    if (signatureInput) signatureInput.value = "";
    setCart(false);
  };
  const readWooChoice = (kind: "housing" | "led") => {
    const directSelectors = kind === "housing"
      ? ["#litho-housing-color", 'form.cart select[name="housing_color"]', 'form.cart select[name="attribute_housing-color"]', 'form.cart select[name="attribute_pa_housing-color"]', 'form.cart select[name*="kolor"]', 'form.cart select[name*="color"]', 'form.cart select[id*="housing"]', 'form.cart select[id*="kolor"]', 'form.cart select[id*="color"]']
      : ["#litho-led-color", 'form.cart select[name="light_temperature"]', 'form.cart select[name="attribute_led-color"]', 'form.cart select[name="attribute_pa_led-color"]', 'form.cart select[name*="barwa"]', 'form.cart select[name*="led"]', 'form.cart select[name*="temper"]', 'form.cart select[id*="led"]', 'form.cart select[id*="barwa"]', 'form.cart select[id*="temper"]'];
    for (const selector of directSelectors) {
      const select = document.querySelector<HTMLSelectElement>(selector);
      if (select?.value) return select.value;
    }
    const terms = kind === "housing" ? /kolor|obudow|housing|case/i : /led|barw|temper|light/i;
    const select = Array.from(document.querySelectorAll<HTMLSelectElement>("form.cart select")).find((candidate) => {
      const context = `${candidate.name} ${candidate.id} ${candidate.closest(".variations, .woocommerce-variation-add-to-cart, .value")?.textContent || ""}`;
      return terms.test(context) && Boolean(candidate.value);
    });
    return select?.value || "";
  };
  const normalizeChoice = (value: string, choices: Record<string, string>, fallback: string) => {
    const slug = (input: string) => input.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    const valueSlug = slug(value);
    const match = Object.entries(choices || {}).find(([key, label]) => slug(key) === valueSlug || slug(label) === valueSlug);
    return match?.[0] || fallback;
  };
  const request = async (path: string, init: RequestInit = {}, browserToken = "") => {
    const headers = new Headers(init.headers);
    headers.set("X-Litho-Nonce", config.nonce);
    headers.set("X-Litho-CSRF-Token", config.csrf);
    if (browserToken) headers.set("X-Litho-Project-Key", browserToken);
    const response = await fetch(`${apiRoot}${path}`, {...init, headers, credentials: "same-origin"});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || config.messages.failed || "Nie udało się przygotować projektu.");
    return data;
  };
  const waitForProject = async (projectId: string, browserToken: string) => {
    for (let attempt = 0; attempt < 150; attempt += 1) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      const result = await request(`/projects/${encodeURIComponent(projectId)}`, {}, browserToken);
      if (result.status === "completed") return result;
      if (result.status === "failed") throw new Error(result.generation_error || config.messages.failed);
    }
    throw new Error("Generowanie trwa zbyt długo. Spróbuj ponownie później.");
  };
  const generate = async (file: File, params: Params): Promise<LithophaneGenerateResult> => {
    setStatus(config.messages.working || "Przygotowujemy projekt…", "working");
    const orientation = params.orientation === "portrait" ? "portrait" : "landscape";
    const housingDefault = Object.keys(config.housingColors || {})[0] || "black-matte";
    const ledDefault = Object.keys(config.ledColors || {})[0] || "warm";
    const housingColor = normalizeChoice(readWooChoice("housing"), config.housingColors, housingDefault);
    const ledColor = normalizeChoice(readWooChoice("led"), config.ledColors, ledDefault);
    const created = await request("/projects", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        product_id: config.productId, size: "150x200", orientation,
        housing_color: housingColor,
        light_temperature: ledColor,
        brightness: params.brightness, contrast: params.contrast, gamma: params.gamma,
        fit_mode: params.fit_mode, rotation_degrees: params.rotation_degrees, crop: params.crop,
      }),
    });
    const body = new FormData(); body.append("image", file, file.name);
    await request(`/projects/${encodeURIComponent(created.project_id)}/image`, {method: "POST", body}, created.browser_token);
    await request(`/projects/${encodeURIComponent(created.project_id)}/generate`, {method: "POST"}, created.browser_token);
    await waitForProject(created.project_id, created.browser_token);
    if (projectIdInput) projectIdInput.value = created.project_id;
    if (signatureInput) signatureInput.value = created.cart_signature;
    setStatus(config.messages.ready || "Projekt jest gotowy.", "success");
    setCart(true);
    return {projectId: created.project_id, signature: created.cart_signature};
  };

  setCart(false);
  try {
    createRoot(mount).render(
      <LithophaneGenerator
        active
        embedded
        initialParams={initial}
        onGenerateOverride={generate}
        onParamsChanged={clearProject}
        apiFetchOverride={(input, init) => fetch(input, {...init, credentials: "same-origin"})}
      />,
    );
  } catch (reason) {
    mounted = false;
    mount.innerHTML = "<p class=\"litho-status error\">Nie udało się uruchomić konfiguratora. Odśwież stronę.</p>";
    if (window.console) console.error("Litho React configurator failed to mount", reason);
  }
}

// Themes, cache/minification plugins and WooCommerce templates can change the
// order in which the mount element and the localized config become available.
// Try immediately, then once after DOMContentLoaded so the bundle is reliable
// regardless of where WordPress places the footer script.
mountConfigurator();
if (!mounted) document.addEventListener("DOMContentLoaded", mountConfigurator, {once: true});
