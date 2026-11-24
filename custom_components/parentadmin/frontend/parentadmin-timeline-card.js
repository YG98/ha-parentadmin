/* ParentAdmin timeline card — ships with the parentadmin integration.
 *
 * type: custom:parentadmin-timeline-card
 * entity: sensor.<child>_nursery_timeline   (required)
 * title: "Today at nursery"                  (optional, default "<First name>'s diary")
 * order: asc | desc                          (optional, default asc = same as the website)
 * photo_columns: 1                           (optional, default 1 = full width like the website)
 * show_header: true                          (optional)
 */
const CARD_VERSION = "0.2.0";

const TYPES = {
  "check-in": { color: "#4FB269", icon: "mdi:door-open" },
  "check-out": { color: "#4FB269", icon: "mdi:door-closed" },
  food: { color: "#505C9F", icon: "mdi:silverware-fork-knife" },
  drink: { color: "#4896C1", icon: "mdi:cup-water" },
  nappy: { color: "#CA714A", icon: "mdi:human-baby-changing-table" },
  sleep: { color: "#4FB269", icon: "mdi:bed-outline" },
  photo: { color: "#BD6A97", icon: "mdi:camera-outline" },
};
const FALLBACK = { color: "var(--primary-color)", icon: "mdi:circle-medium" };

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function fmtTime(hhmm) {
  if (!hhmm) return "";
  const [h, m] = hhmm.split(":").map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")}${h >= 12 ? "pm" : "am"}`;
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(`${iso}T12:00:00`);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return "Today";
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

function ring(pct, color) {
  const r = 16;
  const c = 2 * Math.PI * r;
  const p = Math.max(0, Math.min(100, pct));
  return `<svg class="ring" viewBox="0 0 40 40" aria-label="${p}% eaten">
    <circle cx="20" cy="20" r="${r}" fill="none" stroke="var(--divider-color)" stroke-width="2.5"/>
    <circle cx="20" cy="20" r="${r}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linecap="round"
      stroke-dasharray="${((c * p) / 100).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 20 20)"/>
    <text x="20" y="21.5" text-anchor="middle" dominant-baseline="middle" fill="${color}">${p}<tspan class="pc" dy="-3">%</tspan></text>
  </svg>`;
}

function figure(e, color) {
  const value = String(e.value ?? "").trim();
  if (e.type === "food" && /^\d+$/.test(value)) return ring(Number(value), color);
  if (!value || e.type === "photo") return "";
  // "30ml" -> 30<small>ml</small>, "1Hrs 30Mins" -> 1<small>Hrs</small> 30<small>Mins</small>
  return esc(value).replace(/(\d+(?:\.\d+)?)\s*([A-Za-z]+)/g, "$1<small>$2</small>");
}

class ParentAdminTimelineCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.entity) throw new Error("Set 'entity' to the ParentAdmin timeline sensor");
    this._config = { order: "asc", photo_columns: 1, show_header: true, ...config };
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    }
    this._stateObj = undefined;
    if (this._hass) this.hass = this._hass;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    const st = hass.states[this._config.entity];
    if (st === this._stateObj) return;
    this._stateObj = st;
    this._render();
  }

  getCardSize() {
    const n = this._stateObj?.attributes?.entries?.length ?? 3;
    return Math.max(3, Math.ceil(n * 1.2));
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (k) => k.startsWith("sensor.") && Array.isArray(hass.states[k].attributes?.entries) && "child" in hass.states[k].attributes
    );
    return { entity: entity || "" };
  }

  _onClick(ev) {
    const img = ev.composedPath().find((n) => n.tagName === "IMG" && n.dataset && n.dataset.zoom !== undefined);
    const box = this.shadowRoot.querySelector(".lightbox");
    if (img) {
      box.querySelector("img").src = img.src;
      box.hidden = false;
      return;
    }
    if (ev.composedPath().includes(box)) box.hidden = true;
  }

  _row(e) {
    const t = TYPES[e.type] || FALLBACK;
    const times = [fmtTime(e.time), fmtTime(e.end)].filter(Boolean).join(" - ");
    const sub = [times, e.detail].filter(Boolean).map(esc).join(" - ");
    const photos = Array.isArray(e.photos) ? e.photos : [];
    const photoHtml = photos.length
      ? `<div class="photos">${photos
          .map((src) => `<img loading="lazy" data-zoom src="${esc(src)}" alt="${esc(e.detail || "Diary photo")}">`)
          .join("")}</div>`
      : "";
    return `<div class="row ${photos.length ? "has-photos" : ""}" style="--c:${t.color}">
        <ha-icon icon="${t.icon}"></ha-icon>
        <div class="body">
          <div class="t">${esc(e.title || e.type)}</div>
          ${sub ? `<div class="s">${sub}</div>` : ""}
        </div>
        <div class="fig">${figure(e, t.color)}</div>
        ${photoHtml}
      </div>`;
  }

  _render() {
    const st = this._stateObj;
    const cfg = this._config;
    let body;
    let title = cfg.title;
    let date = "";

    if (!st || st.state === "unavailable" || st.state === "unknown") {
      body = `<div class="empty">Diary unavailable (${esc(cfg.entity)})</div>`;
    } else {
      const a = st.attributes;
      const entries = Array.isArray(a.entries) ? [...a.entries] : [];
      if (cfg.order === "desc") entries.reverse();
      if (title === undefined) title = a.child ? `${a.child.split(" ")[0]}'s diary` : "Nursery diary";
      date = fmtDate(a.date);
      body = entries.length ? entries.map((e) => this._row(e)).join("") : `<div class="empty">No diary entries yet today.</div>`;
    }

    const header = cfg.show_header
      ? `<div class="header"><div class="title">${esc(title || "")}</div><div class="date">${esc(date)}</div></div>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        ha-card { overflow: hidden; }
        .header { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; padding: 16px 16px 10px; }
        .header .title { font-size: 1.25em; font-weight: 700; }
        .header .date { color: var(--secondary-text-color); font-weight: 700; }
        .row { display: flex; flex-wrap: wrap; align-items: center; column-gap: 14px; padding: 12px 16px;
               border-top: 1px solid var(--divider-color); }
        .row ha-icon { --mdc-icon-size: 28px; color: var(--c); width: 36px; display: flex; justify-content: center; flex: 0 0 auto; }
        .body { flex: 1 1 0; min-width: 0; }
        .t { color: var(--c); font-weight: 700; font-size: 1.05em; line-height: 1.3; }
        .s { color: var(--secondary-text-color); font-size: 0.82em; margin-top: 2px; }
        .fig { flex: 0 0 auto; color: var(--c); font-weight: 700; font-size: 1.05em; text-align: right; white-space: nowrap; }
        .fig small { font-size: 0.6em; font-weight: 400; vertical-align: super; margin: 0 4px 0 2px; }
        .ring { width: 46px; height: 46px; display: block; }
        .ring text { font-size: 11px; font-weight: 700; font-family: inherit; }
        .ring .pc { font-size: 6px; font-weight: 400; }
        .photos { flex-basis: 100%; display: grid; grid-template-columns: repeat(${Number(cfg.photo_columns) || 1}, minmax(0, 1fr));
                  gap: 8px; margin: 10px 0 2px 50px; }
        .photos img { width: 100%; max-width: 460px; border-radius: 6px; border: 1px solid var(--divider-color);
                      padding: 3px; box-sizing: border-box; background: var(--card-background-color); cursor: zoom-in; display: block; }
        .empty { padding: 24px 16px; color: var(--secondary-text-color); text-align: center; border-top: 1px solid var(--divider-color); }
        .lightbox { position: fixed; inset: 0; z-index: 9999; background: rgba(0, 0, 0, 0.88); display: flex;
                    align-items: center; justify-content: center; cursor: zoom-out; }
        .lightbox[hidden] { display: none; }
        .lightbox img { max-width: 95vw; max-height: 92vh; border-radius: 6px; }
      </style>
      <ha-card>${header}${body}</ha-card>
      <div class="lightbox" hidden><img alt=""></div>`;
  }
}

if (!customElements.get("parentadmin-timeline-card")) {
  customElements.define("parentadmin-timeline-card", ParentAdminTimelineCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "parentadmin-timeline-card",
    name: "ParentAdmin timeline",
    description: "Nursery diary timeline with photos, laid out like the ParentAdmin website.",
  });
  console.info(`%c PARENTADMIN-TIMELINE-CARD %c ${CARD_VERSION} `, "background:#BD6A97;color:#fff", "");
}
