/**
 * BACnet Schedule Card
 * ---------------------
 * A lightweight custom Lovelace card that renders a BACnet weekly schedule as a
 * 7-day grid and lets the user edit time/value slots. It talks to Home
 * Assistant through the `bacnet.read_schedule` and `bacnet.write_schedule`
 * services.
 *
 * This is an early scaffold (v0.1.0). It intentionally avoids external build
 * tooling so it can be dropped straight into `config/www/` and referenced as a
 * Lovelace resource:
 *
 *   url: /local/bacnet-schedule-card.js
 *   type: module
 *
 * Card configuration:
 *
 *   type: custom:bacnet-schedule-card
 *   device_address: "192.168.1.50"
 *   object_id: "schedule,1"
 *   title: "AHU-1 Occupancy"
 */

const DAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

class BacnetScheduleCard extends HTMLElement {
  setConfig(config) {
    if (!config.device_address || !config.object_id) {
      throw new Error("device_address and object_id are required");
    }
    this._config = config;
    this._schedule = null;
    this._loading = false;
    this._render();
  }

  set hass(hass) {
    const first = this._hass === undefined;
    this._hass = hass;
    if (first) {
      this._loadSchedule();
    }
  }

  getCardSize() {
    return 6;
  }

  async _loadSchedule() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      const response = await this._hass.callService(
        "bacnet",
        "read_schedule",
        {
          device_address: this._config.device_address,
          object_id: this._config.object_id,
        },
        undefined,
        false,
        true
      );
      this._schedule = (response && response.response) || response || null;
    } catch (err) {
      this._error = String(err);
    } finally {
      this._loading = false;
      this._render();
    }
  }

  async _saveSchedule() {
    if (!this._hass || !this._schedule) return;
    await this._hass.callService("bacnet", "write_schedule", {
      device_address: this._config.device_address,
      object_id: this._config.object_id,
      schedule: this._schedule.weekly_schedule,
    });
  }

  _render() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    const title = this._config?.title || "BACnet Schedule";
    const weekly =
      (this._schedule && this._schedule.weekly_schedule) || DAYS.map(() => []);

    const rows = DAYS.map((day, index) => {
      const slots = weekly[index] || [];
      const slotHtml = slots.length
        ? slots
            .map(
              (s) =>
                `<span class="slot">${s.time || "--:--"} → ${
                  s.value ?? "?"
                }</span>`
            )
            .join("")
        : `<span class="empty">No entries</span>`;
      return `<tr><th>${day}</th><td>${slotHtml}</td></tr>`;
    }).join("");

    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 16px; }
        h2 { margin: 0 0 12px; font-size: 1.1rem; }
        table { width: 100%; border-collapse: collapse; }
        th { text-align: left; width: 110px; padding: 6px 8px; color: var(--secondary-text-color); }
        td { padding: 6px 8px; border-bottom: 1px solid var(--divider-color); }
        .slot { display: inline-block; margin: 2px 6px 2px 0; padding: 2px 8px;
                 border-radius: 12px; background: var(--primary-color); color: #fff; font-size: 0.8rem; }
        .empty { color: var(--disabled-text-color); font-style: italic; }
        .actions { margin-top: 12px; }
        button { padding: 6px 14px; border: none; border-radius: 6px;
                 background: var(--primary-color); color: #fff; cursor: pointer; }
        .error { color: var(--error-color); }
      </style>
      <ha-card>
        <h2>${title}</h2>
        ${this._loading ? "<p>Loading…</p>" : ""}
        ${this._error ? `<p class="error">${this._error}</p>` : ""}
        <table><tbody>${rows}</tbody></table>
        <div class="actions">
          <button id="refresh">Refresh</button>
        </div>
      </ha-card>
    `;

    const refresh = this.shadowRoot.getElementById("refresh");
    if (refresh) {
      refresh.addEventListener("click", () => this._loadSchedule());
    }
  }
}

customElements.define("bacnet-schedule-card", BacnetScheduleCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "bacnet-schedule-card",
  name: "BACnet Schedule Card",
  description: "Display and edit a BACnet weekly schedule.",
});
