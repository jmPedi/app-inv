// =========================================================
// CRIPTOACTIVOS (frontend/cripto.js)
// Lógica de la pestaña de criptoactivos. Cargado tras app.js
// (reutiliza formatEur, formatPct, renderBadge, toggleSection).
// El código de fondos (app.js) no se modifica.
// =========================================================

let cryptoChartInstance = null;
let cryptoDoughnutInstance = null;
let globalCryptoData = null;
let currentCryptoView = 'TOTAL';
let currentCryptoTf = 'ALL';

// Mapa símbolo legible -> id CoinGecko (debe coincidir con app/cripto.py)
const SYMBOL_A_COIN = { 'BTC': 'bitcoin', 'ETH': 'ethereum' };

// --- Navegación por pestañas ---
function switchTab(tab) {
  const esFondos = (tab === 'fondos');
  const fondosSection = document.getElementById('fondosSection');
  const criptoSection = document.getElementById('criptoSection');
  const tabFondos = document.getElementById('tabFondos');
  const tabCripto = document.getElementById('tabCripto');

  if (fondosSection) fondosSection.classList.toggle('hidden', !esFondos);
  if (criptoSection) criptoSection.classList.toggle('hidden', esFondos);

  if (tabFondos) tabFondos.classList.toggle('active', esFondos);
  if (tabCripto) tabCripto.classList.toggle('active', !esFondos);

  if (!esFondos) {
    if (!globalCryptoData) {
      loadCryptoData();
    } else {
      renderCryptoCharts();
    }
  }
}

// --- Carga y render de datos ---
async function loadCryptoData() {
  try {
    const res = await fetch('/api/criptoactivos');
    if (!res.ok) throw new Error('Error al conectar con /api/criptoactivos');
    globalCryptoData = await res.json();

    if (!Array.isArray(globalCryptoData.activos)) return;

    renderCryptoKpis(globalCryptoData);
    renderCryptoTable(globalCryptoData.activos);
    renderCryptoOperations(globalCryptoData.operaciones);
    renderCryptoDoughnutChart(globalCryptoData.activos);
    renderCryptoTimeseriesChart();
  } catch (err) {
    console.error(err);
    alert('Error al cargar criptoactivos: ' + err.message);
  }
}

function renderCryptoKpis(d) {
  const t = d.totales;
  document.getElementById('cryptoKpiMarketVal').textContent = formatEur(t.valor_mercado);
  document.getElementById('cryptoKpiInvested').textContent = formatEur(t.invertido);

  const gainElem = document.getElementById('cryptoKpiGain');
  gainElem.textContent = `${formatEur(t.beneficio_eur)} (${formatPct(t.beneficio_pct)})`;
  gainElem.className = `kpi-sub ${t.beneficio_eur >= 0 ? 'positive' : 'negative'}`;

  const gainPctElem = document.getElementById('cryptoKpiGainPct');
  gainPctElem.textContent = formatPct(t.beneficio_pct);
  gainPctElem.className = `kpi-value ${t.beneficio_pct >= 0 ? 'positive' : 'negative'}`;

  document.getElementById('cryptoKpiGainAbs').textContent = `${formatEur(t.beneficio_eur)} de beneficio`;
  document.getElementById('cryptoKpiCount').textContent = t.activos_count;
  document.getElementById('cryptoKpiLastUpdated').textContent = `Actualizado: ${t.actualizado}`;
}

function renderCryptoTable(activos) {
  const tbody = document.getElementById('criptoTableBody');
  if (!tbody) return;
  tbody.innerHTML = activos.map(a => `
    <tr>
      <td>
        <div class="fund-title">${a.symbol_legible} · ${a.name}</div>
        <span class="fund-meta">${a.cantidad} ${a.symbol_legible}</span>
      </td>
      <td><span class="badge-operator">${a.operador || 'N/D'}</span></td>
      <td><strong>${a.cantidad}</strong></td>
      <td>${a.precio_actual > 0 ? a.precio_actual.toFixed(2) + ' €' : 'N/D'}
        <span class="fund-meta">${a.fecha_precio}</span></td>
      <td><strong>${formatEur(a.valor_actual)}</strong></td>
      <td class="${a.beneficio_eur >= 0 ? 'positive' : 'negative'}"><strong>${a.beneficio_eur > 0 ? '+' : ''}${formatEur(a.beneficio_eur)}</strong></td>
      <td>${renderBadge(a.beneficio_pct)}</td>
      <td><strong>${a.peso_pct.toFixed(1)}%</strong></td>
    </tr>
  `).join('');
}

function renderCryptoOperations(ops) {
  const tbody = document.getElementById('criptoOperationsTableBody');
  if (!tbody) return;
  tbody.innerHTML = (ops || []).map(op => `
    <tr>
      <td>${op.fecha}</td>
      <td><span class="badge-type ${String(op.tipo).toLowerCase()}">${op.tipo}</span></td>
      <td><strong>${op.nombre}</strong> <span class="fund-meta">${op.symbol_legible}</span></td>
      <td><span class="badge-operator">${op.operador || 'N/D'}</span></td>
      <td>${formatEur(op.importe)}</td>
      <td><strong>${op.cantidad}</strong></td>
      <td>${op.precio_unitario.toFixed(2)} €</td>
    </tr>
  `).join('');
}

function renderCryptoDoughnutChart(activos) {
  const ctxEl = document.getElementById('criptoAllocationChart');
  if (!ctxEl) return;
  const ctx = ctxEl.getContext('2d');
  const labels = activos.map(a => a.symbol_legible);
  const data = activos.map(a => a.valor_actual);

  if (cryptoDoughnutInstance) cryptoDoughnutInstance.destroy();

  cryptoDoughnutInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: activos.map(a => a.color || '#94a3b8'),
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#94a3b8', font: { size: 11 }, boxWidth: 12 }
        }
      },
      cutout: '65%'
    }
  });
}

function switchCryptoChartView(view, btnElem) {
  currentCryptoView = view;
  document.querySelectorAll('#cryptoViewButtons .view-tab').forEach(b => b.classList.remove('active'));
  if (btnElem) btnElem.classList.add('active');
  renderCryptoTimeseriesChart();
}

function setCryptoTimeframe(tf, btnElem) {
  currentCryptoTf = tf;
  document.querySelectorAll('#criptoSection .tf-btn').forEach(b => b.classList.remove('active'));
  if (btnElem) btnElem.classList.add('active');
  renderCryptoTimeseriesChart();
}

function renderCryptoTimeseriesChart() {
  if (!globalCryptoData) return;

  const isTotal = (currentCryptoView === 'TOTAL');
  let rawPoints = isTotal
    ? (globalCryptoData.timeseries || [])
    : ((globalCryptoData.crypto_timeseries || {})[currentCryptoView] || []);

  if (!rawPoints || rawPoints.length === 0) return;

  let filtered = [...rawPoints];
  const anioActual = new Date().getFullYear();
  if (currentCryptoTf === '1D') {
    filtered = filtered.slice(-2);
  } else if (currentCryptoTf === '5D') {
    filtered = filtered.slice(-5);
  } else if (currentCryptoTf === '1M') {
    filtered = filtered.slice(-30);
  } else if (currentCryptoTf === '6M') {
    filtered = filtered.slice(-180);
  } else if (currentCryptoTf === 'YTD') {
    filtered = filtered.filter(p => p.date >= `${anioActual}-01-01`);
  } else if (currentCryptoTf === '1Y') {
    filtered = filtered.slice(-365);
  }

  const months = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
  const labels = filtered.map(p => {
    const parts = p.date.split('-');
    return `${parts[2]} ${months[parseInt(parts[1], 10) - 1]}`;
  });

  const ctxEl = document.getElementById('criptoChart');
  if (!ctxEl) return;
  const ctx = ctxEl.getContext('2d');
  if (cryptoChartInstance) cryptoChartInstance.destroy();

  const metricElem = document.getElementById('cryptoChartMetric');
  let datasets = [];

  if (isTotal) {
    const values = filtered.map(p => p.market_value);
    const invested = filtered.map(p => p.invested);
    const lastVal = values[values.length - 1];
    const firstVal = values[0];
    const periodGainPct = firstVal > 0 ? ((lastVal - firstVal) / firstVal * 100) : 0;

    metricElem.innerHTML = `Vista: <strong>Total Cripto</strong> · Valor al cierre: <strong>${formatEur(lastVal)}</strong> · Variación en periodo: <span class="${periodGainPct >= 0 ? 'positive' : 'negative'}">${formatPct(periodGainPct)}</span>`;

    const gradient = ctx.createLinearGradient(0, 0, 0, 260);
    gradient.addColorStop(0, 'rgba(249, 115, 22, 0.28)');
    gradient.addColorStop(1, 'rgba(249, 115, 22, 0.00)');

    datasets = [
      {
        label: 'Valor de Mercado',
        data: values,
        borderColor: '#f97316',
        borderWidth: 2,
        tension: 0.3,
        spanGaps: true,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointBackgroundColor: '#f97316',
        fill: true,
        backgroundColor: gradient
      },
      {
        label: 'Capital Invertido',
        data: invested,
        borderColor: 'rgba(148, 163, 184, 0.45)',
        borderWidth: 1.5,
        borderDash: [4, 4],
        pointRadius: 0,
        fill: false,
        tension: 0
      }
    ];
  } else {
    const coin = (globalCryptoData.activos.find(a => a.symbol === currentCryptoView)) || { symbol_legible: currentCryptoView };
    const prices = filtered.map(p => p.price);
    const lastP = prices[prices.length - 1];
    const firstP = prices[0];
    const priceGainPct = firstP > 0 ? ((lastP - firstP) / firstP * 100) : 0;
    const color = coin.color || '#38bdf8';

    metricElem.innerHTML = `Cripto: <strong>${coin.symbol_legible}</strong> · Precio actual: <strong>${lastP.toFixed(2)} €</strong> · Variación periodo: <span class="${priceGainPct >= 0 ? 'positive' : 'negative'}">${formatPct(priceGainPct)}</span>`;

    const gradient = ctx.createLinearGradient(0, 0, 0, 260);
    gradient.addColorStop(0, 'rgba(56, 189, 248, 0.25)');
    gradient.addColorStop(1, 'rgba(56, 189, 248, 0.00)');

    datasets = [
      {
        label: `Precio ${coin.symbol_legible} (€)`,
        data: prices,
        borderColor: color,
        borderWidth: 2,
        tension: 0.3,
        spanGaps: true,
        pointRadius: 0,
        pointHoverRadius: 6,
        pointBackgroundColor: color,
        fill: true,
        backgroundColor: gradient
      }
    ];
  }

  cryptoChartInstance = new Chart(ctx, {
    type: 'line',
    data: { labels: labels, datasets: datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          align: 'end',
          labels: { color: '#889bb8', boxWidth: 12, font: { size: 11 } }
        },
        tooltip: {
          backgroundColor: '#030712',
          titleColor: '#fff',
          bodyColor: '#e2e8f0',
          borderColor: '#38bdf8',
          borderWidth: 1,
          padding: 10,
          callbacks: {
            label: function(context) {
              const label = context.dataset.label || '';
              const val = context.parsed.y;
              return isTotal ? `${label}: ${formatEur(val)}` : `${label}: ${val.toFixed(2)} €`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false, drawBorder: false },
          ticks: { color: '#64748b', maxTicksLimit: 8, font: { size: 11 } }
        },
        y: {
          position: 'right',
          grace: '10%',
          grid: { color: '#1a2844', drawBorder: false },
          ticks: {
            color: '#64748b',
            font: { size: 11 },
            callback: function(val) {
              return isTotal ? formatEur(val) : `${val.toFixed(2)} €`;
            }
          }
        }
      }
    }
  });
}

function renderCryptoCharts() {
  if (!globalCryptoData) return;
  renderCryptoDoughnutChart(globalCryptoData.activos);
  renderCryptoTimeseriesChart();
}

// --- Modal alta de compra cripto ---
function openCryptoPurchaseModal() {
  document.getElementById('criptoPurchaseActivo').value = '';
  document.getElementById('criptoPurchaseFecha').value = new Date().toISOString().split('T')[0];
  document.getElementById('criptoPurchaseCantidad').value = '';
  document.getElementById('criptoPurchasePrecio').value = '';
  document.getElementById('criptoPurchaseExchange').value = '';
  document.getElementById('criptoPurchaseMsg').textContent = '';
  document.getElementById('criptoPurchaseModal').classList.remove('hidden');
  document.getElementById('criptoPurchaseOverlay').classList.remove('hidden');
  document.getElementById('criptoPurchaseActivo').focus();
}

function closeCryptoPurchaseModal() {
  document.getElementById('criptoPurchaseModal').classList.add('hidden');
  document.getElementById('criptoPurchaseOverlay').classList.add('hidden');
}

async function submitCryptoPurchase() {
  const activoVal = document.getElementById('criptoPurchaseActivo').value.trim().toUpperCase();
  const fechaVal = document.getElementById('criptoPurchaseFecha').value;
  const cantidadVal = parseFloat(document.getElementById('criptoPurchaseCantidad').value);
  const precioVal = parseFloat(document.getElementById('criptoPurchasePrecio').value);
  const exchangeVal = document.getElementById('criptoPurchaseExchange').value.trim();
  const msgEl = document.getElementById('criptoPurchaseMsg');
  const saveBtn = document.getElementById('saveCriptoPurchaseBtn');

  msgEl.textContent = '';

  if (!SYMBOL_A_COIN[activoVal]) {
    msgEl.textContent = 'Criptoactivo no válido. Usa BTC o ETH.';
    return;
  }
  if (!fechaVal || isNaN(cantidadVal) || cantidadVal <= 0 || isNaN(precioVal) || precioVal <= 0) {
    msgEl.textContent = 'Completa Fecha, Cantidad (>0) y Precio unitario (>0).';
    return;
  }

  const importe = cantidadVal * precioVal;
  const body = {
    symbol: SYMBOL_A_COIN[activoVal],
    fecha: fechaVal,
    importe: Math.round(importe * 100) / 100,
    cantidad: cantidadVal,
    precio_unitario: precioVal
  };
  if (exchangeVal) body.operador = exchangeVal;

  saveBtn.disabled = true;
  saveBtn.style.opacity = '0.6';
  try {
    const res = await fetch('/api/criptoactivos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    if (res.ok) {
      closeCryptoPurchaseModal();
      globalCryptoData = null; // fuerza recarga en la siguiente activación
      loadCryptoData();
      return;
    }

    let detail = 'Error inesperado.';
    try {
      const data = await res.json();
      if (data && data.detail) detail = data.detail;
    } catch (e) { /* ignore */ }

    if (res.status === 409 || res.status === 422) {
      msgEl.textContent = detail;
    } else {
      msgEl.textContent = 'Error al registrar la compra. Inténtalo de nuevo.';
    }
  } catch (err) {
    console.error(err);
    msgEl.textContent = 'Error de conexión. No se pudo guardar la compra.';
  } finally {
    saveBtn.disabled = false;
    saveBtn.style.opacity = '1';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  // Modal alta de compra cripto
  const btnNueva = document.getElementById('cryptoNewPurchaseBtn');
  if (btnNueva) btnNueva.addEventListener('click', openCryptoPurchaseModal);
  const cancelBtn = document.getElementById('cancelCriptoPurchaseBtn');
  if (cancelBtn) cancelBtn.addEventListener('click', closeCryptoPurchaseModal);
  const overlay = document.getElementById('criptoPurchaseOverlay');
  if (overlay) overlay.addEventListener('click', function(e) {
    if (e.target === this) closeCryptoPurchaseModal();
  });
  const saveBtn = document.getElementById('saveCriptoPurchaseBtn');
  if (saveBtn) saveBtn.addEventListener('click', submitCryptoPurchase);
});