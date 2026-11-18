/**
 * BACnet Heating Circuit Card
 * ---------------------------
 * A live view of one heating (or heating/cooling) circuit, built from the
 * entities of a single BACnet installation ("Circuit de chauffage" sub-device
 * created by the integration from the Siemens plant tree):
 *
 *   - a hydraulic synoptic: supply / return pipes, mixing valve, pump(s),
 *     supply / return temperatures and the current supply setpoint;
 *   - the heating curve, drawn from its base / inflexion / high points, with
 *     the current operating point; a point is edited by clicking it;
 *   - the operating mode, room setpoints and heating limits, writable in a
 *     two-step dialog (enter, then confirm) so nothing is written by accident;
 *   - every remaining point of the installation under "Other points".
 *
 * Point recognition follows the Siemens ABT libraries (HtgCr21x/22x,
 * HCcr21x/22x): the language-independent short name first (last segment of the
 * BACnet object-name, e.g. `...'HCrv'TOaDsgn`), the friendly label as a
 * fallback. Anything can be forced with the `points` option.
 *
 * Card configuration:
 *
 *   type: custom:bacnet-heating-circuit-card
 *   device: 1f0c...                # HA device id of the installation
 *   title: "Circuit radiateurs"    # optional, defaults to the device name
 *   outside_temp: sensor.t_ext     # optional, auto-detected otherwise
 *   sections: [synoptic, curve, settings, others]   # optional
 *   points:                        # optional role -> entity overrides
 *     tFl: sensor.depart
 *     valve: number.vanne
 */

const HC_SECTIONS = ["synoptic", "curve", "settings", "others"];

const HC_I18N = {
  fr: {
    title: "Circuit de chauffage",
    hint: "Choisissez l'installation (appareil BACnet) du circuit à afficher, par exemple :",
    noPoints: "Aucune entité BACnet trouvée pour cet appareil.",
    hydraulic: "Circuit hydraulique",
    emitters: "ÉMETTEURS",
    supply: "DÉPART",
    ret: "RETOUR",
    setpoint: "Cons.",
    valve: "Vanne",
    pump: "Pompe",
    on: "Marche",
    off: "Arrêt",
    fault: "Défaut",
    twinFault: "Défaut pompe jumelée",
    plant: "Installation",
    mode: "Régime",
    outside: "T° ext.",
    safety: "Sécurité",
    cooling: "Rafraîchissement",
    heating: "Chauffage",
    operation: "Fonctionnement de l'installation",
    room: "Consignes d'ambiance",
    limits: "Températures de non-chauffe",
    devices: "Pompes et vanne",
    curve: "Courbe de chauffe",
    curveSettings: "Réglages de la courbe",
    curveNone: "Courbe non disponible sur cette installation.",
    others: "Autres points",
    base: "Base",
    bp: "Inflexion",
    hi: "Haute",
    point: "Point",
    min: "Min",
    max: "Max",
    xAxis: "T° extérieure (°C)",
    yAxis: "T° départ (°C)",
    xField: "T° extérieure",
    yField: "T° départ",
    curvePoint: "Point de la courbe",
    current: "Valeur actuelle",
    newValue: "Nouvelle valeur",
    next: "Suivant",
    back: "Retour",
    cancel: "Annuler",
    write: "Écrire",
    history: "Historique",
    confirm: "Confirmer l'écriture sur l'automate :",
    written: "Écrit.",
    invalid: "Valeur invalide.",
    unchanged: "Aucune modification.",
    readOnly: "lecture seule",
    edDevice: "Installation (appareil)",
    edPick: "— Choisir une installation —",
    edTitle: "Titre",
    edOutside: "Entité de température extérieure (optionnel)",
    edSections: "Sections affichées",
    edNone: "Aucun appareil BACnet trouvé. Ajoutez d'abord des points à l'intégration BACnet.",
    secSynoptic: "Synoptique",
    secCurve: "Courbe de chauffe",
    secSettings: "Réglages",
    secOthers: "Autres points",
  },
  en: {
    title: "Heating circuit",
    hint: "Pick the installation (BACnet device) of the circuit to display, for example:",
    noPoints: "No BACnet entity found for this device.",
    hydraulic: "Hydraulic circuit",
    emitters: "EMITTERS",
    supply: "SUPPLY",
    ret: "RETURN",
    setpoint: "Setp.",
    valve: "Valve",
    pump: "Pump",
    on: "On",
    off: "Off",
    fault: "Fault",
    twinFault: "Twin pump fault",
    plant: "Plant",
    mode: "Mode",
    outside: "Outside",
    safety: "Safety",
    cooling: "Cooling",
    heating: "Heating",
    operation: "Plant operation",
    room: "Room setpoints",
    limits: "Heating limits",
    devices: "Pumps and valve",
    curve: "Heating curve",
    curveSettings: "Curve settings",
    curveNone: "No heating curve on this installation.",
    others: "Other points",
    base: "Base",
    bp: "Inflexion",
    hi: "High",
    point: "Point",
    min: "Min",
    max: "Max",
    xAxis: "Outside temperature (°C)",
    yAxis: "Supply temperature (°C)",
    xField: "Outside temperature",
    yField: "Supply temperature",
    curvePoint: "Curve point",
    current: "Current value",
    newValue: "New value",
    next: "Next",
    back: "Back",
    cancel: "Cancel",
    write: "Write",
    history: "History",
    confirm: "Confirm the write to the controller:",
    written: "Written.",
    invalid: "Invalid value.",
    unchanged: "Nothing to change.",
    readOnly: "read only",
    edDevice: "Installation (device)",
    edPick: "— Select an installation —",
    edTitle: "Title",
    edOutside: "Outside temperature entity (optional)",
    edSections: "Displayed sections",
    edNone: "No BACnet device found. Add points to the BACnet integration first.",
    secSynoptic: "Synoptic",
    secCurve: "Heating curve",
    secSettings: "Settings",
    secOthers: "Other points",
  },
};

// Role -> Siemens short names, then label patterns (matched on the accent-less,
// lower-cased friendly name). Short names win; labels only rescue points whose
// short name is unknown, so a project in another language still binds.
const HC_ROLES = {
  tFl: { sn: ["TFl"], re: /^temperature de depart$/ },
  tRt: { sn: ["TRt"], re: /^temperature (au|de) retour$/ },
  spTFl: { sn: ["PrSpTFl"], re: /^consigne temp\. depart actuelle/ },
  sfty: { sn: ["SftyTLm"], re: /thermostat limiteur de securite/ },
  ovr: { sn: ["OvrTDet"] },
  hc: { sn: ["HCSta"], re: /^etat chaud\/froid$/ },
  tOa: { sn: ["TOaEff", "TOa"], re: /^temperature exterieure( effective)?$/ },
  twnFlt: { sn: ["TwnPuFlt"], re: /defaut pompe jumelee/ },
  opModMan: { sn: ["OpModMan"], re: /selection manu mode fonct|mode de fonctionnement manuel/ },
  prOpMod: { sn: ["PrOpMod"], re: /mode de fonctionnement actuel|regime actuel/ },
  rsn: { sn: ["RsnPrOpMod"], re: /raison du mode de fonctionnement/ },
  frPrt: { sn: ["FrPrt"] },
  pltSta: { sn: ["PltSta"], re: /^etat d'installation$/ },
  sched: { sn: ["Sched"], re: /^(programme horaire|ph)$/ },
  spSet: { sn: ["SpTFl"], re: /^consigne de temperature de depart$/ },
  spH: { sn: ["SpTFlH"] },
  spC: { sn: ["SpTFlC"] },
  spRdc: { sn: ["SpRdc"] },
  hReq: { sn: ["HReq"] },
  cReq: { sn: ["CReq"] },
  hwDmd: { sn: ["HwDmd"] },
  chwDmd: { sn: ["ChwDmd"] },
  limCmf: { sn: ["HtgLm", "SpHLimCmf"], re: /limite de chauffe.*confort/ },
  limEco: { sn: ["HtgLmEco", "SpHLimEco"], re: /limite de chauffe.*eco/ },
  spCmf: { sn: ["SpHCmf", "SpCmf"], re: /^consigne de confort$/ },
  spPcf: { sn: ["DSpHPcf", "DSpPcf", "SpHPcf"], re: /pre.?confort/ },
  spEco: { sn: ["SpHEco", "SpEco"], re: /consigne economie/ },
  spPrt: { sn: ["SpPrt", "SpHPrt"] },
  spCCmf: { sn: ["SpCCmf"] },
  spCPcf: { sn: ["DSpCPcf"] },
  spCEco: { sn: ["SpCEco"] },
  xBase: { sn: ["TOaDsgn", "TOa1HCrv"], re: /^temperature exterieure de base$/ },
  yBase: { sn: ["SpTFlDs", "SpTFl1HCrv"], re: /cons\.temp\.dep pour temp ext\. reference/ },
  xBp: { sn: ["TOaBp"], re: /temp\. exterieure au point d'inflexion/ },
  yBp: { sn: ["SpTFlBp"], re: /depart au point d'inflexion/ },
  xHi: { sn: ["TOaHi", "TOa2HCrv"], re: /^temperature exterieure haute$/ },
  yHi: { sn: ["SpTFlHi", "SpTFl2HCrv"], re: /depart pour temp ext\. elevee/ },
  yMax: { sn: ["SpTFlMax"], re: /consigne maximum temperature depart/ },
  yMin: { sn: ["SpTFlMin"], re: /consigne minimum temperature depart/ },
  expRad: { sn: ["ExpRad"], re: /exposant radiateur/ },
  tOaBase: { sn: ["TOaBase"], re: /point de base pour t.ext/ },
  spTR: { sn: ["SpTR"], re: /^consigne de temperature ambiante$/ },
};

const HC_KNOWN_SN = new Set(
  ["Pos", "VlvPos", "Cmd", "Flt", "Fb", "FbPos"].concat(
    ...Object.values(HC_ROLES).map((r) => r.sn)
  )
);

const HC_OFF_RE =
  /^(off|0|false|inactive|inactif|arr[eê]t|aus|stop|ferm[ée]e?|closed)$/i;
const HC_NORMAL_RE =
  /^(off|0|false|normal|ok|inactive|inactif|aucun|none|no|non)$/i;
const HC_COOL_RE = /froid|refroid|rafra|cool|k[uü]hl/i;
const HC_WRITABLE = ["number", "input_number", "select", "input_select", "switch", "input_boolean"];

function hcEsc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function hcNorm(text) {
  return String(text || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[‘’]/g, "'")
    .toLowerCase()
    .trim();
}

class BacnetHeatingCircuitCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._signature = null;
    this._dlg = null;
    this._note = null;
    this._openOthers = false;
    this._onKey = (ev) => {
      if (!this._dlg) return;
      if (ev.key === "Escape") this._closeDialog();
      // Enter on a focused button already clicks it: advancing here as well
      // would jump straight from the entry step to the write.
      const target = ev.composedPath()[0];
      const onButton = target instanceof Element && target.tagName === "BUTTON";
      if (ev.key === "Enter" && !onButton) this._dialogAdvance();
    };
  }

  // ---- Lovelace API --------------------------------------------------------

  setConfig(config) {
    // Never throw on an incomplete config: the card picker instantiates the
    // card with a stub and a throw leaves its preview spinning.
    this._config = { ...(config || {}) };
    const wanted = Array.isArray(this._config.sections)
      ? this._config.sections.filter((s) => HC_SECTIONS.includes(s))
      : [];
    this._sections = wanted.length ? wanted : HC_SECTIONS;
    this._signature = null;
    this._entityIds = null;
    this._renderShell();
    this._refresh();
  }

  set hass(hass) {
    this._hass = hass;
    this._refresh();
  }

  getCardSize() {
    return 9;
  }

  static getConfigElement() {
    return document.createElement("bacnet-heating-circuit-card-editor");
  }

  static getStubConfig(hass) {
    const devices = hcBacnetDevices(hass);
    const circuit = devices.find((d) => /circuit|chauff|heiz|heat/i.test(d.name));
    return circuit ? { device: circuit.id } : {};
  }

  connectedCallback() {
    window.addEventListener("keydown", this._onKey);
  }

  disconnectedCallback() {
    window.removeEventListener("keydown", this._onKey);
  }

  // ---- helpers -------------------------------------------------------------

  _t(key) {
    const lang = String((this._hass && this._hass.language) || "en").slice(0, 2);
    return (HC_I18N[lang] || HC_I18N.en)[key] || HC_I18N.en[key] || key;
  }

  _fmtNum(value, digits) {
    const lang = (this._hass && this._hass.language) || "en";
    try {
      return new Intl.NumberFormat(lang, {
        maximumFractionDigits: digits == null ? 1 : digits,
      }).format(value);
    } catch (err) {
      return String(Math.round(value * 10) / 10);
    }
  }

  /** Entity ids of the configured installation (cached per registry object). */
  _deviceEntityIds() {
    const hass = this._hass;
    if (this._entityIds && this._entitiesRef === hass.entities) {
      return this._entityIds;
    }
    const ids = [];
    for (const entry of Object.values(hass.entities || {})) {
      if (entry.device_id === this._config.device) ids.push(entry.entity_id);
    }
    this._entitiesRef = hass.entities;
    this._entityIds = ids;
    this._outsideAuto = undefined;
    return ids;
  }

  /** Outside temperature lives at site level, outside the circuit's device. */
  _outsideEntityId(address) {
    if (this._config.outside_temp) return this._config.outside_temp;
    if (this._outsideAuto !== undefined) return this._outsideAuto;
    let found = null;
    const role = HC_ROLES.tOa;
    for (const [entityId, st] of Object.entries(this._hass.states)) {
      const a = st.attributes || {};
      if (!a.object_id || (address && a.device_address !== address)) continue;
      const sn = String(a.object_name || "").split("'").pop();
      const path = a.bacnet_path || [];
      const leaf = hcNorm(path.length ? path[path.length - 1] : a.friendly_name);
      if (role.sn.includes(sn) || role.re.test(leaf)) {
        found = entityId;
        if (sn === "TOaEff") break;
      }
    }
    this._outsideAuto = found;
    return found;
  }

  _point(entityId) {
    const st = this._hass.states[entityId];
    if (!st) return null;
    const a = st.attributes || {};
    const path = Array.isArray(a.bacnet_path) ? a.bacnet_path : [];
    const leaf = path.length ? path[path.length - 1] : a.friendly_name || entityId;
    const parent = path.length > 1 ? path[path.length - 2] : "";
    const chain = a.object_name ? String(a.object_name).split("'") : [];
    let sn = chain.length ? chain[chain.length - 1] : null;
    const psn = chain.length > 1 ? chain[chain.length - 2] : "";
    // Twin devices index their points: `Cmd(1)` / "Commande (1)".
    let idx = null;
    const m = /\((\d+)\)\s*$/.exec(sn || leaf);
    if (m) {
      idx = Number(m[1]);
      if (sn) sn = sn.replace(/\(\d+\)\s*$/, "");
    }
    // Heating/cooling circuits double some points: `PrSpTFl(H)` / `(C)`.
    let mode = null;
    const tag = /\((H|C|Chauffage|Froid)\)\s*$/i.exec(sn || leaf);
    if (tag) {
      mode = /^(c|froid)$/i.test(tag[1]) ? "cold" : "hot";
      if (sn) sn = sn.replace(/\([A-Za-z]+\)\s*$/, "");
    }
    const eqIdx = a.equipment ? path.indexOf(a.equipment) : -1;
    const domain = entityId.split(".")[0];
    const avail = st.state !== "unavailable" && st.state !== "unknown";
    const n = avail ? Number(st.state) : NaN;
    return {
      id: entityId,
      st,
      a,
      domain,
      leaf,
      norm: hcNorm(leaf),
      parent,
      pnorm: hcNorm(parent),
      group: path.slice(eqIdx + 1, -1).join(" · "),
      // Where the point hangs in the plant: tells two heating curves apart.
      branch: path.length ? path.slice(0, -1).join(" · ") : chain.slice(0, -1).join(" · "),
      // Short names of the two levels above (`SplyChw Hcrv`): language-free.
      branchSn: chain.slice(-3, -1).join(" "),
      mode,
      sn,
      psn,
      idx,
      avail,
      val: avail && st.state !== "" && Number.isFinite(n) ? n : null,
      unit: a.unit_of_measurement || "",
      writable: HC_WRITABLE.includes(domain),
      used: false,
    };
  }

  _dis(p) {
    if (!p) return "";
    if (!p.avail) return "—";
    const state = p.st.state;
    if (state === "on" || state === "off") {
      const text = state === "on" ? p.a.active_text : p.a.inactive_text;
      if (text) return String(text);
      return this._t(state);
    }
    if (p.val != null) {
      const digits = p.unit ? 1 : 2;
      return this._fmtNum(p.val, digits) + (p.unit ? " " + p.unit : "");
    }
    return String(state);
  }

  _isOn(p) {
    if (!p || !p.avail) return false;
    if (p.val != null) return p.val !== 0;
    return !HC_OFF_RE.test(p.st.state);
  }

  _isAlarm(p) {
    if (!p || !p.avail) return false;
    if (p.val != null) return p.val !== 0;
    return !HC_NORMAL_RE.test(p.st.state);
  }

  // ---- classification ------------------------------------------------------

  _classify() {
    const overrides = this._config.points || {};
    const pts = this._deviceEntityIds()
      .map((id) => this._point(id))
      .filter(Boolean);
    const forced = {};
    for (const [role, entityId] of Object.entries(overrides)) {
      let p = pts.find((x) => x.id === entityId);
      if (!p) p = this._point(entityId);
      if (p) {
        p.used = true;
        forced[role] = p;
      }
    }
    const find = (pred) => {
      const p = pts.find((x) => !x.used && pred(x));
      if (p) p.used = true;
      return p || null;
    };
    const role = (key, extra) => {
      if (forced[key]) return forced[key];
      const def = HC_ROLES[key];
      const ok = extra || (() => true);
      return (
        find((p) => def.sn.includes(p.sn) && ok(p)) ||
        (def.re
          ? find((p) => !HC_KNOWN_SN.has(p.sn) && def.re.test(p.norm) && ok(p))
          : null)
      );
    };
    const isSensor = (p) => !p.writable && p.val != null;
    const notSetpoint = (p) =>
      !/consigne|regulateur|setpoint|\bmax|\bmin|limit/.test(p.norm);
    const hydFirst = (p) => /hydraul/.test(p.pnorm);

    const syn = {};
    syn.tFl =
      role("tFl", hydFirst) ||
      role("tFl") ||
      find((p) => isSensor(p) && !HC_KNOWN_SN.has(p.sn) && notSetpoint(p) &&
        /temp.*depart|depart.*temp|supply temp|flow temp|vorlauftemp/.test(p.norm));
    syn.tRt =
      role("tRt", hydFirst) ||
      role("tRt") ||
      find((p) => isSensor(p) && !HC_KNOWN_SN.has(p.sn) && notSetpoint(p) &&
        /temp.*retour|retour.*temp|return temp|rucklauftemp/.test(p.norm));
    syn.hc = role("hc");
    while (!forced.hc && find((p) => p.sn === "HCSta"));
    syn.cool = !!(syn.hc && syn.hc.avail && HC_COOL_RE.test(this._dis(syn.hc)));
    // PrSpTFl also exists on the root and on each curve: keep the hydraulic
    // circuit's one (of the current heating/cooling state when it is doubled)
    // and absorb the duplicates.
    const nowMode = (p) => p.mode === (syn.cool ? "cold" : "hot");
    syn.spTFl =
      role("spTFl", (p) => hydFirst(p) && nowMode(p)) ||
      role("spTFl", (p) => hydFirst(p) && !p.mode) ||
      role("spTFl", (p) => !p.mode && !/courbe|curve|hcrv/i.test(p.branch + p.psn)) ||
      role("spTFl", nowMode) ||
      role("spTFl");
    while (!forced.spTFl && syn.spTFl && find((p) => p.sn === "PrSpTFl" ||
      (!HC_KNOWN_SN.has(p.sn) && HC_ROLES.spTFl.re.test(p.norm))));
    const valveParent = (p) =>
      /^Vlv/.test(p.psn) || /vanne|valve|ventil/.test(p.pnorm);
    syn.valve =
      forced.valve ||
      find((p) => p.sn === "Pos" && valveParent(p)) ||
      find((p) => p.sn === "VlvPos") ||
      find((p) => !HC_KNOWN_SN.has(p.sn) && /^position/.test(p.norm) &&
        (valveParent(p) || /vanne|valve/.test(p.norm)));
    syn.sfty = role("sfty");
    syn.ovr = role("ovr");
    syn.tOa = role("tOa");
    if (!syn.tOa) {
      const address = pts.length ? pts[0].a.device_address : null;
      const outside = this._outsideEntityId(address);
      syn.tOa = outside ? this._point(outside) : null;
    }
    syn.twnFlt = role("twnFlt");

    // Pumps: one command per pump device, or an indexed pair in a twin device.
    const pumpParent = (p) =>
      /^(Twn)?Pu\d*$/.test(p.psn) || /pompe|pump/.test(p.pnorm);
    const isCmd = (p) =>
      p.sn === "Cmd" || (!HC_KNOWN_SN.has(p.sn) && /^commande|^command/.test(p.norm));
    const isFlt = (p) =>
      p.sn === "Flt" || (!HC_KNOWN_SN.has(p.sn) && /^defaut|^fault/.test(p.norm));
    let cmds = [];
    for (let p; (p = find((x) => isCmd(x) && pumpParent(x))); ) cmds.push(p);
    if (!cmds.length) {
      for (let p; (p = find((x) => isCmd(x) && x.idx != null &&
        /pompe|pump/.test(x.norm + " " + x.pnorm))); ) cmds.push(p);
    }
    for (const key of ["cmd1", "cmd2"]) {
      if (forced[key] && !cmds.includes(forced[key])) cmds.push(forced[key]);
    }
    const pumps = cmds.map((cmd) => {
      const same = (p) =>
        p.parent === cmd.parent && p.psn === cmd.psn &&
        (cmd.idx == null || p.idx == null || p.idx === cmd.idx);
      const tail = /(\d+)\s*$/.exec(cmd.parent);
      return {
        n: cmd.idx != null ? cmd.idx : tail ? Number(tail[1]) : null,
        cmd,
        flt: find((p) => isFlt(p) && same(p)),
        fb: find((p) => p.sn === "Fb" && same(p)),
      };
    });
    pumps.sort((a, b) => (a.n == null ? 99 : a.n) - (b.n == null ? 99 : b.n));
    pumps.forEach((pu, i) => {
      if (pu.n == null) pu.n = i + 1;
      pu.on = this._isOn(pu.cmd);
      pu.fault = this._isAlarm(pu.flt);
    });
    syn.pumps = pumps.slice(0, 2);

    const list = (title, rows) => ({ title, rows: rows.filter(Boolean) });
    const pltSta = role("pltSta");
    const prOpMod = role("prOpMod");
    const lists = [];
    // "Position" / "Commande (1)" mean nothing without their device: these
    // rows carry the parent name ("Vanne · Position").
    const deviceRows = [syn.valve];
    pumps.forEach((pu) => deviceRows.push(pu.cmd, pu.flt, pu.fb));
    deviceRows.filter(Boolean).forEach((p) => (p.ctx = true));
    deviceRows.push(syn.twnFlt, syn.sfty, syn.ovr);
    lists.push(list(this._t("devices"), deviceRows));
    lists.push(
      list(this._t("operation"), [
        role("opModMan"), prOpMod, role("rsn"), role("frPrt"), role("sched"),
        role("spSet"), role(syn.cool ? "spC" : "spH"), role(syn.cool ? "spH" : "spC"),
        role("spRdc"), role("hReq"), role("cReq"), role("hwDmd"), role("chwDmd"),
      ])
    );
    lists.push(
      list(this._t("room"), [
        role("spCmf"), role("spPcf"), role("spEco"), role("spPrt"),
        role("spCCmf"), role("spCPcf"), role("spCEco"),
      ])
    );
    lists.push(list(this._t("limits"), [role("limCmf"), role("limEco")]));

    // A heating/cooling circuit carries one curve per supply chain (hot
    // water, chilled water) with the very same point names: the points of a
    // curve are those hanging under the same parent, never a mix of both.
    const curveKeys = ["xBase", "yBase", "xBp", "yBp", "xHi", "yHi", "yMax",
      "yMin", "expRad", "tOaBase", "spTR"];
    const isCurvePoint = (p) => curveKeys.some((key) => {
      const def = HC_ROLES[key];
      return def.sn.includes(p.sn) || (!HC_KNOWN_SN.has(p.sn) && def.re.test(p.norm));
    });
    const curvePoints = pts.filter((p) => !p.used && isCurvePoint(p));
    const branchNames = [...new Set(curvePoints.map((p) => p.branch))];
    // Only the two levels above the point are looked at: the circuit itself
    // may well be called "chauffage/rafraîchissement".
    const isCold = (p) =>
      /chw|glac|froid|cool|kalt/.test(
        hcNorm(p.branch.split(" · ").slice(-2).join(" ") + " " + p.branchSn)
      );
    const branches = {};
    for (const p of curvePoints) {
      const kind = isCold(p) ? "cold" : "hot";
      if (!(kind in branches)) branches[kind] = p.branch;
    }
    const dual = "hot" in branches && "cold" in branches;
    const wanted = this._curveBranch || (syn.cool ? "cold" : "hot");
    const shown = wanted in branches ? wanted : "hot" in branches ? "hot" : "cold";
    const cv = {};
    for (const key of curveKeys) {
      cv[key] = role(key, (p) => !branchNames.length || p.branch === branches[shown]);
    }
    const curveRows = [cv.xBase, cv.yBase, cv.xBp, cv.yBp, cv.xHi, cv.yHi,
      cv.yMin, cv.yMax, cv.expRad, cv.tOaBase, cv.spTR];
    lists.push(list(this._t("curveSettings"), curveRows));

    const others = pts
      .filter((p) => !p.used)
      .sort((a, b) =>
        (a.group + "\u0000" + a.leaf).localeCompare(b.group + "\u0000" + b.leaf)
      );
    return {
      syn, pumps, pltSta, prOpMod,
      lists: lists.filter((l) => l.rows.length),
      curve: this._buildCurve(cv, syn),
      curveBranch: dual ? shown : null,
      others, count: pts.length,
    };
  }

  /** SVG geometry of the heating curve; null when no curve point exists. */
  _buildCurve(cv, syn) {
    const pair = (px, py, label, cls) => {
      if (!px || !py) return null;
      if (px.val == null && py.val == null) return null;
      return {
        x: px.val, y: py.val, px, py, label, cls,
        partial: px.val == null || py.val == null,
        editable: px.writable || py.writable,
      };
    };
    const pts = [
      pair(cv.xBase, cv.yBase, this._t("base"), "base"),
      pair(cv.xBp, cv.yBp, this._t("bp"), "bp"),
      pair(cv.xHi, cv.yHi, this._t("hi"), "hi"),
    ].filter(Boolean);
    if (!pts.length) return null;
    pts.sort((a, b) => (a.x == null ? -1e9 : a.x) - (b.x == null ? -1e9 : b.x));
    const full = pts.filter((p) => !p.partial);
    const yMin = cv.yMin ? cv.yMin.val : null;
    const yMax = cv.yMax ? cv.yMax.val : null;
    const curX = syn.tOa ? syn.tOa.val : null;
    const curY = syn.spTFl ? syn.spTFl.val : null;

    const range = (values, fMin, fMax, pad, step) => {
      const v = values.filter((x) => x != null);
      let lo = v.length ? Math.min(...v) - pad : fMin;
      let hi = v.length ? Math.max(...v) + pad : fMax;
      lo = Math.floor(lo / step) * step;
      hi = Math.ceil(hi / step) * step;
      if (hi - lo < step) hi = lo + step;
      return { min: lo, max: hi };
    };
    // Half-readable points still count for the axes: they are drawn on the
    // axis of their missing coordinate and must stay inside the chart.
    const xr = range(pts.map((p) => p.x).concat([curX]), -15, 20, 3, 5);
    const yr = range(pts.map((p) => p.y).concat([yMin, yMax, curY]), 0, 80, 5, 10);
    const W = 460, H = 300, L = 50, R = 18, T = 14, B = 46;
    const sx = (x) => L + ((x - xr.min) / (xr.max - xr.min)) * (W - L - R);
    const sy = (y) => H - B - ((y - yr.min) / (yr.max - yr.min)) * (H - T - B);
    const ticks = (r, step, f) => {
      const out = [];
      // Keep at most ~8 labels whatever the span.
      while ((r.max - r.min) / step > 8) step *= 2;
      for (let v = r.min; v <= r.max + 1e-9; v += step) out.push({ v, s: f(v) });
      return out;
    };
    pts.forEach((p) => {
      p.sx = p.x == null ? L : sx(p.x);
      p.sy = p.y == null ? H - B : sy(p.y);
    });
    const d = full.map((p, i) => `${i ? "L" : "M"}${p.sx.toFixed(1)} ${p.sy.toFixed(1)}`).join(" ");
    let cy = null;
    if (curX != null) {
      if (curY != null) cy = sy(curY);
      else if (full.length >= 2) {
        if (curX <= full[0].x) cy = full[0].sy;
        else if (curX >= full[full.length - 1].x) cy = full[full.length - 1].sy;
        else {
          for (let j = 0; j < full.length - 1; j++) {
            const a = full[j], b = full[j + 1];
            if (curX >= a.x && curX <= b.x) {
              cy = a.sy + ((curX - a.x) / (b.x - a.x)) * (b.sy - a.sy);
              break;
            }
          }
        }
      }
    }
    return {
      W, H, L, R, T, B, pts, full, d,
      fill: full.length >= 2
        ? `${d} L${full[full.length - 1].sx.toFixed(1)} ${H - B} L${full[0].sx.toFixed(1)} ${H - B} Z`
        : "",
      xTicks: ticks(xr, 5, sx), yTicks: ticks(yr, 10, sy),
      minY: yMin != null ? sy(yMin) : null, maxY: yMax != null ? sy(yMax) : null,
      minP: cv.yMin, maxP: cv.yMax,
      curX: curX != null ? Math.min(W - R, Math.max(L, sx(curX))) : null, cy,
      curXDis: syn.tOa ? this._dis(syn.tOa) : "",
      curYDis: syn.spTFl ? this._dis(syn.spTFl) : "",
    };
  }

  // ---- rendering -----------------------------------------------------------

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>${HC_STYLE}</style>
      <ha-card>
        <div id="body"></div>
        <div id="dlg"></div>
      </ha-card>`;
    const body = this.shadowRoot.getElementById("body");
    body.addEventListener("click", (ev) => this._onBodyClick(ev));
    this.shadowRoot
      .getElementById("dlg")
      .addEventListener("click", (ev) => this._onDialogClick(ev));
  }

  _refresh() {
    const body = this.shadowRoot.getElementById("body");
    if (!body || !this._hass) return;
    if (!this._config.device) {
      if (this._signature !== "unconfigured") {
        this._signature = "unconfigured";
        body.innerHTML = `
          <div class="head"><h2>${hcEsc(this._config.title || this._t("title"))}</h2></div>
          <div class="note">${hcEsc(this._t("hint"))}</div>
          <pre class="code">type: custom:bacnet-heating-circuit-card
device: &lt;device id&gt;</pre>`;
      }
      return;
    }
    // Re-render only when one of the circuit's states actually changed: hass
    // is reassigned on every state change of the whole instance.
    const ids = this._deviceEntityIds();
    const outside = this._config.outside_temp || this._outsideAuto || "";
    const states = this._hass.states;
    let signature = this._hass.language + "|" + this._openOthers + "|" + this._curveBranch + "|";
    const forced = Object.values(this._config.points || {});
    for (const id of ids.concat(outside ? [outside] : [], forced)) {
      const st = states[id];
      signature += id + "=" + (st ? st.state : "?") + ";";
    }
    if (signature === this._signature) return;
    this._signature = signature;
    this._model = this._classify();
    body.innerHTML = this._renderBody(this._model);
  }

  _renderBody(m) {
    const device = (this._hass.devices || {})[this._config.device];
    const title =
      this._config.title ||
      (device && (device.name_by_user || device.name)) ||
      this._t("title");
    if (!m.count) {
      return `<div class="head"><h2>${hcEsc(title)}</h2></div>
        <div class="note">${hcEsc(this._t("noPoints"))}</div>`;
    }
    const chips = [];
    const chip = (label, p, cls) => {
      if (!p) return;
      chips.push(
        `<button class="chip ${cls || ""}" data-pt="${hcEsc(p.id)}">
           <span class="chip-k">${hcEsc(label)}</span>${hcEsc(this._dis(p))}
         </button>`
      );
    };
    chip(this._t("plant"), m.pltSta);
    chip(this._t("mode"), m.prOpMod);
    if (m.syn.hc) chip(m.syn.hc.leaf, m.syn.hc, m.syn.cool ? "cool" : "heat");
    chip(this._t("outside"), m.syn.tOa);
    if (this._isAlarm(m.syn.sfty)) chip(this._t("safety"), m.syn.sfty, "alarm");
    if (this._isAlarm(m.syn.ovr)) chip(m.syn.ovr.leaf, m.syn.ovr, "alarm");

    const show = (s) => this._sections.includes(s);
    const top = [];
    if (show("synoptic")) {
      top.push(`<section class="box"><h3>${hcEsc(this._t("hydraulic"))}</h3>${this._renderSynoptic(m)}</section>`);
    }
    if (show("curve")) {
      const toggle = m.curveBranch
        ? `<div class="seg mini">${["hot", "cold"].map((b) =>
            `<button data-act="branch" data-v="${b}" class="${b === m.curveBranch ? "sel" : ""}">${hcEsc(this._t(b === "hot" ? "heating" : "cooling"))}</button>`
          ).join("")}</div>`
        : "";
      top.push(`<section class="box"><div class="box-h"><h3>${hcEsc(this._t("curve"))}</h3>${toggle}</div>${this._renderCurve(m.curve)}</section>`);
    }
    const lists = show("settings")
      ? m.lists.map((l) => this._renderList(l.title, l.rows)).join("")
      : "";
    let others = "";
    if (show("others") && m.others.length) {
      let rows = "";
      if (this._openOthers) {
        let group = null;
        for (const p of m.others) {
          if (p.group !== group) {
            group = p.group;
            if (group) rows += `<div class="sep">${hcEsc(group)}</div>`;
          }
          rows += this._renderRow(p);
        }
      }
      others = `<section class="box wide">
        <button class="fold" data-act="others" aria-expanded="${this._openOthers}">
          <span class="caret ${this._openOthers ? "open" : ""}">▸</span>
          ${hcEsc(this._t("others"))} <span class="count">${m.others.length}</span>
        </button>${rows ? `<div class="others">${rows}</div>` : ""}
      </section>`;
    }
    const note = this._note
      ? `<div class="note ${this._note.kind}">${hcEsc(this._note.text)}</div>`
      : "";
    return `
      <div class="head"><h2>${hcEsc(title)}</h2><div class="chips">${chips.join("")}</div></div>
      ${note}
      ${top.length ? `<div class="grid top">${top.join("")}</div>` : ""}
      ${lists ? `<div class="grid">${lists}</div>` : ""}
      ${others}`;
  }

  _renderList(title, rows) {
    return `<section class="box"><h3>${hcEsc(title)}</h3>${rows
      .map((p) => this._renderRow(p))
      .join("")}</section>`;
  }

  _renderRow(p) {
    const alarm = p.domain === "binary_sensor" && p.st.state === "on" &&
      /defaut|fault|alarm|securite|storung/.test(p.norm);
    return `<button class="row ${p.writable ? "rw" : ""} ${p.avail ? "" : "stale"} ${alarm ? "alarm" : ""}"
        data-pt="${hcEsc(p.id)}" title="${hcEsc(p.group ? p.group + " · " + p.leaf : p.leaf)}">
        <span class="row-k">${hcEsc(p.ctx && p.parent && p.parent !== p.a.equipment ? p.parent + " · " + p.leaf : p.leaf)}</span>
        <span class="row-v">${hcEsc(this._dis(p))}${p.writable ? '<span class="pen">✎</span>' : ""}</span>
      </button>`;
  }

  _renderSynoptic(m) {
    const s = m.syn;
    const running = s.pumps.some((pu) => pu.on);
    const bubble = (x, y, w, label, p, cls) => {
      if (!p) return "";
      return `<g class="bub ${cls || ""} ${p.avail ? "" : "stale"}" data-pt="${hcEsc(p.id)}">
        <rect x="${x}" y="${y}" width="${w}" height="34" rx="6"/>
        <text x="${x + w / 2}" y="${y + 13}" class="bub-k">${hcEsc(label)}</text>
        <text x="${x + w / 2}" y="${y + 28}" class="bub-v">${hcEsc(this._dis(p))}</text>
      </g>`;
    };
    const rotor = (cx, pu) => `
      <g class="pump ${pu.on ? "on" : "off"} ${pu.fault ? "fault" : ""}" data-pt="${hcEsc(pu.cmd.id)}">
        <title>${hcEsc(pu.cmd.leaf)} : ${hcEsc(this._dis(pu.cmd))}${pu.flt ? " — " + hcEsc(pu.flt.leaf) + " : " + hcEsc(this._dis(pu.flt)) : ""}</title>
        <circle cx="${cx}" cy="150" r="${s.pumps.length > 1 ? 12 : 16}" class="pump-body"/>
        <path class="dir" d="M${cx} ${150 - 8} L${cx + 7} ${150 + 5} H${cx - 7} Z"/>
      </g>`;
    let pumps = "";
    if (s.pumps.length === 1) {
      const pu = s.pumps[0];
      pumps = rotor(120, pu) +
        `<text x="98" y="154" class="lbl end ${pu.fault ? "alarm" : ""}">P${pu.n} · ${hcEsc(pu.fault ? this._t("fault") : this._dis(pu.cmd))}</text>`;
    } else if (s.pumps.length === 2) {
      const twin = this._isAlarm(s.twnFlt);
      pumps = `<rect x="84" y="133" width="72" height="34" rx="17" class="twin ${twin ? "fault" : ""}"/>` +
        rotor(102, s.pumps[0]) + rotor(138, s.pumps[1]) +
        s.pumps.map((pu, i) =>
          `<text x="78" y="${146 + i * 14}" class="lbl end ${pu.fault ? "alarm" : ""}">P${pu.n} · ${hcEsc(pu.fault ? this._t("fault") : this._dis(pu.cmd))}</text>`
        ).join("");
    }
    let valve = "";
    if (s.valve) {
      valve = `
        <path d="M240 225 H120" class="pipe ret"/>
        ${running ? '<path d="M240 225 H120" class="flow"/>' : ""}
        <g class="valve" data-pt="${hcEsc(s.valve.id)}">
          <title>${hcEsc(s.valve.leaf)} : ${hcEsc(this._dis(s.valve))}</title>
          <path d="M120 225 L110 208 H130 Z M120 225 L110 242 H130 Z M120 225 L137 215 V235 Z"/>
          <path d="M120 225 H103" class="stem"/>
          <circle cx="93" cy="225" r="10"/>
          <text x="93" y="229" class="motor">M</text>
        </g>
        <g class="bub small ${s.valve.avail ? "" : "stale"}" data-pt="${hcEsc(s.valve.id)}">
          <rect x="14" y="214" width="62" height="22" rx="6"/>
          <text x="45" y="229" class="bub-v">${hcEsc(this._dis(s.valve))}</text>
        </g>`;
    }
    const setpoint = s.spTFl
      ? `<g class="bub small sp ${s.spTFl.avail ? "" : "stale"}" data-pt="${hcEsc(s.spTFl.id)}">
           <title>${hcEsc(s.spTFl.leaf)}</title>
           <rect x="14" y="108" width="94" height="20" rx="6"/>
           <text x="61" y="122" class="bub-v">${hcEsc(this._t("setpoint"))} ${hcEsc(this._dis(s.spTFl))}</text>
         </g>`
      : "";
    return `
      <svg class="syn ${s.cool ? "cool" : ""}" viewBox="0 0 360 300" role="img" aria-label="${hcEsc(this._t("hydraulic"))}">
        <text x="180" y="13" class="zone">${hcEsc(this._t("emitters"))}</text>
        <path d="M220 40 H240 V296" class="pipe ret"/>
        <path d="M120 296 V40 H140" class="pipe sup"/>
        ${running ? '<path d="M120 296 V40 H140" class="flow"/><path d="M220 40 H240 V296" class="flow"/>' : ""}
        <path d="M112 280 H128 L120 266 Z" class="arrow"/>
        <path d="M232 266 H248 L240 280 Z" class="arrow"/>
        <g class="rad">
          <rect x="140" y="22" width="80" height="36" rx="4"/>
          <path d="M152 27 V53 M164 27 V53 M176 27 V53 M188 27 V53 M200 27 V53 M212 27 V53"/>
        </g>
        ${valve}
        ${pumps}
        ${bubble(14, 68, 94, this._t("supply"), s.tFl, "sup")}
        ${setpoint}
        ${bubble(252, 68, 94, this._t("ret"), s.tRt, "ret")}
      </svg>`;
  }

  _renderCurve(c) {
    if (!c) return `<div class="note">${hcEsc(this._t("curveNone"))}</div>`;
    const { W, H, L, R, T, B } = c;
    const f = (v) => v.toFixed(1);
    let g = "";
    for (const t of c.xTicks) {
      g += `<line x1="${f(t.s)}" y1="${T}" x2="${f(t.s)}" y2="${H - B}" class="gridl"/>
            <text x="${f(t.s)}" y="${H - B + 15}" class="tick">${this._fmtNum(t.v, 0)}</text>`;
    }
    for (const t of c.yTicks) {
      g += `<line x1="${L}" y1="${f(t.s)}" x2="${W - R}" y2="${f(t.s)}" class="gridl"/>
            <text x="${L - 6}" y="${f(t.s + 4)}" class="tick end">${this._fmtNum(t.v, 0)}</text>`;
    }
    const limit = (y, p, label) =>
      y == null ? "" : `
        <g class="lim" data-pt="${hcEsc(p.id)}"><title>${hcEsc(p.leaf)}</title>
          <line x1="${L}" y1="${f(y)}" x2="${W - R}" y2="${f(y)}"/>
          <text x="${W - R - 4}" y="${f(y - 4)}" class="end">${hcEsc(label)} ${hcEsc(this._dis(p))}</text>
        </g>`;
    const points = c.pts.map((p, i) => `
      <g class="cpt ${p.cls} ${p.editable ? "rw" : ""}" data-cpt="${i}">
        <title>${hcEsc(p.label)} — ${hcEsc(this._dis(p.px))} → ${hcEsc(this._dis(p.py))}</title>
        <circle cx="${f(p.sx)}" cy="${f(p.sy)}" r="13" class="hit"/>
        <circle cx="${f(p.sx)}" cy="${f(p.sy)}" r="6"/>
        <text x="${f(p.sx)}" y="${f(p.sy - 11)}" class="cpt-l">${hcEsc(p.partial ? p.label + " ?" : p.label)}</text>
      </g>`).join("");
    let cur = "";
    if (c.curX != null) {
      cur = `<line x1="${f(c.curX)}" y1="${T}" x2="${f(c.curX)}" y2="${H - B}" class="cur-l"/>`;
      if (c.cy != null) {
        const anchorEnd = c.curX > W - R - 90;
        cur += `<circle cx="${f(c.curX)}" cy="${f(c.cy)}" r="5" class="cur-d"/>
          <text x="${f(c.curX + (anchorEnd ? -9 : 9))}" y="${H - B - 7}" class="cur-t ${anchorEnd ? "end" : ""}">${hcEsc(c.curXDis)} → ${hcEsc(c.curYDis)}</text>`;
      }
    }
    return `
      <svg class="curve" viewBox="0 0 ${W} ${H}" role="img" aria-label="${hcEsc(this._t("curve"))}">
        ${g}
        <line x1="${L}" y1="${H - B}" x2="${W - R}" y2="${H - B}" class="axis"/>
        <line x1="${L}" y1="${T}" x2="${L}" y2="${H - B}" class="axis"/>
        <text x="${(L + W - R) / 2}" y="${H - 8}" class="axis-t">${hcEsc(this._t("xAxis"))}</text>
        <text transform="translate(13 ${(T + H - B) / 2}) rotate(-90)" class="axis-t">${hcEsc(this._t("yAxis"))}</text>
        ${c.fill ? `<path d="${c.fill}" class="area"/>` : ""}
        ${c.d && c.full.length >= 2 ? `<path d="${c.d}" class="line"/>` : ""}
        ${limit(c.minY, c.minP, this._t("min"))}
        ${limit(c.maxY, c.maxP, this._t("max"))}
        ${cur}
        ${points}
      </svg>`;
  }

  // ---- interaction ---------------------------------------------------------

  _findPoint(entityId) {
    return this._point(entityId);
  }

  _moreInfo(entityId) {
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId },
        bubbles: true,
        composed: true,
      })
    );
  }

  _onBodyClick(ev) {
    const path = ev.composedPath();
    for (const el of path) {
      if (!(el instanceof Element)) continue;
      if (el.id === "body") break;
      if (el.dataset.act === "others") {
        this._openOthers = !this._openOthers;
        this._refresh();
        return;
      }
      if (el.dataset.act === "branch") {
        this._curveBranch = el.dataset.v;
        this._refresh();
        return;
      }
      if (el.dataset.cpt != null) {
        const p = this._model.curve && this._model.curve.pts[Number(el.dataset.cpt)];
        if (p) this._openCurvePoint(p);
        return;
      }
      if (el.dataset.pt) {
        const p = this._findPoint(el.dataset.pt);
        if (!p) return;
        if (p.writable && p.avail) this._openPoint(p);
        else this._moreInfo(p.id);
        return;
      }
    }
  }

  _openPoint(p) {
    const field = { p, label: p.leaf, value: "" };
    if (p.domain === "switch" || p.domain === "input_boolean") {
      field.kind = "bool";
      field.value = p.st.state === "on" ? "on" : "off";
    } else if (Array.isArray(p.a.options)) {
      field.kind = "enum";
      field.value = p.st.state;
    } else {
      field.kind = "num";
      field.value = p.val == null ? "" : String(p.val);
    }
    this._dlg = { title: p.leaf, sub: p.group, fields: [field], step: 1, error: null };
    this._note = null;
    this._renderDialog(true);
  }

  _openCurvePoint(cp) {
    const fields = [
      { p: cp.px, label: this._t("xField"), kind: "num" },
      { p: cp.py, label: this._t("yField"), kind: "num" },
    ];
    fields.forEach((f) => (f.value = f.p.val == null ? "" : String(f.p.val)));
    if (!cp.editable) {
      this._moreInfo(cp.py.id);
      return;
    }
    this._dlg = {
      title: `${this._t("curvePoint")} — ${cp.label}`,
      sub: cp.py.group,
      fields,
      step: 1,
      error: null,
    };
    this._note = null;
    this._renderDialog(true);
  }

  _closeDialog() {
    this._dlg = null;
    this._renderDialog();
  }

  _optionLabel(field, value) {
    if (field.kind === "bool") {
      const text = value === "on" ? field.p.a.active_text : field.p.a.inactive_text;
      return text ? String(text) : this._t(value);
    }
    if (field.kind === "num") {
      const n = Number(String(value).replace(",", "."));
      return this._fmtNum(n, 2) + (field.p.unit ? " " + field.p.unit : "");
    }
    return String(value);
  }

  /** Read the inputs into the dialog model; returns the fields to write. */
  _collectChanges() {
    const dlg = this._dlg;
    const root = this.shadowRoot.getElementById("dlg");
    const changes = [];
    dlg.error = null;
    dlg.fields.forEach((field, i) => {
      const input = root.querySelector(`[data-field="${i}"]`);
      if (input) field.value = input.value;
      if (!field.p.writable || !field.p.avail && field.kind !== "num") return;
      if (field.kind === "num") {
        const text = String(field.value).trim().replace(",", ".");
        if (text === "" && field.p.val == null) return;
        const n = Number(text);
        if (text === "" || !Number.isFinite(n)) {
          dlg.error = this._t("invalid");
          return;
        }
        if (n !== field.p.val) changes.push({ field, value: n });
      } else if (field.value !== field.p.st.state) {
        changes.push({ field, value: field.value });
      }
    });
    if (!dlg.error && !changes.length) dlg.error = this._t("unchanged");
    return dlg.error ? null : changes;
  }

  _dialogAdvance() {
    const dlg = this._dlg;
    if (!dlg || dlg.busy) return;
    if (dlg.step === 1) {
      const changes = this._collectChanges();
      if (changes) {
        dlg.changes = changes;
        dlg.step = 2;
      }
      this._renderDialog();
    } else {
      this._write();
    }
  }

  async _write() {
    const dlg = this._dlg;
    dlg.busy = true;
    dlg.error = null;
    this._renderDialog();
    try {
      for (const { field, value } of dlg.changes) {
        const entity_id = field.p.id;
        const domain = field.p.domain;
        if (field.kind === "bool") {
          await this._hass.callService(domain, value === "on" ? "turn_on" : "turn_off", { entity_id });
        } else if (field.kind === "enum") {
          await this._hass.callService(domain, "select_option", { entity_id, option: value });
        } else {
          await this._hass.callService(domain, "set_value", { entity_id, value });
        }
      }
      this._dlg = null;
      this._note = { kind: "ok", text: `« ${dlg.title} » : ${this._t("written")}` };
      this._signature = null;
      this._renderDialog();
      this._refresh();
      setTimeout(() => {
        this._note = null;
        this._signature = null;
        this._refresh();
      }, 4000);
    } catch (err) {
      dlg.busy = false;
      dlg.error = (err && err.message) || String(err);
      this._renderDialog();
    }
  }

  _onDialogClick(ev) {
    for (const el of ev.composedPath()) {
      if (!(el instanceof Element)) continue;
      const act = el.dataset.act;
      if (!act) continue;
      if (act === "close") this._closeDialog();
      else if (act === "next") this._dialogAdvance();
      else if (act === "back") {
        this._dlg.step = 1;
        this._dlg.error = null;
        this._renderDialog();
      } else if (act === "history") {
        const id = el.dataset.id;
        this._closeDialog();
        this._moreInfo(id);
      } else if (act === "bool") {
        const field = this._dlg.fields[Number(el.dataset.i)];
        field.value = el.dataset.v;
        this._renderDialog();
      }
      return;
    }
  }

  _renderDialog(focus) {
    const root = this.shadowRoot.getElementById("dlg");
    if (!root) return;
    const dlg = this._dlg;
    if (!dlg) {
      root.innerHTML = "";
      return;
    }
    let content = "";
    if (dlg.step === 1) {
      content = dlg.fields.map((field, i) => {
        const p = field.p;
        const locked = !p.writable;
        let input;
        if (field.kind === "bool") {
          input = `<div class="seg">${["off", "on"].map((v) =>
            `<button data-act="bool" data-i="${i}" data-v="${v}" class="${field.value === v ? "sel" : ""}">${hcEsc(this._optionLabel(field, v))}</button>`
          ).join("")}</div><input type="hidden" data-field="${i}" value="${hcEsc(field.value)}"/>`;
        } else if (field.kind === "enum") {
          input = `<select data-field="${i}">${p.a.options.map((o) =>
            `<option value="${hcEsc(o)}" ${o === field.value ? "selected" : ""}>${hcEsc(o)}</option>`
          ).join("")}</select>`;
        } else {
          input = `<div class="num"><input data-field="${i}" type="text" inputmode="decimal"
            value="${hcEsc(field.value)}" ${locked ? "disabled" : ""}/>
            <span>${hcEsc(p.unit)}</span></div>`;
        }
        return `<div class="field">
          <label>${hcEsc(field.label)}${locked ? ` <em>(${hcEsc(this._t("readOnly"))})</em>` : ""}</label>
          <div class="cur">${hcEsc(this._t("current"))} : <b>${hcEsc(this._dis(p))}</b>
            <button class="link" data-act="history" data-id="${hcEsc(p.id)}">${hcEsc(this._t("history"))}</button></div>
          ${input}
        </div>`;
      }).join("");
    } else {
      content = `<div class="confirm">${hcEsc(this._t("confirm"))}</div>` +
        dlg.changes.map(({ field, value }) => `
          <div class="change">
            <span>${hcEsc(field.p.leaf)}</span>
            <span><s>${hcEsc(this._dis(field.p))}</s> → <b>${hcEsc(this._optionLabel(field, field.kind === "num" ? String(value) : value))}</b></span>
          </div>`).join("");
    }
    root.innerHTML = `
      <div class="backdrop" data-act="close"></div>
      <div class="modal" role="dialog" aria-modal="true">
        <div class="modal-h">
          <div><div class="modal-t">${hcEsc(dlg.title)}</div>
          ${dlg.sub ? `<div class="modal-s">${hcEsc(dlg.sub)}</div>` : ""}</div>
          <button class="x" data-act="close" aria-label="${hcEsc(this._t("cancel"))}">✕</button>
        </div>
        <div class="modal-b">${content}
          ${dlg.error ? `<div class="note err">${hcEsc(dlg.error)}</div>` : ""}
        </div>
        <div class="modal-f">
          ${dlg.step === 2
            ? `<button class="btn" data-act="back" ${dlg.busy ? "disabled" : ""}>${hcEsc(this._t("back"))}</button>`
            : `<button class="btn" data-act="close">${hcEsc(this._t("cancel"))}</button>`}
          <button class="btn primary ${dlg.step === 2 ? "warn" : ""}" data-act="next" ${dlg.busy ? "disabled" : ""}>
            ${hcEsc(this._t(dlg.step === 2 ? "write" : "next"))}</button>
        </div>
      </div>`;
    if (focus) {
      const first = root.querySelector("input:not([disabled]):not([type=hidden]), select");
      if (first) {
        first.focus();
        if (first.select) first.select();
      }
    }
  }
}

/** BACnet installations known to Home Assistant: [{id, name}]. */
function hcBacnetDevices(hass) {
  if (!hass || !hass.entities || !hass.devices) return [];
  const ids = new Set();
  for (const entry of Object.values(hass.entities)) {
    if (entry.platform === "bacnet" && entry.device_id) ids.add(entry.device_id);
  }
  const out = [];
  for (const id of ids) {
    const device = hass.devices[id];
    if (!device) continue;
    const area = device.area_id && hass.areas && hass.areas[device.area_id];
    const name = device.name_by_user || device.name || id;
    out.push({ id, name, label: area ? `${name} — ${area.name}` : name });
  }
  return out.sort((a, b) => a.label.localeCompare(b.label));
}

const HC_STYLE = `
  :host { display: block; --hc-sup: #e2453c; --hc-ret: #3f8fe0; --hc-on: #28bf66; --hc-sp: #9d4edd; }
  ha-card { padding: 16px; }
  .head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin-bottom: 12px; }
  h2 { margin: 0; font-size: 1.15rem; font-weight: 600; margin-right: auto; }
  h3 { margin: 0 0 8px; font-size: 0.8rem; font-weight: 700; letter-spacing: .03em;
    text-transform: uppercase; color: var(--secondary-text-color, #727272); }
  button { font: inherit; color: inherit; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { border: 1px solid var(--divider-color, #e0e0e0); background: transparent; border-radius: 100px;
    padding: 3px 10px; font-size: 0.8rem; cursor: pointer; }
  .chip-k { color: var(--secondary-text-color, #727272); margin-right: 6px; }
  .chip.alarm { border-color: var(--error-color, #d72339); color: var(--error-color, #d72339); font-weight: 600; }
  .chip.cool { border-color: var(--hc-ret); }
  .chip.heat { border-color: var(--hc-sup); }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(260px, 100%), 1fr)); gap: 12px; margin-bottom: 12px; }
  .box { border: 1px solid var(--divider-color, #e0e0e0); border-radius: 10px; padding: 12px; min-width: 0; }
  .box.wide { padding: 4px 12px; }
  .note { font-size: 0.85rem; color: var(--secondary-text-color, #727272); margin: 4px 0 10px; }
  .note.ok { color: var(--success-color, #1c703f); }
  .note.err { color: var(--error-color, #d72339); margin: 10px 0 0; }
  .code { margin: 0; padding: 10px 12px; border-radius: 8px; font-size: 0.78rem;
    background: var(--secondary-background-color, #f5f5f5); white-space: pre-wrap; }

  .row { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; width: 100%;
    border: none; background: transparent; text-align: left; padding: 6px 4px; cursor: pointer;
    border-top: 1px solid var(--divider-color, #eee); font-size: 0.88rem; }
  h3 + .row, .sep + .row { border-top: none; }
  .row:hover { background: var(--secondary-background-color, #f5f5f5); }
  .row-k { color: var(--secondary-text-color, #727272); min-width: 0; }
  .row-v { font-weight: 600; text-align: right; white-space: nowrap; }
  .row.rw .row-v { color: var(--primary-color, #03a9f4); }
  .row.stale .row-v { color: var(--disabled-text-color, #9e9e9e); font-weight: 400; }
  .row.alarm .row-v { color: var(--error-color, #d72339); }
  .pen { margin-left: 6px; font-weight: 400; opacity: .7; }
  .sep { font-size: 0.72rem; font-weight: 700; color: var(--secondary-text-color, #727272);
    margin: 10px 0 2px; text-transform: uppercase; letter-spacing: .03em; }
  .fold { display: flex; align-items: center; gap: 8px; width: 100%; border: none; background: transparent;
    padding: 8px 0; cursor: pointer; font-size: 0.88rem; font-weight: 600; text-align: left; }
  .caret { display: inline-block; transition: transform .15s; }
  .caret.open { transform: rotate(90deg); }
  .count { color: var(--secondary-text-color, #727272); font-weight: 400; }
  .others { columns: 300px; column-gap: 24px; padding-bottom: 8px; }
  .others .row, .others .sep { break-inside: avoid; }

  svg { display: block; width: 100%; height: auto; max-height: 340px; }
  svg text { font-family: inherit; fill: var(--primary-text-color, #212121); }
  [data-pt], [data-cpt] { cursor: pointer; }
  .syn { --sup: var(--hc-sup); --ret: var(--hc-ret); }
  .syn.cool { --sup: var(--hc-ret); --ret: #8ec3f5; }
  .zone { font-size: 9px; font-weight: 700; letter-spacing: .08em; text-anchor: middle;
    fill: var(--secondary-text-color, #727272); }
  .pipe { fill: none; stroke-width: 8; stroke-linejoin: round; }
  .pipe.sup { stroke: var(--sup); }
  .pipe.ret { stroke: var(--ret); }
  .flow { fill: none; stroke: #fff; stroke-opacity: .65; stroke-width: 2.5; stroke-linecap: round;
    stroke-dasharray: 1 15; animation: hc-flow 1.1s linear infinite; }
  @keyframes hc-flow { to { stroke-dashoffset: -16; } }
  .arrow { fill: var(--primary-text-color, #212121); opacity: .75; }
  .rad rect { fill: var(--secondary-background-color, #f5f5f5); stroke: var(--secondary-text-color, #727272); stroke-width: 1.5; }
  .rad path { stroke: var(--secondary-text-color, #727272); stroke-width: 1.5; fill: none; opacity: .6; }
  .valve path, .valve circle { fill: var(--card-background-color, #fff); stroke: var(--primary-text-color, #212121);
    stroke-width: 1.6; stroke-linejoin: round; }
  .valve .stem { fill: none; }
  .motor { font-size: 11px; font-weight: 700; text-anchor: middle; }
  .twin { fill: var(--card-background-color, #fff); stroke: var(--primary-text-color, #212121); stroke-width: 1.6; }
  .twin.fault { stroke: var(--error-color, #d72339); stroke-width: 3; }
  .pump-body { fill: var(--card-background-color, #fff); stroke: var(--primary-text-color, #212121); stroke-width: 1.6; }
  /* The triangle is the pump symbol's flow direction: it never moves. A
     running pump is told by its green body and by the flow in the pipes. */
  .pump .dir { fill: var(--secondary-text-color, #727272); }
  .pump.on .pump-body { fill: var(--hc-on); }
  .pump.on .dir { fill: #fff; }
  .pump.fault .pump-body { stroke: var(--error-color, #d72339); stroke-width: 3.5; }
  .lbl { font-size: 11px; font-weight: 600; }
  .lbl.alarm { fill: var(--error-color, #d72339); }
  .end { text-anchor: end; }
  .bub rect { fill: var(--card-background-color, #fff); stroke: var(--divider-color, #bdbdbd); stroke-width: 1.2; }
  .bub.sup rect { stroke: var(--sup); }
  .bub.ret rect { stroke: var(--ret); }
  .bub.sp rect { stroke: var(--hc-sp); stroke-dasharray: 3 2; }
  .bub-k { font-size: 8.5px; font-weight: 700; letter-spacing: .08em; text-anchor: middle;
    fill: var(--secondary-text-color, #727272); }
  .bub-v { font-size: 13px; font-weight: 700; text-anchor: middle; }
  .bub.small .bub-v { font-size: 11px; }
  .bub.stale .bub-v { fill: var(--disabled-text-color, #9e9e9e); }

  .gridl { stroke: var(--divider-color, #e0e0e0); stroke-width: 1; }
  .axis { stroke: var(--secondary-text-color, #727272); stroke-width: 1.2; }
  .tick { font-size: 10.5px; text-anchor: middle; fill: var(--secondary-text-color, #727272); }
  .tick.end { text-anchor: end; }
  .axis-t { font-size: 11px; text-anchor: middle; fill: var(--secondary-text-color, #727272); }
  .area { fill: var(--hc-sup); opacity: .1; }
  .line { fill: none; stroke: var(--hc-sup); stroke-width: 2.5; stroke-linejoin: round; stroke-linecap: round; }
  .lim line { stroke: var(--secondary-text-color, #727272); stroke-width: 1.2; stroke-dasharray: 5 4; }
  .lim text { font-size: 10px; fill: var(--secondary-text-color, #727272); }
  .cpt circle { fill: var(--card-background-color, #fff); stroke: var(--hc-sup); stroke-width: 2.5; }
  .cpt .hit { fill: transparent; stroke: none; }
  .cpt.rw:hover circle:not(.hit) { fill: var(--hc-sup); }
  .cpt-l { font-size: 10.5px; font-weight: 600; text-anchor: middle; }
  /* Halo: labels stay readable where they cross the curve or a limit line. */
  .cpt-l, .cur-t, .lim text { paint-order: stroke; stroke: var(--card-background-color, #fff); stroke-width: 3px; stroke-linejoin: round; }
  .cur-l { stroke: var(--hc-sp); stroke-width: 1.2; stroke-dasharray: 3 3; }
  .cur-d { fill: var(--hc-sp); stroke: var(--card-background-color, #fff); stroke-width: 1.5; }
  .cur-t { font-size: 10.5px; font-weight: 600; fill: var(--hc-sp); }

  .backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 100; }
  .modal { position: fixed; z-index: 101; left: 50%; top: 50%; transform: translate(-50%, -50%);
    width: min(400px, calc(100vw - 32px)); max-height: calc(100vh - 32px); overflow: auto;
    background: var(--card-background-color, #fff); color: var(--primary-text-color, #212121);
    border-radius: 12px; box-shadow: 0 12px 40px rgba(0,0,0,.35); }
  .modal-h { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; padding: 16px 16px 8px; }
  .modal-t { font-size: 1rem; font-weight: 600; }
  .modal-s { font-size: 0.78rem; color: var(--secondary-text-color, #727272); margin-top: 2px; }
  .x { border: none; background: transparent; cursor: pointer; font-size: 1rem; padding: 4px 8px; }
  .modal-b { padding: 4px 16px 12px; }
  .modal-f { display: flex; justify-content: flex-end; gap: 8px; padding: 8px 16px 16px; }
  .field { margin-top: 12px; }
  .field label { display: block; font-size: 0.82rem; font-weight: 600; margin-bottom: 2px; }
  .field em { font-weight: 400; color: var(--secondary-text-color, #727272); }
  .cur { font-size: 0.78rem; color: var(--secondary-text-color, #727272); margin-bottom: 6px; }
  .link { border: none; background: transparent; cursor: pointer; padding: 0 0 0 8px;
    color: var(--primary-color, #03a9f4); font-size: 0.78rem; text-decoration: underline; }
  .num { display: flex; align-items: center; gap: 8px; }
  .modal input[type=text], .modal select { width: 100%; box-sizing: border-box; padding: 9px 10px; font: inherit;
    border: 1px solid var(--divider-color, #bdbdbd); border-radius: 8px;
    background: var(--card-background-color, #fff); color: var(--primary-text-color, #212121); }
  .modal input:disabled { opacity: .55; }
  .seg { display: flex; gap: 8px; }
  .box-h { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
  .box-h h3 { margin: 0; }
  .seg.mini { gap: 4px; }
  .seg.mini button { flex: none; padding: 3px 10px; font-size: 0.78rem; border-radius: 100px; }
  .seg button { flex: 1; padding: 9px; border-radius: 8px; cursor: pointer;
    border: 1px solid var(--divider-color, #bdbdbd); background: transparent; }
  .seg button.sel { border-color: var(--primary-color, #03a9f4); background: var(--primary-color, #03a9f4); color: #fff; font-weight: 600; }
  .confirm { font-size: 0.88rem; margin: 8px 0; }
  .change { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; font-size: 0.88rem;
    border-top: 1px solid var(--divider-color, #eee); }
  .change s { color: var(--secondary-text-color, #727272); }
  .btn { border: 1px solid var(--divider-color, #bdbdbd); background: transparent; border-radius: 8px;
    padding: 7px 16px; cursor: pointer; font-size: 0.88rem; font-weight: 600; }
  .btn.primary { border-color: var(--primary-color, #03a9f4); background: var(--primary-color, #03a9f4); color: #fff; }
  .btn.primary.warn { border-color: var(--warning-color, #c75300); background: var(--warning-color, #c75300); }
  .btn:disabled { opacity: .5; cursor: default; }
  :is(button, [data-pt], [data-cpt]):focus-visible { outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 1px; }
  @media (prefers-reduced-motion: reduce) { .flow { animation: none; } }
`;

// Guard against double definition (the versioned ?v= URL may load the module
// more than once).
if (!customElements.get("bacnet-heating-circuit-card")) {
  customElements.define("bacnet-heating-circuit-card", BacnetHeatingCircuitCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "bacnet-heating-circuit-card",
    name: "BACnet Heating Circuit Card",
    description:
      "Heating circuit overview: hydraulic synoptic, heating curve, setpoints and operating mode of a BACnet installation.",
    preview: false,
    documentationURL: "https://github.com/Morrine74/ha-bacnet",
  });
}

// ---------------------------------------------------------------------------
// Visual editor: pick the installation, title, outside temperature, sections.
// ---------------------------------------------------------------------------

class BacnetHeatingCircuitCardEditor extends HTMLElement {
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
    const first = !this._hass;
    this._hass = hass;
    // The device list only depends on the registries: do not rebuild the form
    // (and lose focus) on every state change.
    if (first || this._devicesRef !== hass.devices) this._render();
  }

  _t(key) {
    const lang = String((this._hass && this._hass.language) || "en").slice(0, 2);
    return (HC_I18N[lang] || HC_I18N.en)[key] || key;
  }

  _emit(patch) {
    const config = { ...this._config, ...patch };
    for (const key of Object.keys(config)) {
      if (config[key] === "" || config[key] == null) delete config[key];
    }
    this._config = config;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config },
        bubbles: true,
        composed: true,
      })
    );
  }

  _render() {
    if (!this._hass) return;
    this._devicesRef = this._hass.devices;
    const devices = hcBacnetDevices(this._hass);
    const selected = this._config.device || "";
    const sections = Array.isArray(this._config.sections) && this._config.sections.length
      ? this._config.sections
      : HC_SECTIONS;
    const secLabel = { synoptic: "secSynoptic", curve: "secCurve", settings: "secSettings", others: "secOthers" };
    const temps = Object.keys(this._hass.states)
      .filter((id) => id.startsWith("sensor.") &&
        /°C|°F|K/.test((this._hass.states[id].attributes || {}).unit_of_measurement || ""))
      .sort();
    this.shadowRoot.innerHTML = `
      <style>
        .ed { display: flex; flex-direction: column; gap: 12px; padding: 4px 0; }
        label { font-size: 0.8rem; color: var(--secondary-text-color, #666); display: block; margin-bottom: 4px; }
        select, input[type=text] { width: 100%; box-sizing: border-box; padding: 8px;
          border: 1px solid var(--divider-color, #ccc); border-radius: 6px;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #212121); font-size: 0.9rem; }
        .checks { display: flex; flex-wrap: wrap; gap: 6px 16px; }
        .checks label { display: inline-flex; align-items: center; gap: 6px; margin: 0;
          color: var(--primary-text-color, #212121); font-size: 0.88rem; }
        .ed-note { font-size: 0.78rem; color: var(--warning-color, #b8860b);
          background: var(--secondary-background-color, #faf7ec); padding: 8px 10px; border-radius: 6px; }
      </style>
      <div class="ed">
        ${devices.length ? "" : `<div class="ed-note">${hcEsc(this._t("edNone"))}</div>`}
        <div>
          <label>${hcEsc(this._t("edDevice"))}</label>
          <select id="device">
            <option value="">${hcEsc(this._t("edPick"))}</option>
            ${devices.map((d) =>
              `<option value="${hcEsc(d.id)}" ${d.id === selected ? "selected" : ""}>${hcEsc(d.label)}</option>`
            ).join("")}
          </select>
        </div>
        <div>
          <label>${hcEsc(this._t("edTitle"))}</label>
          <input id="title" type="text" value="${hcEsc(this._config.title || "")}"/>
        </div>
        <div>
          <label>${hcEsc(this._t("edOutside"))}</label>
          <input id="outside" type="text" list="temps" value="${hcEsc(this._config.outside_temp || "")}"/>
          <datalist id="temps">${temps.map((id) => `<option value="${hcEsc(id)}"></option>`).join("")}</datalist>
        </div>
        <div>
          <label>${hcEsc(this._t("edSections"))}</label>
          <div class="checks">${HC_SECTIONS.map((s) =>
            `<label><input type="checkbox" data-sec="${s}" ${sections.includes(s) ? "checked" : ""}/>${hcEsc(this._t(secLabel[s]))}</label>`
          ).join("")}</div>
        </div>
      </div>`;
    const $ = (id) => this.shadowRoot.getElementById(id);
    $("device").addEventListener("change", (ev) => this._emit({ device: ev.target.value }));
    $("title").addEventListener("change", (ev) => this._emit({ title: ev.target.value }));
    $("outside").addEventListener("change", (ev) => this._emit({ outside_temp: ev.target.value.trim() }));
    this.shadowRoot.querySelectorAll("[data-sec]").forEach((box) =>
      box.addEventListener("change", () => {
        const chosen = [...this.shadowRoot.querySelectorAll("[data-sec]")]
          .filter((b) => b.checked)
          .map((b) => b.dataset.sec);
        // All sections = the default: keep the YAML clean.
        this._emit({ sections: chosen.length === HC_SECTIONS.length ? null : chosen });
      })
    );
  }
}

if (!customElements.get("bacnet-heating-circuit-card-editor")) {
  customElements.define(
    "bacnet-heating-circuit-card-editor",
    BacnetHeatingCircuitCardEditor
  );
}
