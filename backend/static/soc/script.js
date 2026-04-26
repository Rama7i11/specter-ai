const statusUrl = "http://localhost:8000/api/status";
const alertsUrl = "http://localhost:8000/api/alerts";
const defensesUrl = "http://localhost:8000/api/defenses";
const pagerDutyUrl = "http://localhost:8000/api/pagerduty-incidents";
const historyUrl = "http://localhost:8000/api/history";
const tampaFallback = { lat: 27.9506, lon: -82.4572, city: "Tampa", country: "US" };
const specterWaveTickMs = 130;

const liveClock = document.getElementById("liveClock");
const specterBadge = document.getElementById("specterBadge");
const specterModeText = document.getElementById("specterModeText");
const specterHint = document.getElementById("specterHint");
const specterWaveBars = Array.from(document.querySelectorAll("#specterWave .wave-bar"));

const mapPinCount = document.getElementById("mapPinCount");
const alertsFeed = document.getElementById("alertsFeed");
const alertsCount = document.getElementById("alertsCount");
const alertsTodayValue = document.getElementById("alertsTodayValue");
const blockedIpsValue = document.getElementById("blockedIpsValue");
const lockedUsersValue = document.getElementById("lockedUsersValue");
const headingTextEl = document.querySelector(".heading-text");
const blockedList = document.getElementById("blockedList");
const lockedList = document.getElementById("lockedList");
const defenseLog = document.getElementById("defenseLog");
const pagerDutyCount = document.getElementById("pagerDutyCount");
const pagerDutyList = document.getElementById("pagerDutyList");
const historyCount = document.getElementById("historyCount");
const historyTotalAlerts = document.getElementById("historyTotalAlerts");
const historyTotalDefenses = document.getElementById("historyTotalDefenses");
const historyFeed = document.getElementById("historyFeed");
const archiveModal = document.getElementById("archiveModal");
const openArchiveBtn = document.getElementById("openArchiveBtn");
const archiveSummary = document.getElementById("archiveSummary");
const archiveAlertsEl = document.getElementById("archiveAlerts");
const archiveDefensesEl = document.getElementById("archiveDefenses");
const archivePagerDutyEl = document.getElementById("archivePagerDuty");
const revealTargets = Array.from(document.querySelectorAll("[data-reveal]"));
const overlay = document.querySelector(".shape-overlays");
const paths = overlay ? overlay.querySelectorAll(".shape-overlays__path") : [];
const hasGsap = typeof window.gsap !== "undefined";
const CountUpCtor = window.countUp?.CountUp;

const numPoints = 10;
const numPaths = paths.length;
const delayPointsMax = 0.3;
const delayPerPath = 0.25;
const duration = 0.9;
const scrambleChars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
const headingOriginalText = headingTextEl?.textContent?.trim() ?? "";
const SVG_NS = "http://www.w3.org/2000/svg";

const state = {
  seenAlerts: new Set(),
  alertMarkers: new Map(),
  alerts: [],
  defenses: [],
  pagerDutyIncidents: [],
  status: null,
  counters: {
    alertsToday: 0,
    blockedIps: 0,
    lockedUsers: 0,
    historyAlerts: 0,
    historyDefenses: 0
  },
  specter: {
    mode: "ASLEEP",
    voiceLevel: Number.NaN,
    heartbeatSeconds: Number.NaN
  },
  overlay: {
    isOpened: false,
    pointsDelay: [],
    allPoints: []
  }
};

const map = L.map("threatMap", {
  zoomControl: false,
  worldCopyJump: false,
  minZoom: 2,
  maxBounds: [
    [-85, -180],
    [85, 180]
  ],
  maxBoundsViscosity: 1.0,
  inertia: true
}).setView([20, 0], 2.2);

L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png", {
  subdomains: "abcd",
  maxZoom: 19,
  noWrap: true,
  bounds: [
    [-85, -180],
    [85, 180]
  ],
  attribution: "&copy; OpenStreetMap, &copy; CARTO"
}).addTo(map);

function setClock() {
  const now = new Date();
  liveClock.textContent = now.toLocaleTimeString("en-US", { hour12: false });
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function normalizeSpecterMode(rawMode) {
  const normalized = String(rawMode ?? "").trim().toUpperCase();
  const map = {
    ASLEEP: "ASLEEP",
    IDLE: "ASLEEP",
    OFFLINE: "ASLEEP",
    SLEEP: "ASLEEP",
    LISTENING: "LISTENING",
    RECORDING: "LISTENING",
    THINKING: "THINKING",
    ANALYZING: "THINKING",
    ANALYSING: "THINKING",
    PROCESSING: "THINKING",
    HACKING: "HACKING",
    ACTIVE: "HACKING",
    RESPONDING: "HACKING"
  };
  return map[normalized] ?? "";
}

function inferSpecterMode(statusPayload, dialRaw, heartbeatSeconds) {
  const explicit =
    normalizeSpecterMode(
      statusPayload?.specter_mode ??
        statusPayload?.assistant_mode ??
        statusPayload?.assistant_state ??
        statusPayload?.voice_state
    ) || "";
  if (explicit) return explicit;

  if (dialRaw === "MONITOR") return "HACKING";
  if (dialRaw === "ALERT_ONLY") return "THINKING";
  if (dialRaw === "DEFENSE_READY") return heartbeatSeconds < 6 ? "LISTENING" : "ASLEEP";
  return "ASLEEP";
}

function setSpecterMode(mode, voiceLevel, heartbeatSeconds) {
  const normalized = normalizeSpecterMode(mode) || "ASLEEP";
  const infoMap = {
    ASLEEP: {
      className: "specter-asleep",
      label: "Asleep",
      hint: "Awaiting voice channel..."
    },
    LISTENING: {
      className: "specter-listening",
      label: "Listening",
      hint: Number.isFinite(heartbeatSeconds)
        ? `Mic hot · ${Math.max(0, Math.floor(heartbeatSeconds))}s heartbeat`
        : "Mic hot · Listening..."
    },
    THINKING: {
      className: "specter-thinking",
      label: "Analyzing",
      hint: "Parsing command intent..."
    },
    HACKING: {
      className: "specter-hacking",
      label: "Hacking",
      hint: "Executing defensive actions..."
    }
  };
  const info = infoMap[normalized];
  const changed = state.specter.mode !== normalized;

  if (specterBadge && specterModeText && specterHint) {
    specterBadge.classList.remove(
      "specter-asleep",
      "specter-listening",
      "specter-thinking",
      "specter-hacking"
    );
    specterBadge.classList.add(info.className);
    specterModeText.textContent = info.label;
    specterHint.textContent = info.hint;

    if (changed && hasGsap) {
      gsap.fromTo(
        specterBadge,
        { scale: 0.94, opacity: 0.7 },
        { scale: 1, opacity: 1, duration: 0.3, ease: "power2.out" }
      );
    }
  }

  state.specter.mode = normalized;
  state.specter.voiceLevel = Number.isFinite(voiceLevel) ? clamp(voiceLevel, 0, 1) : Number.NaN;
  state.specter.heartbeatSeconds = heartbeatSeconds;
}

function tickSpecterWave() {
  if (!specterWaveBars.length) return;

  const mode = state.specter.mode;
  const now = performance.now() / 220;
  const baseByMode = {
    ASLEEP: 0.12,
    LISTENING: 0.42,
    THINKING: 0.54,
    HACKING: 0.72
  };
  const modeBase = baseByMode[mode] ?? 0.18;
  const level =
    Number.isFinite(state.specter.voiceLevel) && mode !== "ASLEEP"
      ? Math.max(modeBase, state.specter.voiceLevel)
      : modeBase;

  specterWaveBars.forEach((bar, index) => {
    const phase = Math.abs(Math.sin(now + index * 0.82));
    const jitter = Math.random() * 0.1;
    let magnitude = 0.16 + phase * (0.65 * level) + jitter;
    if (mode === "ASLEEP") magnitude = 0.1 + phase * 0.12;
    magnitude = clamp(magnitude, 0.08, 1);

    bar.style.transform = `scaleY(${magnitude.toFixed(3)})`;
    bar.style.opacity = mode === "ASLEEP" ? "0.42" : "0.95";
  });
}

function setWearableStatus(statusPayload) {
  const dialRaw = statusPayload?.dial_position ?? statusPayload?.dial ?? "UNKNOWN";
  const heartbeatSeconds = Number(
    statusPayload?.heartbeat_age_s ??
      statusPayload?.heartbeat_seconds_ago ??
      statusPayload?.heartbeat ??
      Number.NaN
  );
  const voiceLevel = Number(
    statusPayload?.voice_level ??
      statusPayload?.audio_level ??
      statusPayload?.assistant_volume ??
      Number.NaN
  );
  const specterMode = inferSpecterMode(statusPayload, dialRaw, heartbeatSeconds);

  setSpecterMode(specterMode, voiceLevel, heartbeatSeconds);
}

function parseTimestamp(value) {
  if (!value) return Date.now();
  const numeric = Number(value);
  if (Number.isFinite(numeric) && numeric > 100000) {
    return numeric;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : Date.now();
}

function relativeTime(ms) {
  const seconds = Math.max(0, Math.floor((Date.now() - ms) / 1000));
  if (seconds < 60) return `${seconds} sec ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours} hr ago`;
}

function isPrivateIp(ip = "") {
  if (ip.startsWith("192.168.")) return true;
  if (ip.startsWith("10.")) return true;
  if (ip.startsWith("172.")) return true;
  if (ip.startsWith("127.")) return true;
  return false;
}

function normalizeAlerts(alertPayload) {
  const list = Array.isArray(alertPayload) ? alertPayload : alertPayload?.alerts ?? [];
  return list
    .map((raw, index) => {
      const timestampMs = parseTimestamp(raw.timestamp ?? raw.created_at ?? raw.time);
      const ip = raw.ip ?? raw.source_ip ?? raw.attacker_ip ?? "unknown";
      const id =
        raw.id ??
        `${ip}-${raw.type ?? raw.attack_type ?? "UNKNOWN"}-${timestampMs}-${String(index)}`;
      const severity = Number(raw.severity ?? raw.severity_score ?? 5);

      let lat = Number(raw.lat ?? raw.latitude ?? raw.geo?.lat ?? raw.location?.lat);
      let lon = Number(raw.lon ?? raw.lng ?? raw.longitude ?? raw.geo?.lon ?? raw.location?.lon);
      const city = raw.city ?? raw.geo?.city ?? raw.location?.city ?? "";
      const country = raw.country ?? raw.geo?.country ?? raw.location?.country ?? "";

      if (!Number.isFinite(lat) || !Number.isFinite(lon) || isPrivateIp(ip)) {
        lat = tampaFallback.lat;
        lon = tampaFallback.lon;
      }

      return {
        id,
        type: raw.type ?? raw.attack_type ?? "UNKNOWN",
        ip,
        severity,
        timestampMs,
        city: city || tampaFallback.city,
        country: country || tampaFallback.country,
        lat,
        lon
      };
    })
    .sort((a, b) => b.timestampMs - a.timestampMs);
}

function severityClass(level) {
  if (level >= 9) return "sev-high";
  if (level >= 7) return "sev-medium";
  return "sev-low";
}

function placeAlertPin(alert) {
  if (state.alertMarkers.has(alert.id)) return;

  const icon = L.divIcon({
    html: "<span class='attack-marker pulsing'></span>",
    className: "",
    iconSize: [14, 14],
    iconAnchor: [7, 7]
  });

  const marker = L.marker([alert.lat, alert.lon], { icon }).addTo(map);
  const popupTime = new Date(alert.timestampMs).toLocaleTimeString("en-US", { hour12: false });

  marker.bindPopup(
    `<strong>${alert.type}</strong><br/>IP: ${alert.ip}<br/>Time: ${popupTime}<br/>Severity: ${alert.severity}`
  );

  state.alertMarkers.set(alert.id, marker);

  setTimeout(() => {
    const markerEl = marker.getElement()?.querySelector(".attack-marker");
    if (markerEl) markerEl.classList.remove("pulsing");
  }, 2200);
}

function renderAlerts(alerts) {
  const latestEight = alerts.slice(0, 8);
  alertsFeed.innerHTML = "";

  latestEight.forEach((alert) => {
    const isNew = !state.seenAlerts.has(alert.id);
    state.seenAlerts.add(alert.id);

    const alertCard = document.createElement("article");
    alertCard.className = `alert-item ${isNew ? "is-new" : ""}`;
    alertCard.innerHTML = `
      <div class="alert-row">
        <span class="severity ${severityClass(alert.severity)}">SEV ${alert.severity}</span>
        <span class="alert-type">${alert.type}</span>
      </div>
      <p class="alert-meta">From: ${alert.ip} · ${alert.city}, ${alert.country}</p>
      <p class="alert-time" data-time="${alert.timestampMs}">${relativeTime(alert.timestampMs)}</p>
    `;
    alertsFeed.appendChild(alertCard);

    placeAlertPin(alert);
  });

  alertsCount.textContent = `${alerts.length} alerts`;
  mapPinCount.textContent = `${state.alertMarkers.size} active pins`;

  if (!latestEight.length) {
    alertsFeed.innerHTML = "<div class='empty-state'>No active alerts. Sensors armed and monitoring...</div>";
  }

  if (hasGsap) {
    gsap.fromTo(
      ".alert-item.is-new",
      { y: -18, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.4, stagger: 0.05, ease: "power2.out" }
    );
  }
}

function renderList(targetEl, values, emptyText) {
  targetEl.innerHTML = "";
  if (!values.length) {
    targetEl.innerHTML = `<li>${emptyText}</li>`;
    return;
  }

  values.forEach((value) => {
    const li = document.createElement("li");
    li.textContent = value;
    targetEl.appendChild(li);
  });
}

function normalizeDefenses(defensePayload) {
  const commands = Array.isArray(defensePayload)
    ? defensePayload
    : defensePayload?.defenses ?? defensePayload?.commands ?? defensePayload?.logs ?? [];
  const blockedIps = defensePayload?.blocked_ips ?? defensePayload?.blockedIps ?? [];
  const lockedUsers = defensePayload?.locked_users ?? defensePayload?.lockedUsers ?? [];

  return {
    commands: commands
      .map((entry, index) => {
        const timestampMs = parseTimestamp(entry.timestamp ?? entry.time ?? entry.created_at);
        return {
          id: entry.id ?? `cmd-${timestampMs}-${index}`,
          text:
            entry.message ??
            entry.command_text ??
            `${entry.command ?? "Command"} ${entry.target ? `-> ${entry.target}` : ""}`.trim(),
          timestampMs
        };
      })
      .sort((a, b) => b.timestampMs - a.timestampMs),
    blockedIps: Array.isArray(blockedIps) ? blockedIps : [],
    lockedUsers: Array.isArray(lockedUsers) ? lockedUsers : []
  };
}

function renderDefenses(defenseModel) {
  setCounter("blockedIps", blockedIpsValue, defenseModel.blockedIps.length);
  setCounter("lockedUsers", lockedUsersValue, defenseModel.lockedUsers.length);
  renderList(blockedList, defenseModel.blockedIps, "No blocked IPs yet");
  renderList(lockedList, defenseModel.lockedUsers, "No locked users yet");

  defenseLog.innerHTML = "";
  const topFive = defenseModel.commands.slice(0, 5);
  topFive.forEach((entry, index) => {
    const line = document.createElement("div");
    line.className = "terminal-item";
    line.innerHTML = `Cmd ${index + 1} -> ${entry.text} <span class="terminal-time" data-time="${entry.timestampMs}">${relativeTime(entry.timestampMs)}</span>`;
    defenseLog.appendChild(line);
  });

  if (!topFive.length) {
    defenseLog.innerHTML = "<div class='empty-state'>Defense command pipeline idle.</div>";
  }

  if (hasGsap) {
    gsap.fromTo(
      "#defenseLog .terminal-item",
      { x: -10, opacity: 0 },
      { x: 0, opacity: 1, duration: 0.28, stagger: 0.04, ease: "power1.out" }
    );
  }
}

function normalizeIncidents(pagerDutyPayload) {
  const list = Array.isArray(pagerDutyPayload)
    ? pagerDutyPayload
    : pagerDutyPayload?.incidents ?? pagerDutyPayload?.items ?? [];
  return list
    .map((incident, index) => ({
      id: incident.id ?? incident.incident_id ?? `pd-${index}`,
      severity: incident.severity ?? "unknown",
      status: incident.status ?? "Triggered"
    }))
    .slice(0, 8);
}

function renderIncidents(incidents) {
  pagerDutyCount.textContent = `${incidents.length} escalated`;
  pagerDutyList.innerHTML = "";

  incidents.forEach((incident) => {
    const statusClass = `status-${String(incident.status).toLowerCase()}`;
    const item = document.createElement("article");
    item.className = "incident-item";
    item.innerHTML = `
      <strong>${incident.id}</strong>
      <p>Severity: ${incident.severity}</p>
      <p class="${statusClass}">Status: ${incident.status}</p>
    `;
    pagerDutyList.appendChild(item);
  });

  if (!incidents.length) {
    pagerDutyList.innerHTML = "<div class='empty-state'>No escalated incidents.</div>";
  }

  if (hasGsap) {
    gsap.fromTo(
      "#pagerDutyList .incident-item",
      { x: 12, opacity: 0 },
      { x: 0, opacity: 1, duration: 0.3, stagger: 0.04, ease: "power1.out" }
    );
  }
}

function updateRelativeTimeNodes() {
  document.querySelectorAll("[data-time]").forEach((node) => {
    const timestamp = Number(node.dataset.time);
    node.textContent = relativeTime(timestamp);
  });
}

function animateStatNumber(targetEl, value) {
  const safeValue = Number.isFinite(value) ? value : 0;
  if (!CountUpCtor) {
    targetEl.textContent = String(safeValue);
    return;
  }

  const instance = new CountUpCtor(targetEl, safeValue, {
    duration: 0.9,
    useGrouping: false
  });
  if (!instance.error) {
    instance.start();
  } else {
    targetEl.textContent = String(safeValue);
  }
}

function setCounter(name, targetEl, value) {
  const nextValue = Number.isFinite(value) ? value : 0;
  if (state.counters[name] === nextValue) return;
  state.counters[name] = nextValue;
  animateStatNumber(targetEl, nextValue);
}

function ensurePanelGlowBorders() {
  document.querySelectorAll(".panel-glass").forEach((panel) => {
    let svg = panel.querySelector(".panel-glow-container");

    if (!svg) {
      svg = document.createElementNS(SVG_NS, "svg");
      svg.classList.add("panel-glow-container");

      const blurRect = document.createElementNS(SVG_NS, "rect");
      blurRect.setAttribute("pathLength", "100");
      blurRect.classList.add("panel-glow-blur");

      const lineRect = document.createElementNS(SVG_NS, "rect");
      lineRect.setAttribute("pathLength", "100");
      lineRect.classList.add("panel-glow-line");

      svg.appendChild(blurRect);
      svg.appendChild(lineRect);
      panel.appendChild(svg);
    }

    const rx = getComputedStyle(panel).borderRadius || "16px";
    svg.querySelectorAll("rect").forEach((rect) => rect.setAttribute("rx", rx));
  });
}

function scrambleRevealText(el, finalText, options = {}) {
  if (!el || !hasGsap) return;

  const durationSeconds = options.duration ?? 2.2;
  const revealDelay = options.revealDelay ?? 0.15;
  const progressProxy = { value: 0 };
  const totalChars = finalText.length;

  gsap.to(progressProxy, {
    value: 1,
    duration: durationSeconds,
    ease: "power2.inOut",
    delay: revealDelay,
    overwrite: true,
    onUpdate: () => {
      const revealCount = Math.floor(progressProxy.value * totalChars);
      let nextText = "";

      for (let i = 0; i < totalChars; i += 1) {
        const targetChar = finalText[i];
        if (targetChar === " ") {
          nextText += " ";
          continue;
        }

        if (i < revealCount) {
          nextText += targetChar;
        } else {
          const randomIdx = Math.floor(Math.random() * scrambleChars.length);
          nextText += scrambleChars[randomIdx];
        }
      }

      el.textContent = nextText;
    },
    onComplete: () => {
      el.textContent = finalText;
    }
  });
}

function initShapeOverlay() {
  state.overlay.allPoints = [];
  for (let i = 0; i < numPaths; i += 1) {
    const points = [];
    for (let j = 0; j < numPoints; j += 1) {
      points.push(100);
    }
    state.overlay.allPoints.push(points);
  }
}

function renderShapeOverlay() {
  if (!paths.length) return;

  for (let i = 0; i < numPaths; i += 1) {
    const path = paths[i];
    const points = state.overlay.allPoints[i];

    let d = "";
    d += state.overlay.isOpened ? `M 0 0 V ${points[0]} C` : `M 0 ${points[0]} C`;

    for (let j = 0; j < numPoints - 1; j += 1) {
      const p = ((j + 1) / (numPoints - 1)) * 100;
      const cp = p - ((1 / (numPoints - 1)) * 100) / 2;
      d += ` ${cp} ${points[j]} ${cp} ${points[j + 1]} ${p} ${points[j + 1]}`;
    }

    d += state.overlay.isOpened ? " V 100 H 0" : " V 0 H 0";
    path.setAttribute("d", d);
  }
}

function buildOverlayTimeline(open) {
  const tl = gsap.timeline({
    defaults: {
      ease: "power2.inOut",
      duration
    },
    onUpdate: renderShapeOverlay
  });

  state.overlay.isOpened = open;
  state.overlay.pointsDelay = [];

  for (let i = 0; i < numPoints; i += 1) {
    state.overlay.pointsDelay[i] = Math.random() * delayPointsMax;
  }

  for (let i = 0; i < numPaths; i += 1) {
    const points = state.overlay.allPoints[i];
    const pathDelay = delayPerPath * (open ? i : numPaths - i - 1);

    for (let j = 0; j < numPoints; j += 1) {
      const delay = state.overlay.pointsDelay[j];
      tl.to(
        points,
        {
          [j]: open ? 0 : 100
        },
        delay + pathDelay
      );
    }
  }

  return tl;
}

function runCinematicIntro() {
  if (!hasGsap || !overlay || !paths.length) {
    revealTargets.forEach((el) => {
      el.style.opacity = "1";
      el.style.transform = "none";
      el.style.filter = "none";
    });
    map.invalidateSize();
    return;
  }

  initShapeOverlay();
  renderShapeOverlay();
  gsap.set(overlay, { autoAlpha: 1 });

  const tl = gsap.timeline({
    onComplete: () => {
      map.invalidateSize();
      animateStatNumber(alertsTodayValue, Number(alertsTodayValue.textContent));
      animateStatNumber(blockedIpsValue, Number(blockedIpsValue.textContent));
      animateStatNumber(lockedUsersValue, Number(lockedUsersValue.textContent));
    }
  });

  tl.add(buildOverlayTimeline(true))
    .to(overlay, { autoAlpha: 0, duration: 0.35, ease: "power2.out" }, "-=0.2")
    .fromTo(
      revealTargets,
      { y: 48, opacity: 0, scale: 0.98, filter: "blur(8px)" },
      {
        y: 0,
        opacity: 1,
        scale: 1,
        filter: "blur(0px)",
        stagger: 0.08,
        duration: 0.7,
        ease: "power3.out"
      }
    )
    .call(() => {
      scrambleRevealText(headingTextEl, headingOriginalText, {
        duration: 2.6,
        revealDelay: 0
      });
    }, null, "-=0.35");
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed: ${response.status}`);
  return response.json();
}

function renderHistory(payload) {
  if (!historyFeed) return;
  const archivedAlerts = Array.isArray(payload?.alerts) ? payload.alerts : [];
  const totalAlerts = Number(payload?.total_alerts_ever ?? 0);
  const totalDefenses = Number(payload?.total_defenses_ever ?? 0);

  if (historyCount) historyCount.textContent = `${archivedAlerts.length} archived`;
  setCounter("historyAlerts", historyTotalAlerts, totalAlerts);
  setCounter("historyDefenses", historyTotalDefenses, totalDefenses);

  historyFeed.innerHTML = "";

  if (!archivedAlerts.length) {
    historyFeed.innerHTML =
      "<div class='empty-state'>No archived events yet. Run command 2 to archive current state.</div>";
    return;
  }

  const recent = archivedAlerts
    .map((entry, index) => ({
      type: entry.type ?? entry.attack_type ?? "UNKNOWN",
      ip: entry.ip ?? entry.source_ip ?? "unknown",
      timestampMs: parseTimestamp(entry.timestamp ?? entry.time ?? entry.created_at),
      _idx: index
    }))
    .sort((a, b) => b.timestampMs - a.timestampMs)
    .slice(0, 10);

  recent.forEach((entry) => {
    const item = document.createElement("div");
    item.className = "history-item";
    item.innerHTML =
      `<span class="h-type">[${entry.type}]</span> from ${entry.ip} ` +
      `<span class="terminal-time" data-time="${entry.timestampMs}">${relativeTime(entry.timestampMs)}</span>`;
    historyFeed.appendChild(item);
  });
}

async function fetchHistory() {
  try {
    const payload = await fetchJson(historyUrl);
    renderHistory(payload);
  } catch (err) {
    // Silent — history is non-critical.
  }
}

function renderArchiveModal(payload) {
  const alertsRaw = Array.isArray(payload?.alerts) ? payload.alerts : [];
  const defensesRaw = Array.isArray(payload?.defenses) ? payload.defenses : [];
  const pdRaw = Array.isArray(payload?.pagerduty) ? payload.pagerduty : [];

  if (archiveSummary) {
    archiveSummary.textContent =
      `${alertsRaw.length} alerts · ${defensesRaw.length} defenses · ${pdRaw.length} escalations`;
  }

  if (archiveAlertsEl) {
    archiveAlertsEl.innerHTML = "";
    if (!alertsRaw.length) {
      archiveAlertsEl.innerHTML = "<div class='empty-state'>No archived alerts.</div>";
    } else {
      alertsRaw
        .map((a, i) => ({
          type: a.type ?? "UNKNOWN",
          ip: a.ip ?? "unknown",
          severity: Number(a.severity ?? 5),
          city: a.city ?? a.geo_city ?? "",
          country: a.country ?? a.geo_country ?? "",
          pattern: a.matched_pattern ?? "",
          timestampMs: parseTimestamp(a.timestamp ?? a.created_at ?? a.time),
          _idx: i
        }))
        .sort((x, y) => y.timestampMs - x.timestampMs)
        .forEach((a) => {
          const card = document.createElement("article");
          card.className = "alert-item";
          const loc = [a.city, a.country].filter(Boolean).join(", ");
          card.innerHTML = `
            <div class="alert-row">
              <span class="severity ${severityClass(a.severity)}">SEV ${a.severity}</span>
              <span class="alert-type">${a.type}</span>
            </div>
            <p class="alert-meta">From: ${a.ip}${loc ? ` · ${loc}` : ""}${a.pattern ? ` · ${a.pattern}` : ""}</p>
            <p class="alert-time" data-time="${a.timestampMs}">${relativeTime(a.timestampMs)}</p>
          `;
          archiveAlertsEl.appendChild(card);
        });
    }
  }

  if (archiveDefensesEl) {
    archiveDefensesEl.innerHTML = "";
    if (!defensesRaw.length) {
      archiveDefensesEl.innerHTML = "<div class='empty-state'>No archived defenses.</div>";
    } else {
      defensesRaw
        .map((d, i) => ({
          command: d.command ?? "?",
          action: d.action ?? "",
          result: d.result ?? d.message ?? "",
          ip: d.ip ?? "",
          timestampMs: parseTimestamp(d.timestamp ?? d.time),
          _idx: i
        }))
        .sort((x, y) => y.timestampMs - x.timestampMs)
        .forEach((d) => {
          const line = document.createElement("div");
          line.className = "terminal-item";
          const ipSuffix = d.ip ? ` [${d.ip}]` : "";
          line.innerHTML =
            `Cmd ${d.command} -> ${d.action}${ipSuffix}: ${d.result} ` +
            `<span class="terminal-time" data-time="${d.timestampMs}">${relativeTime(d.timestampMs)}</span>`;
          archiveDefensesEl.appendChild(line);
        });
    }
  }

  if (archivePagerDutyEl) {
    archivePagerDutyEl.innerHTML = "";
    if (!pdRaw.length) {
      archivePagerDutyEl.innerHTML = "<div class='empty-state'>No archived escalations.</div>";
    } else {
      pdRaw.forEach((inc, i) => {
        const id = inc.incident_id ?? inc.id ?? `pd-${i}`;
        const status = inc.status ?? "triggered";
        const summary = inc.summary ?? "";
        const item = document.createElement("article");
        item.className = "incident-item";
        item.innerHTML = `
          <strong>${id}</strong>
          ${summary ? `<p>${summary}</p>` : ""}
          <p class="status-${String(status).toLowerCase()}">Status: ${status}</p>
        `;
        archivePagerDutyEl.appendChild(item);
      });
    }
  }
}

async function openArchiveModal() {
  if (!archiveModal) return;
  try {
    const payload = await fetchJson(historyUrl);
    renderArchiveModal(payload);
  } catch (err) {
    if (archiveSummary) archiveSummary.textContent = "Failed to load archive";
  }
  archiveModal.hidden = false;
  if (hasGsap) {
    gsap.fromTo(
      archiveModal.querySelector(".archive-dialog"),
      { y: 24, opacity: 0, scale: 0.97 },
      { y: 0, opacity: 1, scale: 1, duration: 0.35, ease: "power2.out" }
    );
  }
}

function closeArchiveModal() {
  if (archiveModal) archiveModal.hidden = true;
}

if (openArchiveBtn) {
  openArchiveBtn.addEventListener("click", openArchiveModal);
}
if (archiveModal) {
  archiveModal.addEventListener("click", (event) => {
    if (event.target?.dataset?.archiveClose !== undefined) closeArchiveModal();
  });
}
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && archiveModal && !archiveModal.hidden) closeArchiveModal();
});

async function tick() {
  const [statusResult, alertsResult, defensesResult, pagerDutyResult] = await Promise.allSettled([
    fetchJson(statusUrl),
    fetchJson(alertsUrl),
    fetchJson(defensesUrl),
    fetchJson(pagerDutyUrl)
  ]);

  if (statusResult.status === "fulfilled") {
    state.status = statusResult.value ?? {};
    const alertsToday = Number(
      state.status.alerts_today ?? state.status.alertsToday ?? state.status.total_alerts ?? 0
    );
    setCounter("alertsToday", alertsTodayValue, alertsToday);
    setWearableStatus(state.status);
  }

  if (alertsResult.status === "fulfilled") {
    state.alerts = normalizeAlerts(alertsResult.value);
    renderAlerts(state.alerts);
  }

  if (defensesResult.status === "fulfilled") {
    const defenseModel = normalizeDefenses(defensesResult.value);
    state.defenses = defenseModel.commands;
    renderDefenses(defenseModel);
  }

  if (pagerDutyResult.status === "fulfilled") {
    state.pagerDutyIncidents = normalizeIncidents(pagerDutyResult.value);
    renderIncidents(state.pagerDutyIncidents);
  }

  updateRelativeTimeNodes();
}

function setupExpands() {
  document.querySelectorAll(".expand-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const targetId = button.dataset.target;
      const card = button.closest(".expandable");
      if (!targetId || !card) return;
      card.classList.toggle("expanded");
    });
  });
}

setClock();
setSpecterMode("ASLEEP", Number.NaN, Number.NaN);
tickSpecterWave();
ensurePanelGlowBorders();
setupExpands();
updateRelativeTimeNodes();
runCinematicIntro();
tick();
fetchHistory();

setInterval(() => {
  setClock();
  updateRelativeTimeNodes();
}, 1000);

setInterval(tick, 1000);
setInterval(tickSpecterWave, specterWaveTickMs);
setInterval(fetchHistory, 3000);

window.addEventListener("resize", ensurePanelGlowBorders);