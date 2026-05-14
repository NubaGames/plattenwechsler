const state = {
  online: false,
  system: {},
  esp: {},
  events: [],
};
const STATE_TEXT = {
  INIT: "INITIALISIERUNG", REFERENZFAHRT: "REFERENZFAHRT",
  BEREITSCHAFT: "BEREITSCHAFT", PLATTENWECHSEL: "PLATTENWECHSEL LÄUFT",
  SERVICE: "SERVICE-MODUS", FEHLER: "FEHLER", NOT_AUS: "NOT-AUS AKTIV",
};
const STATE_CLASS = {
  BEREITSCHAFT: "bereit", PLATTENWECHSEL: "wechsel",
  REFERENZFAHRT: "referenz", FEHLER: "fehler", SERVICE: "service",
  NOT_AUS: "fehler",
};
const DRUCKER_STATUS_TEXT = {
  bereit: "bereit", druckt: "druckt",
  in_queue: "in Queue", aktiv: "wird gewechselt",
};

async function api(path, body) {
  try {
    const opts = { method: "POST", headers: {"Content-Type":"application/json"} };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const r = await fetch(path, opts);
    return await r.json();
  } catch (e) { toast("Verbindungsfehler", "warn"); return {ok:false}; }
}
async function fetchInitial() {
  try {
    const r = await fetch("/api/state");
    const j = await r.json();
    if (j.system) state.system = j.system;
    if (j.esp) state.esp = j.esp;
    state.online = j.online;
    render();
  } catch (e) {}
}

let evtSource = null;
function startSSE() {
  if (evtSource) evtSource.close();
  evtSource = new EventSource("/api/events");
  evtSource.onmessage = (e) => {
    if (!e.data) return;
    try { handleEvent(JSON.parse(e.data)); } catch (err) {}
  };
  evtSource.onerror = () => {
    document.body.classList.add("offline");
    setTimeout(startSSE, 3000);
  };
  evtSource.onopen = () => { document.body.classList.remove("offline"); };
}
function handleEvent(msg) {
  if (msg.type === "system") state.system = msg.data;
  else if (msg.type === "esp") state.esp = msg.data;
  else if (msg.type === "online") state.online = msg.data;
  else if (msg.type === "error") toast("Fehler: " + (msg.data.klasse||""), "warn");
  else if (msg.type === "event") {
    if (msg.data.drucker) {
      toast("Drucker " + msg.data.drucker + " fertig gewechselt", "success");
      state.events.unshift({
        ts: Date.now()/1000,
        text: "Drucker " + msg.data.drucker + " erfolgreich gewechselt",
      });
      state.events = state.events.slice(0, 20);
    }
  }
  render();
}

document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const target = btn.dataset.tab;
    document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
    document.getElementById("page-" + target).classList.add("active");
    if (target === "service") {
      api("/api/cmd/service/modus", { aktiv: true });
    } else if (state.system.system_state === "SERVICE") {
      api("/api/cmd/service/modus", { aktiv: false });
    }
  });
});

function render() {
  const sys = state.system || {};
  const esp = state.esp || {};
  const sysState = sys.system_state || "INIT";

  const dot = document.getElementById("dotMqtt");
  const lbl = document.getElementById("connLabel");
  if (state.online && esp.connected) {
    dot.className = "dot online"; lbl.textContent = "Pi & ESP online";
  } else if (state.online) {
    dot.className = "dot online"; lbl.textContent = "Pi online · ESP getrennt";
  } else {
    dot.className = "dot"; lbl.textContent = "Pi offline";
  }

  const banner = document.getElementById("statusBanner");
  banner.className = "banner " + (STATE_CLASS[sysState] || "");
  document.getElementById("statusText").textContent = STATE_TEXT[sysState] || sysState;

  let sub = "";
  if (sysState === "PLATTENWECHSEL" && sys.aktiver_drucker)
    sub = "Drucker " + sys.aktiver_drucker + " wird gewechselt";
  else if (sysState === "BEREITSCHAFT") {
    const q = sys.queue_length || 0;
    sub = q===0 ? "System bereit" : (q + " Auftrag" + (q===1?"":"e") + " in Queue");
  } else if (sysState === "FEHLER" && sys.fehler) sub = sys.fehler.klasse;
  document.getElementById("statusSub").textContent = sub;

  document.getElementById("posX").textContent = (esp.x_mm ?? "—") + " mm";
  document.getElementById("posZ").textContent = (esp.z_mm ?? "—") + " mm";
  setKv("kvRef", esp.referenced ? "ja" : "nein", esp.referenced ? "yes" : "no");
  setKv("kvPlate", esp.has_plate ? "ja" : "nein", esp.has_plate ? "yes" : "no");
  setKv("kvObst", esp.obstacle_ok ? "frei" : "ALARM",
        esp.obstacle_ok ? "yes" : "alarm");

  const printerList = document.getElementById("printerList");
  printerList.innerHTML = "";
  const ds = sys.drucker_status || {};
  const druckers = sys.drucker_config || [];
  if (druckers.length === 0) {
    printerList.innerHTML = '<div style="color:var(--text-mute);text-align:center;padding:14px;">— kein Drucker konfiguriert —</div>';
  }
  druckers.forEach(dc => {
    const status = ds[dc.id] || "bereit";
    const row = document.createElement("div");
    row.className = "printer-row " + status;
    row.innerHTML = `
      <div class="pr-name">${dc.name || "Drucker " + dc.id}</div>
      <div class="pr-state ${status}">${DRUCKER_STATUS_TEXT[status] || status}</div>`;
    printerList.appendChild(row);
  });

  const queueList = document.getElementById("queueList");
  queueList.innerHTML = "";
  const q = sys.queue || [];
  if (q.length === 0) {
    queueList.innerHTML = '<li class="empty">— keine Aufträge —</li>';
  } else {
    q.forEach(a => {
      const li = document.createElement("li");
      li.textContent = `#${a.id}  Drucker ${a.drucker}  (${a.quelle})`;
      queueList.appendChild(li);
    });
  }

  const grid = document.getElementById("printerGrid");
  grid.innerHTML = "";
  const kannKlicken = !sys.fehler && esp.connected
    && (sysState === "BEREITSCHAFT" || sysState === "PLATTENWECHSEL");
  if (druckers.length === 0) {
    grid.innerHTML = '<div style="color:var(--text-mute);text-align:center;padding:30px;">Noch kein Drucker konfiguriert.<br>Geh zum <strong>Drucker</strong>-Tab um einen hinzuzufügen.</div>';
  }
  druckers.forEach(dc => {
    const status = ds[dc.id] || "bereit";
    const card = document.createElement("div");
    card.className = "printer-card " + status;
    let badge = "BEREIT", sub = "bereit für Auftrag";
    if (status === "in_queue") { badge = "WARTET"; sub = "in Warteschlange"; }
    else if (status === "aktiv") { badge = "AKTIV"; sub = "wird gewechselt"; }
    else if (status === "druckt") { badge = "DRUCKT"; sub = "Drucker arbeitet"; }
    const enabled = kannKlicken && status === "bereit";
    card.innerHTML = `
      <div class="pc-head">
        <div class="pc-name">${dc.name || "Drucker " + dc.id}</div>
        <div class="pc-badge ${status}">${badge}</div>
      </div>
      <div class="pc-state ${status}">${sub}</div>
      <button class="btn btn-primary" ${enabled?"":"disabled"} data-did="${dc.id}">
        ${enabled ? "Plattenwechsel starten"
                  : (status==="in_queue"?"In der Queue"
                    :status==="aktiv"?"Wird gewechselt …":"nicht verfügbar")}
      </button>`;
    card.querySelector("button").addEventListener("click", async () => {
      const r = await api("/api/cmd/auftrag", { drucker_id: dc.id });
      if (r.ok) toast("Auftrag angenommen — Drucker " + dc.id, "success");
      else toast("Auftrag konnte nicht gesendet werden", "warn");
    });
    grid.appendChild(card);
  });

  const serviceAktiv = sysState === "SERVICE";
  const sb = document.getElementById("serviceBanner");
  sb.className = "service-banner" + (serviceAktiv ? " active" : "");
  sb.textContent = serviceAktiv
    ? "Service-Modus aktiv. Schlitten kann manuell zu Positionen gefahren werden."
    : "Service-Modus inaktiv. Aktiviere ihn um den Schlitten zu bewegen.";
  document.getElementById("btnServiceModus").textContent =
    serviceAktiv ? "Service-Modus beenden" : "Service-Modus aktivieren";
  document.querySelectorAll(".pos-btn").forEach(b => { b.disabled = !serviceAktiv; });

  const sd = document.getElementById("serviceDruckerButtons");
  sd.innerHTML = "";
  if (druckers.length === 0) {
    sd.innerHTML = '<div style="color:var(--text-mute);">— kein Drucker konfiguriert —</div>';
  }
  druckers.forEach(dc => {
    const b = document.createElement("button");
    b.className = "btn"; b.textContent = dc.name || "Drucker " + dc.id;
    b.disabled = !serviceAktiv;
    b.addEventListener("click", async () => {
      const r = await api("/api/cmd/service/drucker", { drucker_id: dc.id });
      if (r.ok) toast("→ " + (dc.name || "Drucker " + dc.id));
    });
    sd.appendChild(b);
  });

  renderDruckerTab(druckers);

  const fb = document.getElementById("fehlerBadge");
  const errCard = document.getElementById("errorCard");
  const f = sys.fehler;
  if (f) {
    fb.style.display = "inline-block";
    errCard.className = "error-card active";
    document.getElementById("errorClass").textContent = f.klasse || "Fehler";
    document.getElementById("errorMsg").textContent = f.nachricht || "";
    let meta = "Zeit: " + new Date(f.timestamp*1000).toLocaleTimeString();
    if (f.esp_code) meta += "  ·  ESP-Code: " + f.esp_code;
    if (f.quittiert) meta += "  ·  ✓ quittiert";
    document.getElementById("errorMeta").textContent = meta;
    document.getElementById("btnQuittieren").disabled = !!f.quittiert;
  } else {
    fb.style.display = "none";
    errCard.className = "error-card";
    document.getElementById("errorClass").textContent = "Kein aktiver Fehler";
    document.getElementById("errorMsg").textContent = "Das System läuft normal.";
    document.getElementById("errorMeta").textContent = "";
    document.getElementById("btnQuittieren").disabled = true;
  }

  const evList = document.getElementById("eventList");
  evList.innerHTML = "";
  if (state.events.length === 0) {
    evList.innerHTML = '<li class="empty">— keine Ereignisse —</li>';
  } else {
    state.events.forEach(e => {
      const li = document.createElement("li");
      const t = new Date(e.ts*1000).toLocaleTimeString();
      li.textContent = "[" + t + "] " + e.text;
      evList.appendChild(li);
    });
  }
}

function setKv(id, v, cls) {
  const el = document.getElementById(id);
  el.textContent = v;
  el.className = "kv-value " + (cls || "");
}

function renderDruckerTab(druckers) {
  const list = document.getElementById("druckerList");
  list.innerHTML = "";
  if (druckers.length === 0) {
    list.innerHTML = '<div style="color:var(--text-mute);text-align:center;padding:30px;">— kein Drucker konfiguriert —</div>';
    return;
  }
  druckers.forEach(dc => {
    const card = document.createElement("div");
    card.className = "drucker-edit-card";
    card.innerHTML = `
      <div class="drucker-edit-head">
        <div>
          <div class="drucker-edit-name">${dc.name || "Drucker " + dc.id}</div>
          <div class="drucker-edit-id">ID ${dc.id} · Pin ${dc.pin_fertig||"—"}</div>
        </div>
      </div>
      <div class="drucker-row"><div class="info">
        <div class="name">X-Position</div>
        <div class="meta">${dc.pos_x} mm</div></div></div>
      <div class="drucker-row"><div class="info">
        <div class="name">Z Anfahrt (sicher)</div>
        <div class="meta">${dc.pos_z_anfahr} mm</div></div></div>
      <div class="drucker-row"><div class="info">
        <div class="name">Z Türarm-Höhe</div>
        <div class="meta">${dc.pos_z_tuer} mm</div></div></div>
      <div class="drucker-row"><div class="info">
        <div class="name">Z Druckbett</div>
        <div class="meta">${dc.pos_z_druckbett} mm</div></div></div>
      <div class="drucker-row">
        <div class="info">
          <div class="name">Türarm-Hub</div>
          <div class="meta">${dc.door_arm_hub_mm} mm</div>
        </div>
        <div class="actions">
          <button class="btn" data-edit="${dc.id}">Bearbeiten</button>
          <button class="btn" data-delete="${dc.id}">Entfernen</button>
        </div>
      </div>`;
    card.querySelector('[data-edit]').addEventListener("click",
      () => openDruckerModal(dc));
    card.querySelector('[data-delete]').addEventListener("click",
      () => deleteDrucker(dc));
    list.appendChild(card);
  });
}

function openDruckerModal(dc) {
  document.getElementById("druckerModalTitle").textContent =
    dc ? `Drucker ${dc.id} bearbeiten` : "Neuen Drucker hinzufügen";
  document.getElementById("f_name").value = dc?.name || "";
  document.getElementById("f_pin").value = dc?.pin_fertig ?? 0;
  document.getElementById("f_pos_x").value = dc?.pos_x ?? 0;
  document.getElementById("f_anfahr").value = dc?.pos_z_anfahr ?? 0;
  document.getElementById("f_tuer").value = dc?.pos_z_tuer ?? 0;
  document.getElementById("f_bett").value = dc?.pos_z_druckbett ?? 0;
  document.getElementById("f_hub").value = dc?.door_arm_hub_mm ?? 50;
  document.getElementById("druckerModal").classList.add("show");
  document.getElementById("druckerModal").dataset.editId = dc?.id || "";
}

function closeDruckerModal() {
  document.getElementById("druckerModal").classList.remove("show");
}

async function saveDruckerModal() {
  const editId = document.getElementById("druckerModal").dataset.editId;
  const data = {
    name: document.getElementById("f_name").value || null,
    pin_fertig: parseInt(document.getElementById("f_pin").value) || 0,
    pos_x: parseInt(document.getElementById("f_pos_x").value) || 0,
    pos_z_anfahr: parseInt(document.getElementById("f_anfahr").value) || 0,
    pos_z_tuer: parseInt(document.getElementById("f_tuer").value) || 0,
    pos_z_druckbett: parseInt(document.getElementById("f_bett").value) || 0,
    door_arm_hub_mm: parseInt(document.getElementById("f_hub").value) || 50,
  };
  if (editId) data.id = parseInt(editId);
  const r = await api("/api/cmd/drucker/setzen", data);
  if (r.ok) {
    toast(editId ? "Gespeichert" : "Hinzugefügt", "success");
    closeDruckerModal();
  }
}

async function deleteDrucker(dc) {
  if (!confirm(`Drucker ${dc.id} (${dc.name || ""}) wirklich entfernen?`)) return;
  const r = await api("/api/cmd/drucker/entfernen", { id: dc.id });
  if (r.ok) toast("Entfernt: Drucker " + dc.id);
}

document.getElementById("btnStop").addEventListener("click", async () => {
  await api("/api/cmd/stop"); toast("STOP gesendet");
});
document.getElementById("btnQuittieren").addEventListener("click", async () => {
  const r = await api("/api/cmd/quittieren");
  if (r.ok) toast("Fehler quittiert", "success");
});
document.getElementById("btnReferenzfahrt").addEventListener("click", async () => {
  if (!confirm("Referenzfahrt jetzt durchführen?")) return;
  const r = await api("/api/cmd/referenzfahrt");
  if (r.ok) toast("Referenzfahrt gestartet");
});
document.getElementById("btnServiceModus").addEventListener("click", async () => {
  const aktiv = state.system.system_state !== "SERVICE";
  await api("/api/cmd/service/modus", { aktiv });
  toast(aktiv ? "Service-Modus aktiviert" : "Service-Modus beendet");
});
document.querySelectorAll(".pos-btn").forEach(btn => {
  btn.addEventListener("click", async () => {
    const ziel = btn.dataset.ziel;
    const r = await api("/api/cmd/service/fahre", { ziel });
    if (r.ok) toast("Fahre zu: " + btn.textContent);
  });
});
document.getElementById("btnDruckerHinzufuegen").addEventListener("click", () => {
  openDruckerModal(null);
});
document.getElementById("btnDruckerCancel").addEventListener("click", closeDruckerModal);
document.getElementById("btnDruckerSpeichern").addEventListener("click", saveDruckerModal);
document.getElementById("druckerModal").addEventListener("click", (e) => {
  if (e.target === document.getElementById("druckerModal")) closeDruckerModal();
});

let toastTimeout = null;
function toast(text, kind="") {
  const t = document.getElementById("toast");
  t.textContent = text; t.className = "toast show " + kind;
  if (toastTimeout) clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => { t.className = "toast " + kind; }, 2500);
}

fetchInitial();
startSSE();
