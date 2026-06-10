/**
 * BACnet Schedule Card
 * ---------------------
 * An interactive, graphical weekly-schedule editor for BACnet `schedule`
 * objects, rendered as a grid:
 *
 *   - Columns  = the 7 days of the week
 *   - Rows     = the hours of the day (configurable resolution)
 *   - Cells    = colored by their state, using a soft pastel palette
 *
 * Interaction:
 *   - Left click (or click + drag) paints the currently selected state.
 *   - Right click opens a context menu (set a state, clear, delete the whole
 *     segment, fill the day, copy/paste a day...).
 *
 * It reads/writes through the `bacnet.read_schedule` / `bacnet.write_schedule`
 * services. No build tooling is required: drop this file into `config/www/` and
 * register it as a Lovelace resource:
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
 *   resolution: 30            # minutes per slot (15 / 30 / 60), default 30
 *   default_value: 0          # value used for "empty" slots
 *   states:                   # optional, overrides the default palette
 *     - { label: "Occupied",   value: 1, color: "#BFE3C0" }
 *     - { label: "Standby",    value: 2, color: "#FCE1B6" }
 *     - { label: "Unoccupied", value: 0, color: "#E3EAF2" }
 */

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const DAY_FULL = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

// A soft, pastel default palette used when the user does not provide states.
const DEFAULT_STATES = [
  { label: "Occupied", value: 1, color: "#BFE3C0" }, // mint green
  { label: "Standby", value: 2, color: "#FCE1B6" }, // peach
  { label: "Unoccupied", value: 0, color: "#E3EAF2" }, // pale blue-grey
];

// Extra pastel colors used to auto-assign a color to unknown values.
const PASTEL_FALLBACK = [
  "#AEDFF7",
  "#F8C8DC",
  "#D7C9F0",
  "#C6E7DC",
  "#FFF3B0",
  "#F7C9A6",
  "#C9D6F0",
  "#E6C9E0",
];

class BacnetScheduleCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._grid = null; // number[7][slots] of value
    this._states = DEFAULT_STATES;
    this._activeStateIndex = 0;
    this._painting = false;
    this._dirty = false;
    this._loading = false;
    this._error = null;
    this._clipboardDay = null;
    this._menu = null;
    this._onUp = () => {
      this._painting = false;
    };
  }

  setConfig(config) {
    // Do not throw when required fields are missing: the Lovelace card picker
    // instantiates the card with an empty config to render a preview, and a
    // hard throw there leaves the preview spinning forever. Instead we remember
    // that the card is not configured and render a friendly hint.
    config = config || {};
    this._configured = Boolean(config.device_address && config.object_id);
    this._config = {
      title: "BACnet Schedule",
      resolution: 30,
      default_value: 0,
      ...config,
    };
    if (![15, 30, 60].includes(Number(this._config.resolution))) {
      this._config.resolution = 30;
    }
    if (Array.isArray(config.states) && config.states.length) {
      this._states = config.states;
    }
    this._slots = (24 * 60) / Number(this._config.resolution);
    this._activeStateIndex = 0;
    this._grid = this._emptyGrid();
    if (this._configured) {
      this._renderShell();
      // Reload from the device when the target changed (e.g. another schedule
      // was picked in the visual editor) and hass is already available.
      if (this._hass && this._loadedKey !== this._targetKey()) {
        this._loadSchedule();
      }
    } else {
      this._renderUnconfigured();
    }
  }

  _targetKey() {
    return `${this._config.device_address}|${this._config.object_id}`;
  }

  static getStubConfig() {
    // Intentionally unconfigured: the add-card preview then shows the help
    // hint instead of firing read_schedule at a placeholder address (which
    // kept the preview "loading" until the request timed out).
    return {};
  }

  static getConfigElement() {
    // Visual editor with device -> schedule selectors.
    return document.createElement("bacnet-schedule-card-editor");
  }

  set hass(hass) {
    this._hass = hass;
    // First hass after setConfig: load the configured schedule once. The key
    // is set when a load starts, so a failed load does not retry on every
    // state change (use the refresh button instead).
    if (this._configured && this._loadedKey !== this._targetKey()) {
      this._loadSchedule();
    }
  }

  getCardSize() {
    return 10;
  }

  connectedCallback() {
    window.addEventListener("mouseup", this._onUp);
  }

  disconnectedCallback() {
    window.removeEventListener("mouseup", this._onUp);
    this._closeMenu();
  }

  // ---- model helpers -------------------------------------------------------

  _emptyGrid() {
    const def = Number(this._config.default_value);
    return Array.from({ length: 7 }, () =>
      Array.from({ length: this._slots }, () => def)
    );
  }

  _slotToTime(slot) {
    const minutes = slot * Number(this._config.resolution);
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  }

  _timeToSlot(time) {
    // Accepts "HH:MM" or "HH:MM:SS".
    const [h = "0", m = "0"] = String(time).split(":");
    const minutes = Number(h) * 60 + Number(m);
    return Math.floor(minutes / Number(this._config.resolution));
  }

  _stateForValue(value) {
    return this._states.find((s) => String(s.value) === String(value));
  }

  _colorForValue(value) {
    const state = this._stateForValue(value);
    if (state) return state.color;
    if (String(value) === String(this._config.default_value)) {
      return "transparent";
    }
    // Deterministically pick a fallback pastel for unknown numeric values.
    const idx = Math.abs(_hashCode(String(value))) % PASTEL_FALLBACK.length;
    return PASTEL_FALLBACK[idx];
  }

  _labelForValue(value) {
    const state = this._stateForValue(value);
    return state ? state.label : String(value);
  }

  // ---- BACnet <-> grid conversion -----------------------------------------

  _scheduleToGrid(weekly) {
    const grid = this._emptyGrid();
    if (!Array.isArray(weekly)) return grid;
    weekly.forEach((day, dayIndex) => {
      if (dayIndex > 6 || !Array.isArray(day)) return;
      const entries = day
        .map((e) => ({ slot: this._timeToSlot(e.time), value: e.value }))
        .sort((a, b) => a.slot - b.slot);
      let cursor = 0;
      let current = Number(this._config.default_value);
      for (const entry of entries) {
        const start = Math.max(0, Math.min(this._slots, entry.slot));
        for (let s = cursor; s < start; s++) grid[dayIndex][s] = current;
        // A null value is BACnet "no action" - render it as the default state.
        current =
          entry.value === null || entry.value === undefined
            ? Number(this._config.default_value)
            : entry.value;
        cursor = start;
      }
      for (let s = cursor; s < this._slots; s++) grid[dayIndex][s] = current;
    });
    return grid;
  }

  _gridToSchedule() {
    const def = Number(this._config.default_value);
    return this._grid.map((day) => {
      const entries = [];
      let previous = null;
      day.forEach((value, slot) => {
        if (slot === 0) {
          // Only emit a 00:00 entry when the day does not start at default.
          if (String(value) !== String(def)) {
            entries.push({ time: this._slotToTime(slot) + ":00", value });
          }
          previous = value;
          return;
        }
        if (String(value) !== String(previous)) {
          entries.push({ time: this._slotToTime(slot) + ":00", value });
          previous = value;
        }
      });
      return entries;
    });
  }

  // ---- service calls -------------------------------------------------------

  async _loadSchedule() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    this._loadedKey = this._targetKey();
    this._error = null;
    this._update();
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
      const data = (response && response.response) || response || {};
      if (data.weekly_schedule == null) {
        // The service replied but every property read failed: wrong object id
        // or the device did not answer.
        this._grid = this._emptyGrid();
        this._error =
          "No schedule data received - check the device address and object id";
      } else {
        this._grid = this._scheduleToGrid(data.weekly_schedule);
      }
      this._valueType = data.value_type || null;
      this._dirty = false;
    } catch (err) {
      this._error = String(err);
    } finally {
      this._loading = false;
      this._update();
    }
  }

  async _saveSchedule() {
    if (!this._hass) return;
    this._error = null;
    try {
      const payload = {
        device_address: this._config.device_address,
        object_id: this._config.object_id,
        schedule: this._gridToSchedule(),
      };
      // Prefer an explicit card config, then the type detected on read; when
      // neither is known the backend auto-detects from schedule-default.
      const valueType = this._config.value_type || this._valueType;
      if (valueType) payload.value_type = valueType;
      await this._hass.callService("bacnet", "write_schedule", payload);
      this._dirty = false;
      this._update();
    } catch (err) {
      this._error = String(err);
      this._update();
    }
  }

  // ---- painting ------------------------------------------------------------

  _paint(day, slot, value) {
    if (this._grid[day][slot] === value) return;
    this._grid[day][slot] = value;
    this._dirty = true;
    const cell = this.shadowRoot.querySelector(
      `.cell[data-day="${day}"][data-slot="${slot}"]`
    );
    if (cell) this._styleCell(cell, value);
    this._updateStatus();
  }

  _fillDay(day, value) {
    for (let s = 0; s < this._slots; s++) this._grid[day][s] = value;
    this._dirty = true;
    this._update();
  }

  _clearSegment(day, slot) {
    const target = this._grid[day][slot];
    let start = slot;
    let end = slot;
    while (start > 0 && this._grid[day][start - 1] === target) start--;
    while (end < this._slots - 1 && this._grid[day][end + 1] === target) end++;
    const def = Number(this._config.default_value);
    for (let s = start; s <= end; s++) this._grid[day][s] = def;
    this._dirty = true;
    this._update();
  }

  // ---- context menu --------------------------------------------------------

  _openMenu(x, y, day, slot) {
    this._closeMenu();
    const menu = document.createElement("div");
    menu.className = "ctx-menu";

    const header = document.createElement("div");
    header.className = "ctx-header";
    header.textContent = `${DAY_FULL[day]} · ${this._slotToTime(slot)}`;
    menu.appendChild(header);

    this._states.forEach((state, index) => {
      const item = document.createElement("button");
      item.className = "ctx-item";
      const dot = document.createElement("span");
      dot.className = "ctx-dot";
      dot.style.background = state.color;
      item.appendChild(dot);
      item.appendChild(document.createTextNode(`Set "${state.label}"`));
      item.addEventListener("click", () => {
        this._activeStateIndex = index;
        this._paint(day, slot, state.value);
        this._closeMenu();
        this._update();
      });
      menu.appendChild(item);
    });

    menu.appendChild(_separator());

    menu.appendChild(
      _menuButton("Clear this slot", () => {
        this._paint(day, slot, Number(this._config.default_value));
        this._closeMenu();
      })
    );
    menu.appendChild(
      _menuButton("Delete segment", () => {
        this._clearSegment(day, slot);
        this._closeMenu();
      })
    );
    menu.appendChild(
      _menuButton(`Fill ${DAY_FULL[day]} with active state`, () => {
        this._fillDay(day, this._states[this._activeStateIndex].value);
        this._closeMenu();
      })
    );

    menu.appendChild(_separator());

    menu.appendChild(
      _menuButton("Copy day", () => {
        this._clipboardDay = [...this._grid[day]];
        this._closeMenu();
        this._update();
      })
    );
    const paste = _menuButton("Paste day", () => {
      if (this._clipboardDay) {
        this._grid[day] = [...this._clipboardDay];
        this._dirty = true;
        this._update();
      }
      this._closeMenu();
    });
    if (!this._clipboardDay) paste.setAttribute("disabled", "");
    menu.appendChild(paste);

    this.shadowRoot.appendChild(menu);
    // Position within the card, keeping the menu inside the viewport width.
    const rect = this.getBoundingClientRect();
    const left = Math.min(x - rect.left, rect.width - 210);
    menu.style.left = `${Math.max(4, left)}px`;
    menu.style.top = `${y - rect.top}px`;
    this._menu = menu;

    setTimeout(() => {
      window.addEventListener("click", this._closeMenuOnce, { once: true });
    }, 0);
  }

  _closeMenu() {
    if (this._menu) {
      this._menu.remove();
      this._menu = null;
    }
  }

  get _closeMenuOnce() {
    if (!this.__closeMenuOnce) {
      this.__closeMenuOnce = () => this._closeMenu();
    }
    return this.__closeMenuOnce;
  }

  // ---- rendering -----------------------------------------------------------

  _styleCell(cell, value) {
    const color = this._colorForValue(value);
    cell.style.background = color === "transparent" ? "" : color;
    cell.classList.toggle("is-empty", color === "transparent");
    cell.title = this._labelForValue(value);
  }

  _renderUnconfigured() {
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="head"><h2>BACnet Schedule</h2></div>
        <div class="status info">
          Set <code>device_address</code> and <code>object_id</code> to edit a
          BACnet schedule, e.g.:
        </div>
        <pre class="hint-code">type: custom:bacnet-schedule-card
device_address: "192.168.0.99"
object_id: "schedule,1"</pre>
      </ha-card>
    `;
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="head">
          <h2 id="title"></h2>
          <div class="head-actions">
            <button id="refresh" class="btn ghost" title="Reload from device">↻</button>
            <button id="save" class="btn primary">Save</button>
          </div>
        </div>
        <div id="status" class="status"></div>
        <div id="palette" class="palette"></div>
        <div id="board" class="board"></div>
      </ha-card>
    `;
    this.shadowRoot.getElementById("title").textContent = this._config.title;
    this.shadowRoot
      .getElementById("refresh")
      .addEventListener("click", () => this._loadSchedule());
    this.shadowRoot
      .getElementById("save")
      .addEventListener("click", () => this._saveSchedule());
    this._renderPalette();
    this._renderBoard();
    this._updateStatus();
  }

  _renderPalette() {
    const palette = this.shadowRoot.getElementById("palette");
    if (!palette) return;
    palette.innerHTML = "";
    this._states.forEach((state, index) => {
      const swatch = document.createElement("button");
      swatch.className =
        "swatch" + (index === this._activeStateIndex ? " active" : "");
      swatch.innerHTML = `<span class="chip" style="background:${state.color}"></span>${state.label}`;
      swatch.addEventListener("click", () => {
        this._activeStateIndex = index;
        this._renderPalette();
      });
      palette.appendChild(swatch);
    });
    const hint = document.createElement("span");
    hint.className = "hint";
    hint.textContent = "Left-click/drag to paint · Right-click for options";
    palette.appendChild(hint);
  }

  _renderBoard() {
    const board = this.shadowRoot.getElementById("board");
    if (!board) return;
    board.innerHTML = "";

    // Header row: empty corner + day names.
    const corner = document.createElement("div");
    corner.className = "corner";
    board.appendChild(corner);
    DAYS.forEach((day, i) => {
      const head = document.createElement("div");
      head.className = "day-head";
      head.textContent = day;
      head.dataset.day = i;
      board.appendChild(head);
    });

    const perHour = 60 / Number(this._config.resolution);
    for (let slot = 0; slot < this._slots; slot++) {
      const isHour = slot % perHour === 0;
      const axis = document.createElement("div");
      axis.className = "hour" + (isHour ? " mark" : "");
      axis.textContent = isHour ? this._slotToTime(slot) : "";
      board.appendChild(axis);

      for (let day = 0; day < 7; day++) {
        const cell = document.createElement("div");
        cell.className = "cell" + (isHour ? " hour-line" : "");
        cell.dataset.day = day;
        cell.dataset.slot = slot;
        this._styleCell(cell, this._grid[day][slot]);

        cell.addEventListener("mousedown", (ev) => {
          if (ev.button !== 0) return;
          ev.preventDefault();
          this._painting = true;
          this._paint(day, slot, this._states[this._activeStateIndex].value);
        });
        cell.addEventListener("mouseenter", () => {
          if (this._painting) {
            this._paint(day, slot, this._states[this._activeStateIndex].value);
          }
        });
        cell.addEventListener("contextmenu", (ev) => {
          ev.preventDefault();
          this._openMenu(ev.clientX, ev.clientY, day, slot);
        });
        board.appendChild(cell);
      }
    }
  }

  _updateStatus() {
    const status = this.shadowRoot.getElementById("status");
    if (!status) return;
    if (this._loading) {
      status.textContent = "Loading…";
      status.className = "status info";
    } else if (this._error) {
      status.textContent = this._error;
      status.className = "status error";
    } else if (this._dirty) {
      status.textContent = "Unsaved changes";
      status.className = "status warn";
    } else {
      status.textContent = "In sync with device";
      status.className = "status ok";
    }
  }

  _update() {
    // Full refresh of the dynamic parts (board + palette + status).
    if (!this.shadowRoot.getElementById("board")) {
      this._renderShell();
      return;
    }
    this._renderPalette();
    this._renderBoard();
    this._updateStatus();
  }
}

// ---- small DOM helpers -----------------------------------------------------

function _separator() {
  const sep = document.createElement("div");
  sep.className = "ctx-sep";
  return sep;
}

function _menuButton(label, handler) {
  const btn = document.createElement("button");
  btn.className = "ctx-item";
  btn.textContent = label;
  btn.addEventListener("click", handler);
  return btn;
}

function _hashCode(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return hash;
}

const STYLE = `
  :host { display: block; }
  ha-card { padding: 16px; }
  .head { display: flex; align-items: center; justify-content: space-between; }
  h2 { margin: 0; font-size: 1.15rem; font-weight: 600; }
  .head-actions { display: flex; gap: 8px; }
  .btn {
    border: none; border-radius: 8px; padding: 6px 14px; cursor: pointer;
    font-size: 0.85rem; font-weight: 600;
  }
  .btn.primary { background: var(--primary-color, #03a9f4); color: #fff; }
  .btn.ghost {
    background: var(--secondary-background-color, #e8e8e8);
    color: var(--primary-text-color, #212121);
    font-size: 1rem; line-height: 1;
  }
  .status { font-size: 0.8rem; margin: 8px 0; min-height: 1em; }
  .status.ok { color: var(--success-color, #4caf50); }
  .status.warn { color: var(--warning-color, #ff9800); }
  .status.error { color: var(--error-color, #f44336); }
  .status.info { color: var(--secondary-text-color, #727272); }

  .palette { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 12px; }
  .swatch {
    display: inline-flex; align-items: center; gap: 6px;
    border: 1px solid var(--divider-color, #e0e0e0); border-radius: 18px;
    padding: 4px 12px 4px 6px; background: var(--card-background-color, #fff);
    cursor: pointer; font-size: 0.8rem; color: var(--primary-text-color, #212121);
    transition: box-shadow 0.15s, border-color 0.15s;
  }
  .swatch.active {
    border-color: var(--primary-color, #03a9f4);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary-color, #03a9f4) 30%, transparent);
  }
  .swatch .chip { width: 16px; height: 16px; border-radius: 50%; border: 1px solid rgba(0,0,0,0.12); }
  .hint { font-size: 0.72rem; color: var(--secondary-text-color, #888); margin-left: auto; }

  .board {
    position: relative;
    display: grid;
    grid-template-columns: 52px repeat(7, 1fr);
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 10px; overflow: hidden;
    user-select: none;
  }
  .corner { background: var(--secondary-background-color, #f5f5f5); }
  .day-head {
    background: var(--secondary-background-color, #f5f5f5);
    text-align: center; font-size: 0.78rem; font-weight: 700;
    padding: 6px 0; color: var(--primary-text-color, #212121);
    border-left: 1px solid var(--divider-color, #e0e0e0);
  }
  .hour {
    font-size: 0.68rem; color: var(--secondary-text-color, #999);
    text-align: right; padding-right: 6px; height: 14px; line-height: 14px;
    background: var(--secondary-background-color, #fafafa);
  }
  .hour.mark { color: var(--primary-text-color, #555); font-weight: 600; }
  .cell {
    height: 14px; border-left: 1px solid var(--divider-color, #eee);
    cursor: crosshair;
  }
  .cell.hour-line { border-top: 1px solid var(--divider-color, #e0e0e0); }
  .cell.is-empty {
    background-image: linear-gradient(45deg,
      var(--secondary-background-color, #fafafa) 25%, transparent 25%,
      transparent 50%, var(--secondary-background-color, #fafafa) 50%,
      var(--secondary-background-color, #fafafa) 75%, transparent 75%);
    background-size: 8px 8px;
  }
  .cell:hover { outline: 1px solid var(--primary-color, #03a9f4); outline-offset: -1px; }

  .ctx-menu {
    position: absolute; z-index: 20; min-width: 200px;
    background: var(--card-background-color, #fff);
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.18);
    padding: 6px; display: flex; flex-direction: column;
  }
  .ctx-header {
    font-size: 0.72rem; font-weight: 700; padding: 4px 8px 8px;
    color: var(--secondary-text-color, #888);
  }
  .ctx-item {
    display: flex; align-items: center; gap: 8px;
    border: none; background: transparent; cursor: pointer;
    padding: 7px 8px; border-radius: 6px; font-size: 0.83rem; text-align: left;
    color: var(--primary-text-color, #212121);
  }
  .hint-code {
    margin: 8px 0 0; padding: 10px 12px; border-radius: 8px;
    background: var(--secondary-background-color, #f5f5f5);
    color: var(--primary-text-color, #212121);
    font-size: 0.78rem; white-space: pre-wrap; overflow-x: auto;
  }
`;

// Guard against double definition (the versioned ?v= URL may load the module
// more than once); defining a custom element twice throws and would break the
// card. Only register the picker entry on first load too.
if (!customElements.get("bacnet-schedule-card")) {
  customElements.define("bacnet-schedule-card", BacnetScheduleCard);

  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "bacnet-schedule-card",
    name: "BACnet Schedule Card",
    description:
      "Graphical weekly-schedule editor for BACnet schedule objects (days × hours grid, pastel states, right-click actions).",
    preview: false,
    documentationURL: "https://github.com/Morrine74/ha-bacnet",
  });
}

// ---------------------------------------------------------------------------
// Visual editor: pick a BACnet device, then one of its schedules.
// ---------------------------------------------------------------------------

class BacnetScheduleCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  /** Collect schedule entities exposed by the BACnet integration. */
  _schedules() {
    if (!this._hass) return [];
    const result = [];
    for (const [entityId, state] of Object.entries(this._hass.states)) {
      const attrs = state.attributes || {};
      if (attrs.object_type !== "schedule" || !attrs.device_address) continue;
      result.push({
        entityId,
        address: attrs.device_address,
        deviceId: attrs.device_id,
        objectId: attrs.object_id,
        name: attrs.friendly_name || entityId,
      });
    }
    return result;
  }

  _devices(schedules) {
    const map = new Map();
    for (const s of schedules) {
      if (!map.has(s.address)) {
        map.set(s.address, {
          address: s.address,
          deviceId: s.deviceId,
          label: `Device ${s.deviceId ?? "?"} (${s.address})`,
        });
      }
    }
    return [...map.values()];
  }

  _emit(patch) {
    this._config = { ...this._config, ...patch };
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      })
    );
    this._render();
  }

  _render() {
    const schedules = this._schedules();
    const devices = this._devices(schedules);
    const selectedAddress = this._config.device_address || "";
    const selectedObject = this._config.object_id || "";
    const daySchedules = schedules.filter(
      (s) => s.address === selectedAddress
    );

    const manualHint = devices.length
      ? ""
      : `<div class="ed-note">No schedule entities found yet. Add some
         schedule points to the BACnet integration first, or fill the fields
         manually below.</div>`;

    this.shadowRoot.innerHTML = `
      <style>
        .ed { display: flex; flex-direction: column; gap: 12px; padding: 4px 0; }
        label { font-size: 0.8rem; color: var(--secondary-text-color, #666); display: block; margin-bottom: 4px; }
        select, input { width: 100%; box-sizing: border-box; padding: 8px;
          border: 1px solid var(--divider-color, #ccc); border-radius: 6px;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #212121); font-size: 0.9rem; }
        .ed-note { font-size: 0.78rem; color: var(--warning-color, #b8860b);
          background: var(--secondary-background-color, #faf7ec);
          padding: 8px 10px; border-radius: 6px; }
        .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
      </style>
      <div class="ed">
        ${manualHint}
        <div>
          <label>Device</label>
          <select id="device">
            <option value="">— Select a device —</option>
            ${devices
              .map(
                (d) =>
                  `<option value="${d.address}" ${
                    d.address === selectedAddress ? "selected" : ""
                  }>${d.label}</option>`
              )
              .join("")}
          </select>
        </div>
        <div>
          <label>Schedule</label>
          <select id="schedule" ${selectedAddress ? "" : "disabled"}>
            <option value="">— Select a schedule —</option>
            ${daySchedules
              .map(
                (s) =>
                  `<option value="${s.objectId}" ${
                    s.objectId === selectedObject ? "selected" : ""
                  }>${s.name} [${s.objectId}]</option>`
              )
              .join("")}
          </select>
        </div>
        <div>
          <label>Title</label>
          <input id="title" type="text" value="${
            this._config.title || ""
          }" placeholder="BACnet Schedule" />
        </div>
        <div class="row2">
          <div>
            <label>Resolution (min)</label>
            <select id="resolution">
              ${[15, 30, 60]
                .map(
                  (r) =>
                    `<option value="${r}" ${
                      Number(this._config.resolution || 30) === r
                        ? "selected"
                        : ""
                    }>${r}</option>`
                )
                .join("")}
            </select>
          </div>
          <div>
            <label>Value type (optional)</label>
            <select id="value_type">
              ${["", "real", "unsigned", "integer", "boolean", "enumerated"]
                .map(
                  (t) =>
                    `<option value="${t}" ${
                      (this._config.value_type || "") === t ? "selected" : ""
                    }>${t || "auto"}</option>`
                )
                .join("")}
            </select>
          </div>
        </div>
      </div>
    `;

    const deviceSel = this.shadowRoot.getElementById("device");
    const schedSel = this.shadowRoot.getElementById("schedule");
    const titleInput = this.shadowRoot.getElementById("title");
    const resSel = this.shadowRoot.getElementById("resolution");
    const vtSel = this.shadowRoot.getElementById("value_type");

    deviceSel.addEventListener("change", () => {
      // Reset schedule when the device changes.
      this._emit({ device_address: deviceSel.value, object_id: "" });
    });
    schedSel.addEventListener("change", () => {
      const chosen = daySchedules.find((s) => s.objectId === schedSel.value);
      this._emit({
        object_id: schedSel.value,
        title:
          this._config.title || (chosen ? chosen.name : "BACnet Schedule"),
      });
    });
    titleInput.addEventListener("change", () =>
      this._emit({ title: titleInput.value })
    );
    resSel.addEventListener("change", () =>
      this._emit({ resolution: Number(resSel.value) })
    );
    vtSel.addEventListener("change", () => {
      const patch = { value_type: vtSel.value };
      if (!vtSel.value) delete patch.value_type;
      this._emit(patch);
    });
  }
}

if (!customElements.get("bacnet-schedule-card-editor")) {
  customElements.define(
    "bacnet-schedule-card-editor",
    BacnetScheduleCardEditor
  );
}

