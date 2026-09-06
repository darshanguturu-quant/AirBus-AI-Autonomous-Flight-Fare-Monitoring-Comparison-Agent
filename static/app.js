/**
 * AirBus AI — Autonomous Flight Fare Monitoring Client Logic
 * Handles real-time SSE stream, autonomous countdown, DOM rendering,
 * price trend canvas chart, configuration management, and audit log inspection.
 */

let currentTop5 = [];
let currentDatesComparison = null;
let selectedDateFilter = 'all'; // 'all', or date string
let currentConfig = null;
let viewMode = 'cards'; // 'cards' or 'table'
let timerSeconds = 300;
let timerTotal = 300;
let eventSource = null;

// South Indian airport names lookup
const AIRPORT_NAMES = {
  "MAA": "Chennai", "BLR": "Bengaluru", "HYD": "Hyderabad", "COK": "Kochi",
  "TRV": "Thiruvananthapuram", "CCJ": "Kozhikode", "CNN": "Kannur", "IXE": "Mangaluru",
  "CJB": "Coimbatore", "IXM": "Madurai", "TRZ": "Tiruchirappalli", "VGA": "Vijayawada",
  "VTZ": "Visakhapatnam", "RJA": "Rajahmundry", "TIR": "Tirupati"
};

const DEST_NAMES = {
  "DXB": "Dubai Intl", "SHJ": "Sharjah Intl", "AUH": "Abu Dhabi Intl"
};

document.addEventListener("DOMContentLoaded", () => {
  initApp();
});

async function initApp() {
  await loadConfig();
  await loadTop5();
  await loadHistory();
  await loadAlerts();
  setupSSE();
  // Fallback heartbeat every 15s to guarantee fresh sync
  setInterval(syncStatus, 15000);
}

// SSE Connection
function setupSSE() {
  if (eventSource) {
    eventSource.close();
  }

  eventSource = new EventSource("/api/events");

  eventSource.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      handleLiveEvent(payload);
    } catch (e) {
      console.warn("SSE parse error:", e);
    }
  };

  eventSource.onerror = () => {
    console.warn("SSE connection interrupted. Reconnecting in 5s...");
    eventSource.close();
    setTimeout(setupSSE, 5000);
  };
}

function handleLiveEvent(evt) {
  if (evt.type === "TIMER_TICK") {
    const remaining = evt.data.seconds_remaining;
    const total = evt.data.total_interval || 300;
    updateTimerDisplay(remaining, total);

    if (evt.data.is_scanning) {
      setScanningState(true);
    } else {
      setScanningState(false);
    }
  } else if (evt.type === "SCAN_STARTED") {
    setScanningState(true);
  } else if (evt.type === "SCAN_COMPLETED") {
    setScanningState(false);
    currentTop5 = evt.data.top5 || [];
    currentDatesComparison = evt.data.dates_comparison || null;
    if (currentDatesComparison) {
      renderDatesComparison(currentDatesComparison);
    }
    applyDateFilter();
    renderHUD(evt.data);
    loadHistory();
    loadAlerts();

    if (evt.data.alerts && evt.data.alerts.length > 0) {
      showAlertBanner(evt.data.alerts[0].message);
      playAlertBeep();
    }
  } else if (evt.type === "SCAN_FAILED") {
    setScanningState(false);
    console.error("Scan failed on server:", evt.data);
  }
}

function updateTimerDisplay(remaining, total) {
  timerSeconds = remaining;
  timerTotal = total;
  const mins = Math.floor(remaining / 60);
  const secs = remaining % 60;
  const disp = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  const el = document.getElementById("timer-display");
  if (el) el.textContent = disp;

  const fill = document.getElementById("timer-fill");
  if (fill && total > 0) {
    const pct = ((total - remaining) / total) * 100;
    fill.style.width = `${pct}%`;
  }
}

function setScanningState(isScanning) {
  const btn = document.getElementById("btn-scan-now");
  const text = document.getElementById("scan-btn-text");
  const beacon = document.getElementById("radar-beacon");

  if (btn && text) {
    if (isScanning) {
      btn.classList.add("scanning");
      text.textContent = "Scanning...";
      if (beacon) beacon.classList.add("fast-pulse");
    } else {
      btn.classList.remove("scanning");
      text.textContent = "Scan Now";
      if (beacon) beacon.classList.remove("fast-pulse");
    }
  }
}

async function syncStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    if (data.is_scanning) {
      setScanningState(true);
    }
  } catch (e) {
    // silence
  }
}

async function triggerManualScan() {
  setScanningState(true);
  try {
    const res = await fetch("/api/scan", { method: "POST" });
    const data = await res.json();
    if (data.status === "SUCCESS") {
      await loadTop5();
      await loadHistory();
      await loadAlerts();
    }
  } catch (e) {
    console.error("Manual scan error:", e);
  } finally {
    setScanningState(false);
  }
}

async function loadTop5() {
  try {
    const res = await fetch("/api/top5");
    const data = await res.json();
    currentTop5 = data.top5 || [];
    currentDatesComparison = data.dates_comparison || null;

    if (currentDatesComparison) {
      renderDatesComparison(currentDatesComparison);
    }
    applyDateFilter();
    renderHUD(data);
    updateArbitrageCalculator(currentTop5);
  } catch (e) {
    console.error("Failed to load Top 5:", e);
  }
}

function renderHUD(data) {
  const cheapest = data.top5 && data.top5.length > 0 ? data.top5[0] : null;

  const priceEl = document.getElementById("hud-cheapest-price");
  const routeEl = document.getElementById("hud-cheapest-route");
  const breakdownEl = document.getElementById("hud-cheapest-breakdown");
  const dropEl = document.getElementById("hud-price-drop");
  const dropDetailEl = document.getElementById("hud-price-drop-detail");
  const lastUpdatedEl = document.getElementById("last-updated-text");

  if (cheapest) {
    if (priceEl) priceEl.textContent = `₹${cheapest.total_effective_price.toLocaleString('en-IN')}`;
    if (routeEl) routeEl.textContent = `${cheapest.departure_airport} ➔ ${cheapest.arrival_airport} (${cheapest.airline})`;
    if (breakdownEl) {
      breakdownEl.textContent = `Airfare ₹${cheapest.airfare_total.toLocaleString('en-IN')} + Ground ₹${cheapest.ground_transport_cost}`;
    }

    if (cheapest.price_difference && cheapest.price_difference !== 0) {
      const diff = cheapest.price_difference;
      const pct = cheapest.percentage_change;
      const sign = diff < 0 ? "▼" : "▲";
      if (dropEl) {
        dropEl.textContent = `${sign} ₹${Math.abs(diff).toLocaleString('en-IN')} (${pct}%)`;
        dropEl.style.color = diff < 0 ? "var(--accent-emerald)" : "var(--accent-rose)";
      }
      if (dropDetailEl) dropDetailEl.textContent = `vs previous scan for #${cheapest.rank}`;
    } else {
      if (dropEl) {
        dropEl.textContent = "₹0 (0%)";
        dropEl.style.color = "var(--text-primary)";
      }
      if (dropDetailEl) dropDetailEl.textContent = "Stable vs previous scan";
    }
  }

  if (lastUpdatedEl && data.timestamp) {
    const t = new Date(data.timestamp);
    lastUpdatedEl.textContent = `Last scan: ${t.toLocaleTimeString()}`;
  }
}

// 3 CONSECUTIVE DATES COMPARISON RENDERING
function renderDatesComparison(data) {
  if (!data || !data.consecutive_dates) return;

  const dates = data.consecutive_dates;
  const cheapestMap = data.cheapest_by_date || {};
  const winnerDate = data.overall_cheapest_date;
  const maxSavings = data.max_savings || 0;

  // 1. Update summary text
  const summaryEl = document.getElementById("winner-summary-text");
  if (summaryEl && winnerDate) {
    const winnerObj = cheapestMap[winnerDate];
    const formattedWinnerDate = formatDateReadable(winnerDate);
    const winnerDayOfWeek = getDayOfWeek(winnerDate);
    if (winnerObj && winnerObj.has_flights && maxSavings > 0) {
      summaryEl.innerHTML = `🏆 Cheapest Travel Date: <strong>${winnerDayOfWeek}, ${formattedWinnerDate}</strong> (₹${winnerObj.price.toLocaleString('en-IN')}) — <span style="color: #4ade80; font-weight: 700;">Save ₹${maxSavings.toLocaleString('en-IN')}!</span>`;
    } else if (winnerObj && winnerObj.has_flights) {
      summaryEl.innerHTML = `🏆 Lowest Fare Available on <strong>${winnerDayOfWeek}, ${formattedWinnerDate}</strong>: ₹${winnerObj.price.toLocaleString('en-IN')}`;
    }
  }

  // 2. Render 3 date comparison cards
  const grid = document.getElementById("dates-cards-grid");
  if (grid) {
    grid.innerHTML = dates.map((dt, idx) => {
      const isWinner = dt === winnerDate;
      const info = cheapestMap[dt] || { has_flights: false, price: null };
      const formattedDate = formatDateReadable(dt);
      const dayOfWeek = getDayOfWeek(dt);

      let badgeHtml = '';
      if (isWinner) {
        badgeHtml = `<span class="badge-winner-gold">🏆 CHEAPEST DAY</span>`;
      } else if (info.has_flights && data.overall_cheapest_price && info.price) {
        const diff = Math.round(info.price - data.overall_cheapest_price);
        if (diff > 0) {
          badgeHtml = `<span class="badge-date-diff">+₹${diff.toLocaleString('en-IN')} vs Day ${dates.indexOf(winnerDate) + 1}</span>`;
        }
      }

      const priceDisplay = info.has_flights && info.price
        ? `₹${info.price.toLocaleString('en-IN')}`
        : 'Unavailable';

      const priceSub = info.has_flights
        ? `Airfare ₹${info.airfare.toLocaleString('en-IN')} + Ground ₹${info.ground}`
        : 'No direct live flights';

      const routeText = info.has_flights
        ? `${info.departure_airport} ➔ ${info.arrival_airport} (${info.flight_number || ''})`
        : 'South India ➔ Dubai Area';

      const airlineText = info.has_flights ? info.airline : 'All Airlines';
      const deepLink = info.deep_link || `https://www.google.com/travel/flights?q=flights+from+South+India+to+Dubai+on+${dt}+one+way&curr=INR`;
      const isFilterActive = selectedDateFilter === dt;

      return `
        <div class="date-compare-card ${isWinner ? 'winner-card' : ''}" onclick="filterByDate('${dt}')" title="Click to view Top 5 flights for ${formattedDate}">
          <div class="date-card-header">
            <div class="date-card-title-group">
              <span class="date-card-day-label">Day ${idx + 1} • ${dayOfWeek}</span>
              <div class="date-card-date-str">${formattedDate}</div>
            </div>
            ${badgeHtml}
          </div>

          <div class="date-card-price-box">
            <div class="date-card-price-val">${priceDisplay}</div>
            <div class="date-card-price-sub">${priceSub}</div>
          </div>

          <div class="date-card-route-info">
            <div class="date-card-route-text">✈ ${routeText}</div>
            <div class="date-card-airline-text">${airlineText}</div>
          </div>

          <div class="date-card-actions">
            <button class="btn-date-select ${isFilterActive ? 'active' : ''}" onclick="event.stopPropagation(); filterByDate('${dt}')">
              ${isFilterActive ? '✓ Viewing This Day' : 'View Flights for This Day'}
            </button>
            <a href="${deepLink}" target="_blank" rel="noopener noreferrer" class="btn-book" onclick="event.stopPropagation()" style="padding: 8px 12px; font-size: 0.8rem;" title="Verify live price on Google Flights for ${formattedDate}">
              Google Flights ↗
            </a>
          </div>
        </div>
      `;
    }).join("");
  }

  // 3. Update filter pill labels
  updateFilterPills(dates);
}

function updateFilterPills(dates) {
  const container = document.getElementById("date-filter-pills");
  if (!container || !dates || dates.length === 0) return;

  let pillsHtml = `
    <button class="date-pill ${selectedDateFilter === 'all' ? 'active' : ''}" id="pill-date-all" onclick="filterByDate('all')">
      🔥 All ${dates.length} Dates (Overall Top 5)
    </button>
  `;

  dates.forEach((dt, idx) => {
    const formatted = formatDateReadable(dt);
    const day = getDayOfWeek(dt);
    const isWinner = currentDatesComparison && currentDatesComparison.overall_cheapest_date === dt;
    const winnerTag = isWinner ? ' 🏆' : '';
    pillsHtml += `
      <button class="date-pill ${selectedDateFilter === dt ? 'active' : ''}" id="pill-date-${idx}" onclick="filterByDate('${dt}')">
        Day ${idx + 1} (${day}, ${formatted})${winnerTag}
      </button>
    `;
  });

  container.innerHTML = pillsHtml;
}

function filterByDate(dateKey) {
  selectedDateFilter = dateKey;
  if (currentDatesComparison && currentDatesComparison.consecutive_dates) {
    updateFilterPills(currentDatesComparison.consecutive_dates);
    renderDatesComparison(currentDatesComparison);
  }
  applyDateFilter();
}

function filterByDateIndex(idx) {
  if (currentDatesComparison && currentDatesComparison.consecutive_dates && currentDatesComparison.consecutive_dates[idx]) {
    filterByDate(currentDatesComparison.consecutive_dates[idx]);
  }
}

function applyDateFilter() {
  if (selectedDateFilter === 'all') {
    renderTop5(currentTop5);
  } else {
    // Check if top5_by_date has specific entries for this date
    if (currentDatesComparison && currentDatesComparison.top5_by_date && currentDatesComparison.top5_by_date[selectedDateFilter]) {
      renderTop5(currentDatesComparison.top5_by_date[selectedDateFilter]);
    } else {
      const filtered = currentTop5.filter(f => f.travel_date === selectedDateFilter || (f.departure_datetime && f.departure_datetime.startsWith(selectedDateFilter)));
      renderTop5(filtered);
    }
  }
}

function formatDateReadable(dateStr) {
  if (!dateStr) return '';
  const parts = dateStr.split("-");
  if (parts.length === 3) {
    const year = parseInt(parts[0]);
    const month = parseInt(parts[1]) - 1;
    const day = parseInt(parts[2]);
    const d = new Date(year, month, day);
    return d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric', year: 'numeric' });
  }
  return dateStr;
}

function getDayOfWeek(dateStr) {
  if (!dateStr) return '';
  const parts = dateStr.split("-");
  if (parts.length === 3) {
    const year = parseInt(parts[0]);
    const month = parseInt(parts[1]) - 1;
    const day = parseInt(parts[2]);
    const d = new Date(year, month, day);
    return d.toLocaleDateString('en-IN', { weekday: 'short' });
  }
  return '';
}

function renderTop5(flights) {
  const container = document.getElementById("top5-cards-container");
  const tableBody = document.getElementById("flights-table-body");

  if (!flights || flights.length === 0) {
    if (container) container.innerHTML = `<div class="empty-state">No flights found matching constraints. Try adjusting filters.</div>`;
    if (tableBody) tableBody.innerHTML = `<tr><td colspan="11" class="empty-state">No flights found.</td></tr>`;
    return;
  }

  // 1. Render Cards
  if (container) {
    container.innerHTML = flights.map((f) => renderFlightCard(f)).join("");
  }

  // 2. Render Table View (Section 13)
  if (tableBody) {
    tableBody.innerHTML = flights.map((f) => renderTableRow(f)).join("");
  }
}

function renderFlightCard(f) {
  const rankClass = `rank-${f.rank}`;
  const depCity = AIRPORT_NAMES[f.departure_airport] || f.departure_airport;
  const arrCity = DEST_NAMES[f.arrival_airport] || f.arrival_airport;

  const durationHours = Math.floor(f.duration_minutes / 60);
  const durationMins = f.duration_minutes % 60;
  const durationStr = `${durationHours}h ${durationMins}m`;

  const stopsText = f.stops === 0 ? "Non-stop" : (f.stops === 1 ? `1 Stop (${f.stopover_airports || 'via Hub'})` : `${f.stops} Stops`);
  const stopsClass = f.stops === 0 ? "" : "stops-1";

  // Price Delta badge
  let deltaBadge = `<span class="price-delta-badge new">New</span>`;
  if (f.price_difference && f.price_difference !== 0) {
    const diff = f.price_difference;
    const pct = f.percentage_change;
    const isDown = diff < 0;
    deltaBadge = `
      <span class="price-delta-badge ${isDown ? 'down' : 'up'}">
        ${isDown ? '▼' : '▲'} ₹${Math.abs(diff).toLocaleString('en-IN')} (${pct}%)
      </span>
    `;
  }

  const multiSourceText = f.source_count > 1 ? `Seen on ${f.source_count} approved sources` : "Verified Direct";

  // Departure date formatting
  const travelDateStr = f.travel_date || (f.departure_datetime ? f.departure_datetime.substring(0, 10) : "");
  const formattedFlightDate = formatDateReadable(travelDateStr);
  const dayOfWeek = getDayOfWeek(travelDateStr);
  const dateBadge = travelDateStr ? `<span class="flight-date-tag">📅 ${dayOfWeek}, ${formattedFlightDate}</span>` : '';

  return `
    <article class="flight-card ${rankClass}" id="flight-card-${f.itinerary_id}">
      <div class="card-top-bar">
        <div class="rank-badge-wrap">
          <div class="rank-number">${f.rank}</div>
          <span class="rank-tag">${f.rank === 1 ? '🏆 LOWEST EFFECTIVE COST' : `RANK #${f.rank}`}</span>
          ${dateBadge}
        </div>
        ${deltaBadge}
      </div>

      <!-- Route Timeline -->
      <div class="route-timeline">
        <div class="airport-node">
          <span class="airport-code">${f.departure_airport}</span>
          <span class="airport-city">${depCity}</span>
        </div>

        <div class="flight-path-middle">
          <span class="flight-duration">${durationStr}</span>
          <div class="flight-path-line">
            <span class="flight-path-plane">✈</span>
          </div>
          <span class="flight-stops-badge ${stopsClass}">${stopsText}</span>
        </div>

        <div class="airport-node" style="text-align: right;">
          <span class="airport-code">${f.arrival_airport}</span>
          <span class="airport-city">${arrCity}</span>
        </div>
      </div>

      <!-- Airline & Schedule -->
      <div class="carrier-info">
        <div class="carrier-name">
          <span>${f.airline}</span>
          <span class="flight-code">(${f.flight_number})</span>
        </div>
        <div class="carrier-baggage">
          🧳 ${f.baggage_included || 'Standard Cabin 7kg'}
        </div>
      </div>

      <!-- Price Normalization Breakdown -->
      <div class="cost-breakdown-box">
        <div class="cost-row" style="color: #fff; font-weight: 700; font-size: 0.9rem;">
          <span>Live Airfare on Website:</span>
          <span style="color: #4ade80; font-family: var(--font-heading); font-size: 1.1rem;">₹${f.airfare_total.toLocaleString('en-IN')}</span>
        </div>
        <div class="cost-row" style="font-size: 0.76rem; color: var(--text-muted);">
          <span>Includes mandatory taxes & carrier surcharges</span>
          <span>Exact site price</span>
        </div>
        <div class="cost-row ground-transport">
          <span>Dubai Ground Transport (${f.arrival_airport} ➔ Central Dubai):</span>
          <span>${f.ground_transport_cost === 0 ? '₹0 (Direct)' : `+₹${f.ground_transport_cost.toLocaleString('en-IN')}`}</span>
        </div>
        <div class="total-fare-row">
          <span class="total-fare-label">Total Effective Travel Cost:</span>
          <span class="total-fare-amount">₹${f.total_effective_price.toLocaleString('en-IN')}</span>
        </div>
      </div>

      <!-- Card Action & Multi-Source Links -->
      <div class="card-action-footer">
        <div class="source-badge">
          <span class="source-name-badge">
            <span>🛡️</span> ${f.source_name}
          </span>
          <span class="source-reliability-label">${f.source_type} • Verified Live</span>
        </div>

        <div style="display: flex; gap: 6px; flex-wrap: wrap;">
          <a href="${f.source_url}" target="_blank" rel="noopener noreferrer" class="btn-book" title="Open directly on Google Flights">
            Google Flights ↗
          </a>
          ${f.deep_links && f.deep_links.airline_direct ? `
            <a href="${f.deep_links.airline_direct}" target="_blank" rel="noopener noreferrer" class="btn-book" style="background: rgba(99, 102, 241, 0.15); color: #a5b4fc; border-color: rgba(99, 102, 241, 0.4);" title="Check on official airline site">
              Airline ↗
            </a>
          ` : ''}
          ${f.deep_links && f.deep_links.skyscanner ? `
            <a href="${f.deep_links.skyscanner}" target="_blank" rel="noopener noreferrer" class="btn-book" style="background: rgba(16, 185, 129, 0.15); color: #6ee7b7; border-color: rgba(16, 185, 129, 0.4);" title="Compare on Skyscanner">
              Skyscanner ↗
            </a>
          ` : ''}
        </div>
      </div>
    </article>
  `;
}

function renderTableRow(f) {
  const durationHours = Math.floor(f.duration_minutes / 60);
  const durationMins = f.duration_minutes % 60;
  const durationStr = `${durationHours}h ${durationMins}m`;
  const travelDateStr = f.travel_date || (f.departure_datetime ? f.departure_datetime.substring(0, 10) : "");
  const formattedFlightDate = formatDateReadable(travelDateStr);

  return `
    <tr>
      <td><div class="table-rank-pill">${f.rank}</div></td>
      <td>
        <strong>${f.departure_airport}</strong> <small>(${AIRPORT_NAMES[f.departure_airport] || ''})</small>
        ${travelDateStr ? `<br><span class="flight-date-tag" style="font-size: 0.7rem; padding: 1px 6px;">📅 ${formattedFlightDate}</span>` : ''}
      </td>
      <td><strong>${f.arrival_airport}</strong> <small>(${f.arrival_airport})</small></td>
      <td>${f.airline} <small>(${f.flight_number})</small></td>
      <td>${f.stops === 0 ? 'Non-stop' : `${f.stops} stop`}</td>
      <td>${durationStr}</td>
      <td>₹${f.airfare_total.toLocaleString('en-IN')}</td>
      <td>${f.ground_transport_cost === 0 ? '₹0' : `+₹${f.ground_transport_cost}`}</td>
      <td><strong style="color: var(--accent-cyan);">₹${f.total_effective_price.toLocaleString('en-IN')}</strong></td>
      <td>
        <span class="tag tag-cost">${f.source_name}</span>
      </td>
      <td>
        <div style="display: flex; gap: 4px;">
          <a href="${f.source_url}" target="_blank" rel="noopener noreferrer" class="btn-book" style="padding: 4px 8px; font-size: 0.75rem;">Google Flights ↗</a>
          ${f.deep_links && f.deep_links.airline_direct ? `<a href="${f.deep_links.airline_direct}" target="_blank" rel="noopener noreferrer" class="btn-book" style="padding: 4px 8px; font-size: 0.75rem; background: rgba(99, 102, 241, 0.15); color: #a5b4fc;">Airline ↗</a>` : ''}
        </div>
      </td>
    </tr>
  `;
}

// Section 17 Arbitrage Calculator
function updateArbitrageCalculator(flights) {
  const dxbFlights = flights.filter(f => f.arrival_airport === "DXB");
  const shjFlights = flights.filter(f => f.arrival_airport === "SHJ");
  const auhFlights = flights.filter(f => f.arrival_airport === "AUH");

  const minDxb = dxbFlights.length > 0 ? dxbFlights[0] : null;
  const minShj = shjFlights.length > 0 ? shjFlights[0] : null;
  const minAuh = auhFlights.length > 0 ? auhFlights[0] : null;

  // DXB
  if (minDxb) {
    document.getElementById("arb-dxb-airfare").textContent = `₹${minDxb.airfare_total.toLocaleString('en-IN')}`;
    document.getElementById("arb-dxb-total").textContent = `₹${minDxb.total_effective_price.toLocaleString('en-IN')}`;
  }

  // SHJ
  if (minShj) {
    document.getElementById("arb-shj-airfare").textContent = `₹${minShj.airfare_total.toLocaleString('en-IN')}`;
    document.getElementById("arb-shj-total").textContent = `₹${minShj.total_effective_price.toLocaleString('en-IN')}`;

    if (minDxb && minShj.total_effective_price < minDxb.total_effective_price) {
      const saving = minDxb.total_effective_price - minShj.total_effective_price;
      const pct = ((saving / minDxb.total_effective_price) * 100).toFixed(1);
      document.getElementById("shj-saving-badge").textContent = `SAVES ₹${saving.toLocaleString('en-IN')}`;
      document.getElementById("shj-comparison-text").textContent = `⭐ Flying to Sharjah + ₹500 taxi is ₹${saving.toLocaleString('en-IN')} (${pct}%) cheaper than DXB!`;
    } else {
      document.getElementById("shj-comparison-text").textContent = `Sharjah route competitive with DXB direct.`;
    }
  }

  // AUH
  if (minAuh) {
    document.getElementById("arb-auh-airfare").textContent = `₹${minAuh.airfare_total.toLocaleString('en-IN')}`;
    document.getElementById("arb-auh-total").textContent = `₹${minAuh.total_effective_price.toLocaleString('en-IN')}`;
    document.getElementById("auh-comparison-text").textContent = `Airport express shuttle transfer ~1h 15m to central Dubai.`;
  }
}

// Chart Visualization
async function loadHistory() {
  try {
    const res = await fetch("/api/history");
    const data = await res.json();
    renderTrendChart(data.scans || []);
  } catch (e) {
    console.warn("Failed to load history chart:", e);
  }
}

function renderTrendChart(scans) {
  const canvas = document.getElementById("trendChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;

  ctx.clearRect(0, 0, width, height);

  if (!scans || scans.length === 0) {
    ctx.fillStyle = "#64748b";
    ctx.font = "14px Plus Jakarta Sans";
    ctx.fillText("Price trend points will populate as autonomous 5-minute scans run...", 40, height / 2);
    return;
  }

  // Reverse scans so oldest is left, latest is right
  const chronological = [...scans].reverse();
  const prices = chronological.map(s => s.cheapest_fare).filter(p => p > 0);

  if (prices.length < 2) {
    ctx.fillStyle = "#64748b";
    ctx.font = "14px Plus Jakarta Sans";
    ctx.fillText("Awaiting next scan cycle to plot multi-point trend curve...", 40, height / 2);
    return;
  }

  const minPrice = Math.min(...prices) * 0.95;
  const maxPrice = Math.max(...prices) * 1.05;
  const paddingX = 60;
  const paddingY = 40;

  // Grid Lines
  ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = paddingY + (height - paddingY * 2) * (i / 4);
    ctx.beginPath();
    ctx.moveTo(paddingX, y);
    ctx.lineTo(width - paddingX, y);
    ctx.stroke();

    const labelVal = Math.round(maxPrice - (maxPrice - minPrice) * (i / 4));
    ctx.fillStyle = "#64748b";
    ctx.font = "11px Outfit";
    ctx.fillText(`₹${labelVal.toLocaleString('en-IN')}`, 10, y + 4);
  }

  // Plot Line
  const stepX = (width - paddingX * 2) / (prices.length - 1);
  const points = prices.map((price, idx) => {
    const x = paddingX + idx * stepX;
    const y = paddingY + (1 - (price - minPrice) / (maxPrice - minPrice)) * (height - paddingY * 2);
    return { x, y, price };
  });

  // Gradient fill under curve
  const gradient = ctx.createLinearGradient(0, paddingY, 0, height - paddingY);
  gradient.addColorStop(0, "rgba(0, 242, 254, 0.3)");
  gradient.addColorStop(1, "rgba(0, 242, 254, 0.0)");

  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let i = 1; i < points.length; i++) {
    ctx.lineTo(points[i].x, points[i].y);
  }
  ctx.lineTo(points[points.length - 1].x, height - paddingY);
  ctx.lineTo(points[0].x, height - paddingY);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();

  // Draw stroke
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let i = 1; i < points.length; i++) {
    ctx.lineTo(points[i].x, points[i].y);
  }
  ctx.strokeStyle = "#00f2fe";
  ctx.lineWidth = 3;
  ctx.stroke();

  // Draw nodes
  points.forEach((pt, i) => {
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, 5, 0, Math.PI * 2);
    ctx.fillStyle = "#fff";
    ctx.fill();
    ctx.strokeStyle = "#00c6ff";
    ctx.lineWidth = 2;
    ctx.stroke();

    // Node label
    ctx.fillStyle = "#bae6fd";
    ctx.font = "11px Outfit";
    ctx.fillText(`₹${pt.price.toLocaleString('en-IN')}`, pt.x - 20, pt.y - 10);
  });
}

// Alerts List
async function loadAlerts() {
  try {
    const res = await fetch("/api/alerts");
    const data = await res.json();
    const container = document.getElementById("alerts-list-container");
    if (!container) return;

    if (!data.alerts || data.alerts.length === 0) {
      container.innerHTML = `<div class="empty-state">No major price drop alerts recorded yet. Continuous monitor active.</div>`;
      return;
    }

    container.innerHTML = data.alerts.map(a => {
      const time = new Date(a.timestamp).toLocaleTimeString();
      let icon = "⭐";
      if (a.alert_type === "NEW_CHEAPEST") icon = "🚨";
      else if (a.alert_type === "PRICE_DROP") icon = "📉";

      return `
        <div class="alert-item">
          <div class="alert-item-left">
            <span style="font-size: 1.2rem;">${icon}</span>
            <span class="alert-item-msg">${a.message}</span>
          </div>
          <span class="alert-item-time">${time}</span>
        </div>
      `;
    }).join("");
  } catch (e) {
    console.warn("Failed to load alerts:", e);
  }
}

// Banner controls
function showAlertBanner(msg) {
  const banner = document.getElementById("alert-banner");
  const text = document.getElementById("alert-banner-text");
  if (banner && text) {
    text.textContent = msg;
    banner.classList.remove("hidden");
  }
}

function dismissBanner() {
  const banner = document.getElementById("alert-banner");
  if (banner) banner.classList.add("hidden");
}

function playAlertBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
    osc.frequency.setValueAtTime(880, ctx.currentTime + 0.1); // A5
    gain.gain.setValueAtTime(0.2, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.35);
    osc.start();
    osc.stop(ctx.currentTime + 0.35);
  } catch (e) {
    // browser audio policies
  }
}

// Config Modal & Airport Pills
async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    const data = await res.json();
    currentConfig = data.config;

    // Populate inputs
    document.getElementById("cfg-travel-date").value = currentConfig.travel_date;
    document.getElementById("cfg-baggage").value = currentConfig.baggage;
    document.getElementById("cfg-max-stops").value = currentConfig.maximum_stops;
    document.getElementById("cfg-max-duration").value = currentConfig.maximum_journey_duration_hours;
    document.getElementById("cfg-refresh-interval").value = currentConfig.refresh_interval_seconds;
    document.getElementById("cfg-alert-threshold").value = currentConfig.alert_price_drop_absolute;

    const gt = currentConfig.ground_transport_costs || {};
    document.getElementById("cfg-gt-dxb").value = gt.DXB !== undefined ? gt.DXB : 0;
    document.getElementById("cfg-gt-shj").value = gt.SHJ !== undefined ? gt.SHJ : 500;
    document.getElementById("cfg-gt-auh").value = gt.AUH !== undefined ? gt.AUH : 1800;

    const groqKeyInput = document.getElementById("cfg-groq-key");
    if (groqKeyInput) {
      groqKeyInput.value = currentConfig.groq_api_key || "";
    }

    // Populate airport pills
    const grid = document.getElementById("airports-checkbox-grid");
    if (grid && data.available_departure_airports) {
      grid.innerHTML = Object.entries(data.available_departure_airports).map(([code, meta]) => {
        const checked = currentConfig.departure_airports.includes(code) ? "checked" : "";
        return `
          <label class="airport-pill-label">
            <input type="checkbox" name="dep_airports" value="${code}" ${checked}>
            <span>${code} (${meta.city})</span>
          </label>
        `;
      }).join("");
    }

    // Populate allowed domains in audit modal
    const allowContainer = document.getElementById("allowlist-tags-container");
    if (allowContainer && data.approved_sources) {
      allowContainer.innerHTML = Object.entries(data.approved_sources).map(([dom, meta]) => {
        return `<span class="allow-tag">${dom} (${meta.name} - ${meta.type})</span>`;
      }).join("");
    }
  } catch (e) {
    console.error("Failed to load config:", e);
  }
}

async function handleConfigSubmit(e) {
  e.preventDefault();
  if (!currentConfig) return;

  const depCheckboxes = document.querySelectorAll("input[name='dep_airports']:checked");
  const selectedAirports = Array.from(depCheckboxes).map(cb => cb.value);

  if (selectedAirports.length === 0) {
    alert("Please select at least 1 departure airport.");
    return;
  }

  const updatedConfig = {
    ...currentConfig,
    travel_date: document.getElementById("cfg-travel-date").value,
    baggage: document.getElementById("cfg-baggage").value,
    maximum_stops: parseInt(document.getElementById("cfg-max-stops").value, 10),
    maximum_journey_duration_hours: parseInt(document.getElementById("cfg-max-duration").value, 10),
    refresh_interval_seconds: parseInt(document.getElementById("cfg-refresh-interval").value, 10),
    alert_price_drop_absolute: parseFloat(document.getElementById("cfg-alert-threshold").value),
    ground_transport_costs: {
      "DXB": parseFloat(document.getElementById("cfg-gt-dxb").value),
      "SHJ": parseFloat(document.getElementById("cfg-gt-shj").value),
      "AUH": parseFloat(document.getElementById("cfg-gt-auh").value)
    },
    groq_api_key: document.getElementById("cfg-groq-key") ? document.getElementById("cfg-groq-key").value.trim() : "",
    departure_airports: selectedAirports
  };

  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updatedConfig)
    });
    if (res.ok) {
      closeModal("config-modal");
      setScanningState(true);
    }
  } catch (e) {
    console.error("Failed to save config:", e);
  }
}

// Audit Logs Modal
async function openAuditModal() {
  openModal('audit-modal');
  try {
    const res = await fetch("/api/audit-logs");
    const data = await res.json();
    const tbody = document.getElementById("audit-logs-body");
    if (!tbody) return;

    if (!data.logs || data.logs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No audit logs recorded yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = data.logs.map(l => `
      <tr>
        <td><strong>${l.source_name}</strong></td>
        <td><code>${l.source_domain}</code></td>
        <td><span class="tag tag-free">Approved</span></td>
        <td><span class="badge ${l.status === 'SUCCESS' ? 'badge-saving' : 'badge-ai'}">${l.status}</span></td>
        <td>${l.response_time_ms} ms</td>
        <td>${l.flights_found} flights</td>
      </tr>
    `).join("");
  } catch (e) {
    console.error("Failed to load audit logs:", e);
  }
}

// View switcher
function setViewMode(mode) {
  viewMode = mode;
  const cardsContainer = document.getElementById("top5-cards-container");
  const tableContainer = document.getElementById("top5-table-container");
  const cardsBtn = document.getElementById("view-cards-btn");
  const tableBtn = document.getElementById("view-table-btn");

  if (mode === "cards") {
    cardsContainer.classList.remove("hidden");
    tableContainer.classList.add("hidden");
    cardsBtn.classList.add("active");
    tableBtn.classList.remove("active");
  } else {
    cardsContainer.classList.add("hidden");
    tableContainer.classList.remove("hidden");
    cardsBtn.classList.remove("active");
    tableBtn.classList.add("active");
  }
}

// Modal helper
function openModal(id) {
  if (id === 'audit-modal') {
    openAuditModal();
    return;
  }
  const m = document.getElementById(id);
  if (m) m.classList.remove("hidden");
}

function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add("hidden");
}
