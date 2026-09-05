let doughnutChartInstance = null;
let timeseriesChartInstance = null;
let globalData = null;
let currentView = 'TOTAL';
let currentTimeframe = 'ALL';

function formatEur(val) {
  return new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' }).format(val);
}

function formatPct(val) {
  if (val === null || val === undefined) return 'N/D';
  const sign = val > 0 ? '+' : '';
  return `${sign}${val.toFixed(2)}%`;
}

function renderBadge(val) {
  if (val === null || val === undefined) {
    return `<span class="badge-nd">N/D</span>`;
  }
  const isPos = val >= 0;
  const cls = isPos ? 'badge-positive' : 'badge-negative';
  return `<span class="${cls}">${formatPct(val)}</span>`;
}

// ==========================================
// TOOLTIP FLOTANTE GLOBAL DINÁMICO
// ==========================================
function initGlobalTooltip() {
  let tip = document.getElementById('globalTooltip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'globalTooltip';
    document.body.appendChild(tip);
  }

  document.addEventListener('mouseover', (e) => {
    const icon = e.target.closest('.info-icon');
    if (icon && icon.hasAttribute('data-tooltip')) {
      tip.textContent = icon.getAttribute('data-tooltip');
      tip.style.display = 'block';
      const rect = icon.getBoundingClientRect();
      const tipWidth = 260;
      let left = rect.left + rect.width / 2 - tipWidth / 2;
      let top = rect.top - tip.offsetHeight - 10;

      // Ajustes de bordes de pantalla
      if (left < 10) left = 10;
      if (left + tipWidth > window.innerWidth - 10) left = window.innerWidth - tipWidth - 10;
      if (top < 10) top = rect.bottom + 10; // Si no cabe arriba, mostrarlo abajo

      tip.style.left = `${left}px`;
      tip.style.top = `${top}px`;
    }
  });

  document.addEventListener('mouseout', (e) => {
    const icon = e.target.closest('.info-icon');
    if (icon) {
      tip.style.display = 'none';
    }
  });
}

async function loadData(forceRefresh = false) {
  const btn = document.getElementById('refreshBtn');
  const spinner = document.getElementById('refreshSpinner');
  const text = document.getElementById('refreshText');

  if (btn) {
    btn.style.opacity = '0.6';
    if (spinner) spinner.style.animation = 'spin 1s linear infinite';
    if (text && forceRefresh) text.textContent = 'Consultando mercado...';
  }

  try {
    const url = forceRefresh ? '/api/portfolio?refresh=true' : '/api/portfolio';
    const res = await fetch(url);
    if (!res.ok) throw new Error('Error al conectar con la API');
    globalData = await res.json();

    const t = globalData.totales;
    document.getElementById('kpiMarketVal').textContent = formatEur(t.valor_mercado);
    document.getElementById('kpiInvested').textContent = formatEur(t.invertido);

    const gainElem = document.getElementById('kpiGain');
    gainElem.textContent = `${formatEur(t.beneficio_eur)} (${formatPct(t.beneficio_pct)})`;
    gainElem.className = `kpi-sub ${t.beneficio_eur >= 0 ? 'positive' : 'negative'}`;

    const gainPctElem = document.getElementById('kpiGainPct');
    gainPctElem.textContent = formatPct(t.beneficio_pct);
    gainPctElem.className = `kpi-value ${t.beneficio_pct >= 0 ? 'positive' : 'negative'}`;

    document.getElementById('kpiGainAbs').textContent = `${formatEur(t.beneficio_eur)} de beneficio`;
    document.getElementById('kpiActiveCount').textContent = t.fondos_activos;
    document.getElementById('kpiLastUpdated').textContent = `Actualizado: ${t.actualizado}`;

    const activeFunds = globalData.fondos.filter(f => f.is_active);
    const transferredFunds = globalData.fondos.filter(f => !f.is_active);

    // 1. Tabla de Posiciones Activas
    const tbodyFunds = document.getElementById('fundsTableBody');
    tbodyFunds.innerHTML = activeFunds.map(f => `
      <tr>
        <td>
          <div class="fund-title">${f.short_name}</div>
          <span class="fund-meta">${f.isin} · TER ${f.ter} · Riesgo ${f.risk}/7</span>
        </td>
        <td><span class="badge-operator">${f.operador}</span></td>
        <td><strong>${f.participaciones}</strong></td>
        <td>${formatEur(f.invertido)}</td>
        <td>${f.nav_actual.toFixed(2)} €</td>
        <td style="font-size: 0.85rem; color: var(--text-muted);">${f.fecha_nav.includes('-') ? f.fecha_nav.split('-').reverse().join('/') : f.fecha_nav}</td>
        <td><strong>${formatEur(f.valor_actual)}</strong></td>
        <td class="${f.beneficio_eur >= 0 ? 'positive' : 'negative'}"><strong>${f.beneficio_eur > 0 ? '+' : ''}${formatEur(f.beneficio_eur)}</strong></td>
        <td>${renderBadge(f.beneficio_pct)}</td>
        <td><strong>${f.peso_pct.toFixed(1)}%</strong></td>
      </tr>
    `).join('');

    // 2. Tabla de Variaciones Reales
    const tbodyVar = document.getElementById('variationsTableBody');
    tbodyVar.innerHTML = activeFunds.map(f => {
      const meses = f.months_active;
      const realGainText = `${renderBadge(f.beneficio_pct)} <small class="muted">(${meses} m)</small>`;
      return `
        <tr>
          <td><strong>${f.short_name}</strong></td>
          <td>${renderBadge(f.variacion_dia)}</td>
          <td>${renderBadge(f.variacion_semana)}</td>
          <td>${renderBadge(f.variacion_mes)}</td>
          <td>${renderBadge(f.variacion_ano)}</td>
          <td><strong>${realGainText}</strong></td>
        </tr>
      `;
    }).join('');

    // 3. Tabla de Todas las Operaciones
    const tbodyOps = document.getElementById('operationsTableBody');
    if (tbodyOps && globalData.all_operations) {
      tbodyOps.innerHTML = globalData.all_operations.map(op => `
        <tr>
          <td>${op.fecha}</td>
          <td><span class="badge-type ${op.tipo.toLowerCase()}">${op.tipo}</span></td>
          <td><strong>${op.fondo_name}</strong> <span class="fund-meta">${op.isin}</span></td>
          <td><span class="badge-operator">${op.operador}</span></td>
          <td>${formatEur(op.importe)}</td>
          <td><strong>${op.participaciones}</strong></td>
          <td>${op.precio_titulo.toFixed(2)} €</td>
        </tr>
      `).join('');
    }

    // 4. Tabla de Fondos Traspasados
    const tbodyTrans = document.getElementById('transferredTableBody');
    if (tbodyTrans) {
      tbodyTrans.innerHTML = transferredFunds.map(f => `
        <tr>
          <td>
            <div class="fund-title">${f.short_name}</div>
            <span class="fund-meta">${f.isin}</span>
          </td>
          <td>${f.category}</td>
          <td><strong>${formatEur(f.invertido)}</strong></td>
          <td>${f.ordenes_count} compras</td>
          <td><span class="badge-negative">Traspasado</span></td>
        </tr>
      `).join('');
    }

    renderDoughnutChart(activeFunds);
    renderTimeseriesChart();

  } catch (err) {
    console.error(err);
    alert('Error al actualizar datos: ' + err.message);
  } finally {
    if (btn) {
      btn.style.opacity = '1';
      if (spinner) spinner.style.animation = 'none';
      if (text) text.textContent = 'Actualizar Precios';
    }
  }
}

function renderDoughnutChart(funds) {
  const ctx = document.getElementById('allocationChart').getContext('2d');
  const labels = funds.map(f => f.short_name);
  const data = funds.map(f => f.valor_actual);

  if (doughnutChartInstance) {
    doughnutChartInstance.destroy();
  }

  doughnutChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: ['#38bdf8', '#818cf8', '#34d399', '#fbbf24'],
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

function switchChartView(view, btnElem) {
  currentView = view;
  document.querySelectorAll('.view-tab').forEach(b => b.classList.remove('active'));
  if (btnElem) btnElem.classList.add('active');
  renderTimeseriesChart();
}

function setTimeframe(tf, btnElem) {
  currentTimeframe = tf;
  document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
  if (btnElem) btnElem.classList.add('active');
  renderTimeseriesChart();
}

function renderTimeseriesChart() {
  if (!globalData) return;

  const isTotal = (currentView === 'TOTAL');
  let rawPoints = isTotal ? (globalData.timeseries || []) : ((globalData.fund_timeseries || {})[currentView] || []);

  if (!rawPoints || rawPoints.length === 0) return;

  let filtered = [...rawPoints];
  if (currentTimeframe === '1D') {
    filtered = filtered.slice(-2);
  } else if (currentTimeframe === '5D') {
    filtered = filtered.slice(-5);
  } else if (currentTimeframe === '1M') {
    filtered = filtered.slice(-30);
  } else if (currentTimeframe === '6M') {
    filtered = filtered.slice(-180);
  } else if (currentTimeframe === 'YTD') {
    filtered = filtered.filter(p => p.date >= '2026-01-01');
  } else if (currentTimeframe === '1Y') {
    filtered = filtered.slice(-365);
  }

  const months = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
  const labels = filtered.map(p => {
    const parts = p.date.split('-');
    return `${parts[2]} ${months[parseInt(parts[1], 10) - 1]}`;
  });

  const ctx = document.getElementById('portfolioTimeseriesChart').getContext('2d');
  if (timeseriesChartInstance) {
    timeseriesChartInstance.destroy();
  }

  const metricElem = document.getElementById('chartCurrentMetric');
  let datasets = [];

  if (isTotal) {
    const values = filtered.map(p => p.market_value);
    const invested = filtered.map(p => p.invested);
    const lastVal = values[values.length - 1];
    const firstVal = values[0];
    const periodGainPct = firstVal > 0 ? ((lastVal - firstVal) / firstVal * 100) : 0;

    metricElem.innerHTML = `Vista: <strong>Toda la Cartera</strong> · Valor al cierre: <strong>${formatEur(lastVal)}</strong> · Variación en periodo: <span class="${periodGainPct >= 0 ? 'positive' : 'negative'}">${formatPct(periodGainPct)}</span>`;

    const gradient = ctx.createLinearGradient(0, 0, 0, 260);
    gradient.addColorStop(0, 'rgba(20, 184, 166, 0.28)');
    gradient.addColorStop(1, 'rgba(20, 184, 166, 0.00)');

    datasets = [
      {
        label: 'Valor de Mercado',
        data: values,
        borderColor: '#14b8a6',
        borderWidth: 2,
        tension: 0.3,
        spanGaps: true,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointBackgroundColor: '#14b8a6',
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
    const fundMeta = globalData.fondos.find(f => f.isin === currentView) || { short_name: currentView };
    const navs = filtered.map(p => p.nav);
    const lastNav = navs[navs.length - 1];
    const firstNav = navs[0];
    const navGainPct = firstNav > 0 ? ((lastNav - firstNav) / firstNav * 100) : 0;

    metricElem.innerHTML = `Fondo: <strong>${fundMeta.short_name}</strong> · NAV actual: <strong>${lastNav.toFixed(2)} €</strong> · Variación NAV periodo: <span class="${navGainPct >= 0 ? 'positive' : 'negative'}">${formatPct(navGainPct)}</span> · Invertido: <strong>${formatEur(fundMeta.invertido)}</strong> (${fundMeta.participaciones} part.)`;

    const gradient = ctx.createLinearGradient(0, 0, 0, 260);
    gradient.addColorStop(0, 'rgba(56, 189, 248, 0.25)');
    gradient.addColorStop(1, 'rgba(56, 189, 248, 0.00)');

    datasets = [
      {
        label: `NAV ${fundMeta.short_name} (€/part)`,
        data: navs,
        borderColor: '#38bdf8',
        borderWidth: 2,
        tension: 0.3,
        spanGaps: true,
        pointRadius: 0,
        pointHoverRadius: 6,
        pointBackgroundColor: '#38bdf8',
        fill: true,
        backgroundColor: gradient
      }
    ];
  }

  timeseriesChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: datasets
    },
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

function toggleSection(contentId, iconId) {
  const content = document.getElementById(contentId);
  const icon = document.getElementById(iconId);
  if (!content) return;
  if (content.classList.contains('hidden')) {
    content.classList.remove('hidden');
    if (icon) icon.textContent = '▲';
  } else {
    content.classList.add('hidden');
    if (icon) icon.textContent = '▼';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initGlobalTooltip();
  loadData(false);
});
