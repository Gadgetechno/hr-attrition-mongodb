/* app.js – HR Attrition MongoDB Dashboard  */

// ── State ─────────────────────────────────────────────────────────
let currentTab = 'overview';
let empPage = 1;

const PAGE_TITLES = {
  overview: 'Dashboard',
  employees: 'Employees',
  projects: 'Projects',
  bson: 'BSON Types Demo',
  crud: 'CRUD Operations',
  aggregations: 'Aggregation Pipelines',
  indexing: 'Index Performance',
  ml: 'ML Predictions',
};

// ── Routing ───────────────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    switchTab(link.dataset.tab);
    if (window.innerWidth <= 768)
      document.getElementById('sidebar').classList.remove('open');
  });
});

function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(l => l.classList.remove('active'));
  document.getElementById(`tab-${tab}`).classList.add('active');
  document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
  document.getElementById('pageTitle').textContent = PAGE_TITLES[tab] || tab;
  currentTab = tab;

  if (tab === 'overview')   loadOverview();
  if (tab === 'employees')  loadEmployees(1);
  if (tab === 'projects')   loadProjects();
}

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}
function refreshCurrent() { switchTab(currentTab); }

// ── Overtime toggle wiring ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const ot = document.getElementById('f_overtime');
  const lb = document.getElementById('overtimeLabel');
  if (ot && lb) {
    ot.addEventListener('change', () => {
      lb.textContent = ot.checked ? 'Working overtime' : 'No overtime';
      lb.style.color = ot.checked ? 'var(--rose)' : 'var(--text-dim)';
    });
  }
});

// ── API helpers ───────────────────────────────────────────────────
async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  const j = await r.json();
  if (j.error) throw new Error(j.error);
  return j;
}

function fmtJSON(obj) { return JSON.stringify(obj, null, 2); }

function setResult(id, content) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = typeof content === 'string' ? content : fmtJSON(content);
}

function setLoading(id, msg = 'Running query…') {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = `
    <div class="loading">
      <div class="loading-spinner"></div>
      ${msg}
    </div>`;
}

function setError(id, msg) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = `<div class="error-msg">⚠️ ${msg}</div>`;
}

// ── Connection ────────────────────────────────────────────────────
async function checkHealth() {
  const dot  = document.getElementById('connDot');
  const txt  = document.getElementById('connText');
  try {
    const h = await api('/api/health');
    dot.className = 'conn-dot connected';
    txt.textContent = `MongoDB ${h.mongo_version} · Connected`;
    return h;
  } catch (e) {
    dot.className = 'conn-dot error';
    txt.textContent = 'Cannot connect to MongoDB';
    return null;
  }
}

// ═══════════════════════════════════════════════════════════════════
// OVERVIEW
// ═══════════════════════════════════════════════════════════════════
async function loadOverview() {
  const h = await checkHealth();
  if (!h) return;

  const c = h.document_counts || {};
  const cards = [
    { label: 'Employees',       val: c.employees       || 0, sub: 'in employees collection',   cls: 'accent' },
    { label: 'Departments',     val: c.departments     || 0, sub: 'reference collection',       cls: 'teal' },
    { label: 'Projects',        val: c.projects        || 0, sub: 'many-to-many links',          cls: 'amber' },
    { label: 'Exit Interviews', val: c.exit_interviews || 0, sub: 'text-indexed comments',      cls: 'rose' },
    { label: 'Job Roles',       val: c.job_roles       || 0, sub: 'role reference docs',        cls: 'sky' },
    { label: 'ML Model Runs',   val: c.ml_models       || 0, sub: 'model registry entries',     cls: 'green-c' },
  ];

  document.getElementById('statsGrid').innerHTML = cards.map(c => `
    <div class="stat-card ${c.cls}">
      <div class="stat-label">${c.label}</div>
      <div class="stat-value">${(c.val || 0).toLocaleString()}</div>
      <div class="stat-sub">${c.sub}</div>
    </div>`).join('');

  Promise.all([
    api('/api/aggregations/by-department').then(renderDeptChart),
    api('/api/aggregations/income-distribution').then(renderIncomeChart),
    api('/api/aggregations/overtime-impact').then(renderOvertimeChart),
    api('/api/aggregations/engagement-by-quarter').then(renderEngagementChart),
    api('/api/aggregations/dashboard-facet').then(renderFacetCharts),
    api('/api/aggregations/by-job-level').then(renderLevelChart),
  ]).catch(console.error);
}

function renderDeptChart(data) {
  const max = Math.max(...data.map(d => d.attrition_rate_pct), 1);
  document.getElementById('deptChart').innerHTML = data.map(d => `
    <div class="bar-item">
      <div class="bar-label" title="${d.dept_name}">${d.dept_name}</div>
      <div class="bar-track">
        <div class="bar-fill red-fill" style="width:${(d.attrition_rate_pct / max * 100).toFixed(1)}%">
          <span class="bar-val">${d.attrition_rate_pct}%</span>
        </div>
      </div>
      <div class="bar-extra">n = ${d.employees}</div>
    </div>`).join('');
}

function renderIncomeChart(data) {
  const max = Math.max(...data.map(d => d.employees), 1);
  document.getElementById('incomeChart').innerHTML = data.map(d => `
    <div class="bar-item">
      <div class="bar-label">${d.range_label}</div>
      <div class="bar-track">
        <div class="bar-fill teal-fill" style="width:${(d.employees / max * 100).toFixed(1)}%">
          <span class="bar-val">${d.employees}</span>
        </div>
      </div>
      <div class="bar-extra">${d.attrition_rate_pct}% left</div>
    </div>`).join('');
}

function renderOvertimeChart(data) {
  document.getElementById('overtimeChart').innerHTML = `
    <div class="ot-cards">` +
    data.map(d => `
      <div class="ot-card">
        <div class="ot-label">${d.cohort}</div>
        <div class="ot-value" style="color:${d.overtime ? 'var(--rose)' : 'var(--green)'}">${d.attrition_rate_pct}%</div>
        <div class="ot-label">attrition rate</div>
        <div style="margin-top:8px;font-size:11.5px;color:var(--text-dim)">Satisfaction: <strong>${d.avg_satisfaction}</strong></div>
        <div style="font-size:11.5px;color:var(--text-muted)">${d.employees.toLocaleString()} employees</div>
      </div>`).join('') + `</div>`;
}

function renderEngagementChart(data) {
  const max = Math.max(...data.map(d => d.avg_score), 1);
  document.getElementById('engagementChart').innerHTML = data.map(d => `
    <div class="bar-item">
      <div class="bar-label">${d._id}</div>
      <div class="bar-track">
        <div class="bar-fill purple-fill" style="width:${(d.avg_score / max * 100).toFixed(1)}%">
          <span class="bar-val">${d.avg_score}</span>
        </div>
      </div>
      <div class="bar-extra">${d.responses} resp</div>
    </div>`).join('');
}

function renderFacetCharts(data) {
  const roles = data.top_risk_roles || [];
  const max = roles.length ? Math.max(...roles.map(r => r.attrition_rate_pct), 1) : 1;
  document.getElementById('riskRolesChart').innerHTML = roles.map(r => `
    <div class="bar-item">
      <div class="bar-label" title="${r._id}">${r._id}</div>
      <div class="bar-track">
        <div class="bar-fill orange-fill" style="width:${(r.attrition_rate_pct / max * 100).toFixed(1)}%">
          <span class="bar-val">${r.attrition_rate_pct}%</span>
        </div>
      </div>
      <div class="bar-extra">n = ${r.n}</div>
    </div>`).join('');
}

function renderLevelChart(data) {
  const max = Math.max(...data.map(d => d.attrition_rate_pct), 1);
  document.getElementById('levelChart').innerHTML = data.map(d => `
    <div class="bar-item">
      <div class="bar-label">Job Level ${d.job_level}</div>
      <div class="bar-track">
        <div class="bar-fill" style="width:${(d.attrition_rate_pct / max * 100).toFixed(1)}%">
          <span class="bar-val">${d.attrition_rate_pct}%</span>
        </div>
      </div>
      <div class="bar-extra">$${d.avg_income?.toLocaleString()}</div>
    </div>`).join('');
}

// ═══════════════════════════════════════════════════════════════════
// EMPLOYEES
// ═══════════════════════════════════════════════════════════════════
async function loadEmployees(page) {
  empPage = page || empPage;
  const dept = document.getElementById('filterDept')?.value || '';
  const attr = document.getElementById('filterAttrition')?.value || '';
  const role = document.getElementById('searchRole')?.value || '';
  document.getElementById('employeeTable').innerHTML = `<div class="loading"><div class="loading-spinner"></div>Loading employees…</div>`;
  try {
    const params = new URLSearchParams({ page: empPage, size: 25, dept, attrition: attr, role });
    const data = await api(`/api/employees?${params}`);
    renderEmployeeTable(data);
    renderPagination(data.total, data.page, data.size);
  } catch (e) { setError('employeeTable', e.message); }
}

function renderEmployeeTable(data) {
  if (!data.data.length) {
    document.getElementById('employeeTable').innerHTML = `
      <div class="empty-state"><div class="empty-icon">🔍</div><div class="empty-text">No employees found with these filters.</div></div>`;
    return;
  }
  const rows = data.data.map(e => {
    const inc = e.compensation?.monthly_income?.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }) || '—';
    const risk = e.attrition_risk != null ? `${(e.attrition_risk * 100).toFixed(1)}%` : '—';
    const tier = e.risk_tier || '—';
    const tCls = tier === 'High' ? 'high' : tier === 'Medium' ? 'medium' : 'low';
    return `<tr onclick="loadEmployeeDetail('${e.employee_id}')">
      <td><code style="color:var(--purple-soft)">${e.employee_id}</code></td>
      <td>${e.age}</td>
      <td>${e.gender}</td>
      <td>${e.department}</td>
      <td>${e.job_role}</td>
      <td style="text-align:center">${e.job_level}</td>
      <td>${inc}</td>
      <td><span class="pill pill-${(e.attrition || 'No').toLowerCase()}">${e.attrition || 'No'}</span></td>
      <td style="text-align:center">${e.overtime ? '✔' : '—'}</td>
      <td>${risk}</td>
      <td><span class="pill pill-${tCls.toLowerCase()}">${tier}</span></td>
    </tr>`;
  }).join('');

  document.getElementById('employeeTable').innerHTML = `
    <div style="overflow-x:auto">
    <table class="data-table">
      <thead><tr>
        <th>ID</th><th>Age</th><th>Gender</th><th>Department</th>
        <th>Role</th><th>Lvl</th><th>Income</th><th>Status</th>
        <th>OT</th><th>Risk</th><th>Tier</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    <div style="font-size:11.5px;color:var(--text-muted);margin-top:10px;padding-top:10px;border-top:1px solid var(--border)">
      Showing ${((data.page - 1) * data.size) + 1}–${Math.min(data.page * data.size, data.total)} of <strong style="color:var(--text)">${data.total.toLocaleString()}</strong> employees
    </div>`;
}

function renderPagination(total, page, size) {
  const pages = Math.ceil(total / size);
  if (pages <= 1) { document.getElementById('empPagination').innerHTML = ''; return; }
  let html = '';
  const lo = Math.max(1, page - 2), hi = Math.min(pages, page + 2);
  if (lo > 1) html += `<button class="pag-btn" onclick="loadEmployees(1)">1</button>`;
  if (lo > 2) html += `<span style="color:var(--text-muted);padding:0 6px;font-size:12px">…</span>`;
  for (let p = lo; p <= hi; p++)
    html += `<button class="pag-btn ${p === page ? 'active' : ''}" onclick="loadEmployees(${p})">${p}</button>`;
  if (hi < pages - 1) html += `<span style="color:var(--text-muted);padding:0 6px;font-size:12px">…</span>`;
  if (hi < pages) html += `<button class="pag-btn" onclick="loadEmployees(${pages})">${pages}</button>`;
  document.getElementById('empPagination').innerHTML = html;
}

async function loadEmployeeDetail(empId) {
  document.getElementById('empModal').classList.add('open');
  document.getElementById('modalContent').innerHTML = `<div class="loading"><div class="loading-spinner"></div>Loading…</div>`;
  try {
    const d = await api(`/api/employees/${empId}`);
    renderModal(d);
  } catch (e) {
    document.getElementById('modalContent').innerHTML = `<div class="error-msg">⚠️ ${e.message}</div>`;
  }
}

function renderModal(d) {
  const ri = d.attrition_risk != null ? `${(d.attrition_risk * 100).toFixed(1)}%` : 'Not scored';
  const tierCls = d.risk_tier === 'High' ? 'rose' : d.risk_tier === 'Medium' ? 'amber' : 'green';
  document.getElementById('modalContent').innerHTML = `
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:18px">
      <div style="width:52px;height:52px;border-radius:16px;background:var(--grad-purple);display:flex;align-items:center;justify-content:center;font-size:22px">👤</div>
      <div>
        <h2 style="font-size:20px;font-weight:800;letter-spacing:-.02em">${d.employee_id}</h2>
        <p style="color:var(--text-dim);font-size:13px;margin-top:2px">${d.job_role} · ${d.department}</p>
      </div>
      ${d.risk_tier ? `<div style="margin-left:auto"><span class="pill pill-${d.risk_tier?.toLowerCase()}">${d.risk_tier} Risk</span></div>` : ''}
    </div>
    <div class="modal-grid">
      ${mf('Age', d.age)} ${mf('Gender', d.gender)}
      ${mf('Marital Status', d.marital_status)} ${mf('Job Level', d.job_level)}
      ${mf('Monthly Income', `$${(d.compensation?.monthly_income || 0).toLocaleString()}`)}
      ${mf('Overtime', d.overtime ? '✔ Yes' : 'No')}
      ${mf('Attrition', d.attrition)} ${mf('Risk Score', ri)}
      ${mf('Business Travel', d.business_travel)} ${mf('Distance', `${d.distance_from_home_km} km`)}
      ${mf('Years @ Company', d.career?.years_at_company)} ${mf('Total Experience', `${d.career?.total_working_years} yrs`)}
      ${mf('Since Promotion', `${d.career?.years_since_last_promotion} yrs`)}
      ${mf('Training (last yr)', d.career?.training_times_last_year)}
      ${mf('Job Satisfaction', `${d.satisfaction?.job} / 4`)}
      ${mf('Env Satisfaction', `${d.satisfaction?.environment} / 4`)}
    </div>
    ${d.exit_interview ? `
    <div style="margin-top:18px;background:rgba(251,113,133,.07);border:1.5px solid rgba(251,113,133,.2);border-radius:16px;padding:16px">
      <div style="font-size:10px;font-weight:700;color:var(--rose);text-transform:uppercase;letter-spacing:.07em;margin-bottom:8px">Exit Interview</div>
      <div style="margin-bottom:8px;display:flex;gap:6px;flex-wrap:wrap">
        ${(d.exit_interview.theme_tags || []).map(t => `<span class="badge badge-red">${t}</span>`).join('')}
      </div>
      <p style="font-size:12.5px;line-height:1.7;color:var(--text-dim);font-style:italic">"${d.exit_interview.comments}"</p>
    </div>` : ''}
    <div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border);font-size:11.5px;color:var(--text-muted);display:flex;gap:18px;flex-wrap:wrap">
      <span>📁 Projects: ${(d.project_ids || []).join(', ') || 'None'}</span>
      <span>📅 Hired: ${d.hire_date ? new Date(d.hire_date).toLocaleDateString() : 'N/A'}</span>
    </div>`;
}

function mf(label, val) {
  return `<div class="modal-field">
    <div class="modal-field-label">${label}</div>
    <div class="modal-field-val">${val ?? '—'}</div>
  </div>`;
}
function closeModal() { document.getElementById('empModal').classList.remove('open'); }

// ═══════════════════════════════════════════════════════════════════
// PROJECTS
// ═══════════════════════════════════════════════════════════════════
async function loadProjects() {
  document.getElementById('projectsTable').innerHTML = `<div class="loading"><div class="loading-spinner"></div>Loading projects…</div>`;
  try {
    const data = await api('/api/projects');
    const rows = data.map(p => `
      <tr class="project-row">
        <td>${p.project_id}</td>
        <td>${p.name}</td>
        <td>${p.dept_id ? p.dept_id : '<span style="color:var(--text-muted)">Cross-functional</span>'}</td>
        <td>${p.member_count}</td>
        <td>$${(p.budget_usd || 0).toLocaleString()}</td>
        <td>${p.start_date ? new Date(p.start_date).toLocaleDateString() : '—'}</td>
      </tr>`).join('');
    document.getElementById('projectsTable').innerHTML = `
      <div style="overflow-x:auto">
      <table class="data-table">
        <thead><tr>
          <th>Project ID</th><th>Name</th><th>Department</th>
          <th>Members</th><th>Budget</th><th>Start Date</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`;
  } catch (e) { setError('projectsTable', e.message); }
}

// ═══════════════════════════════════════════════════════════════════
// BSON DEMO
// ═══════════════════════════════════════════════════════════════════
async function runBsonDemo() {
  setLoading('bsonResult', 'Inserting BSON document into MongoDB…');
  try {
    const data = await api('/api/bson-types', { method: 'POST' });
    const rows = (data.bson_types || []).map(t => `  ${t.k.padEnd(22)} → ${t.t}`).join('\n');
    setResult('bsonResult',
      `Inserted _id : ${data.inserted_id}\n${data.message}\n\nBSON types detected by $type:\n${rows}`);
  } catch (e) { setError('bsonResult', e.message); }
}

// ═══════════════════════════════════════════════════════════════════
// CRUD
// ═══════════════════════════════════════════════════════════════════
async function runCrud(op) {
  const id = `crud${op[0].toUpperCase()}${op.slice(1)}Result`;
  const method = op === 'read' ? 'GET' : 'POST';
  setLoading(id, `Running ${op} operations…`);
  try {
    const data = await api(`/api/crud/${op}`, { method });
    setResult(id, data);
  } catch (e) { setError(id, e.message); }
}

// ═══════════════════════════════════════════════════════════════════
// AGGREGATIONS
// ═══════════════════════════════════════════════════════════════════
async function runAgg(endpoint, resultId) {
  setLoading(resultId, 'Executing aggregation pipeline…');
  try {
    const data = await api(`/api/aggregations/${endpoint}`);
    setResult(resultId, data);
  } catch (e) { setError(resultId, e.message); }
}

async function runExitSearch() {
  const q = document.getElementById('exitSearchQ').value;
  setLoading('aggExitSearch', 'Running $text search…');
  try {
    const data = await api(`/api/aggregations/exit-text-search?q=${encodeURIComponent(q)}`);
    setResult('aggExitSearch', data);
  } catch (e) { setError('aggExitSearch', e.message); }
}

// ═══════════════════════════════════════════════════════════════════
// INDEXING
// ═══════════════════════════════════════════════════════════════════
async function runIndexingDemo() {
  const el = document.getElementById('indexingResult');
  el.innerHTML = `<div class="loading"><div class="loading-spinner"></div>Running explain() before and after index creation…</div>`;
  try {
    const data = await api('/api/indexing/explain');
    const scenarios = [
      { key: 'range_query_income_gt_12000',        label: 'Scenario 1 — Single Field Index',   sub: 'income > $12,000' },
      { key: 'compound_overtime_female_sort_age',  label: 'Scenario 2 — Compound Index',        sub: 'overtime + gender, sorted by age' },
      { key: 'covered_query_dept_attrition',       label: 'Scenario 3 — Covered Query',         sub: 'dept_id + attrition_flag (zero doc reads!)' },
    ];
    el.innerHTML = scenarios.map(s => {
      const d = data[s.key];
      if (!d) return '';
      return `
        <div style="margin-top:22px">
          <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:10px">
            <span style="font-size:14px;font-weight:700;color:var(--purple-soft)">${s.label}</span>
            <span style="font-size:12px;color:var(--text-muted)">${s.sub}</span>
          </div>
          <div class="compare-grid">
            ${explainCard('Before (no index)', d.before, false)}
            ${explainCard('After (index created)', d.after, true)}
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    el.innerHTML = `<div class="error-msg">⚠️ ${e.message}</div>`;
  }
}

function explainCard(title, s, isAfter) {
  if (!s) return '';
  const stages = (s.stages || '').split('→').map(st => st.trim());
  const stageHtml = stages.map(st => {
    const cls = st.includes('IXSCAN') ? 'ixscan' : '';
    return `<span class="stage-badge ${cls}">${st}</span>`;
  }).join(' <span style="color:var(--text-muted)">→</span> ');
  return `<div class="compare-card ${isAfter ? 'after' : ''}">
    <h4>${title}</h4>
    <div class="stat-row"><span class="stat-key">Plan</span><span class="stat-val">${stageHtml}</span></div>
    <div class="stat-row"><span class="stat-key">Keys examined</span><span class="stat-val ${isAfter ? 'improved' : ''}">${s.keys_examined ?? '—'}</span></div>
    <div class="stat-row"><span class="stat-key">Docs examined</span><span class="stat-val ${isAfter ? 'improved' : ''}">${s.docs_examined ?? '—'}</span></div>
    <div class="stat-row"><span class="stat-key">Docs returned</span><span class="stat-val">${s.returned ?? '—'}</span></div>
    <div class="stat-row"><span class="stat-key">Time</span><span class="stat-val ${isAfter ? 'improved' : ''}">${s.ms ?? '—'} ms</span></div>
  </div>`;
}

async function loadIndexInventory() {
  setLoading('indexInventory', 'Fetching index inventory…');
  try {
    const data = await api('/api/indexing/inventory');
    let out = '';
    for (const [coll, indexes] of Object.entries(data)) {
      out += `\n── ${coll} ──\n`;
      for (const [name, info] of Object.entries(indexes))
        out += `  ${name.padEnd(42)} ${JSON.stringify(info.key)}${info.unique ? '  UNIQUE' : ''}\n`;
    }
    setResult('indexInventory', out.trim());
  } catch (e) { setError('indexInventory', e.message); }
}

// ═══════════════════════════════════════════════════════════════════
// ML — TRAIN
// ═══════════════════════════════════════════════════════════════════
async function trainModel() {
  const btn = document.getElementById('trainBtn');
  const stat = document.getElementById('trainStatus');
  btn.disabled = true;
  btn.textContent = '⏳ Training…';
  stat.textContent = 'Loading data from MongoDB, training RandomForest…';
  document.getElementById('modelInfoBox').innerHTML = `<div class="loading"><div class="loading-spinner"></div>Training in progress — may take ~5 seconds…</div>`;
  try {
    const data = await api('/api/ml/train', { method: 'POST' });
    stat.textContent = `✅ Trained at ${new Date(data.trained_at).toLocaleTimeString()}`;
    renderModelInfo(data);
  } catch (e) {
    document.getElementById('modelInfoBox').innerHTML = `<div class="error-msg">⚠️ ${e.message}</div>`;
    stat.textContent = '';
  } finally {
    btn.disabled = false;
    btn.textContent = '⚡ Train Model from MongoDB';
  }
}

async function loadModelInfo() {
  document.getElementById('modelInfoBox').innerHTML = `<div class="loading"><div class="loading-spinner"></div>Checking model status…</div>`;
  try {
    const data = await api('/api/ml/model-info');
    if (!data.trained) {
      document.getElementById('modelInfoBox').innerHTML = `
        <div style="margin-top:14px;padding:16px;background:var(--surface2);border:1px solid var(--border);border-radius:14px;color:var(--text-dim);font-size:13px">
          ⚠️ ${data.message}
        </div>`;
      return;
    }
    renderModelInfo(data);
  } catch (e) {
    document.getElementById('modelInfoBox').innerHTML = `<div class="error-msg">⚠️ ${e.message}</div>`;
  }
}

function renderModelInfo(data) {
  const m = data.metrics || {};
  const features = (data.top_features || []).slice(0, 8);
  const maxImp = features.length ? Math.max(...features.map(f => f.importance)) : 1;
  document.getElementById('modelInfoBox').innerHTML = `
    <div class="model-info-grid">
      ${mi('Accuracy', m.accuracy + '%')} ${mi('F1 Score', m.f1 + '%')}
      ${mi('ROC-AUC', m.roc_auc)} ${mi('Train Rows', m.train_rows?.toLocaleString())}
      ${mi('Test Rows', m.test_rows?.toLocaleString())} ${mi('Features', data.feature_count)}
    </div>
    <div style="margin-top:18px">
      <div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px">Top Feature Importances</div>
      <div class="drivers-grid">
        ${features.map(f => `
          <div class="driver-chip">
            <div class="driver-chip-name">${f.name}</div>
            <div class="driver-chip-bar">
              <div class="driver-chip-fill" style="width:${(f.importance/maxImp*100).toFixed(1)}%"></div>
            </div>
            <div class="driver-chip-val">${f.importance.toFixed(4)}</div>
          </div>`).join('')}
      </div>
    </div>`;
}

function mi(label, val) {
  return `<div class="model-info-tile"><div class="model-info-val">${val ?? '—'}</div><div class="model-info-lab">${label}</div></div>`;
}

// ═══════════════════════════════════════════════════════════════════
// ML — PREDICT
// ═══════════════════════════════════════════════════════════════════
function updSlider(el, valId) {
  document.getElementById(valId).textContent = el.value;
}
function updSliderF(el, valId) {
  document.getElementById(valId).textContent = (el.value / 10).toFixed(1);
}

async function runPredict(e) {
  e.preventDefault();
  const btn = document.getElementById('predictBtn');
  btn.disabled = true;
  btn.textContent = '⏳ Predicting…';
  document.getElementById('predictResult').innerHTML = `<div class="loading"><div class="loading-spinner"></div>Running prediction…</div>`;

  const body = {
    age:                          +document.getElementById('f_age').value,
    distance_from_home_km:        +document.getElementById('f_distance').value,
    job_level:                    +document.getElementById('f_job_level').value,
    'compensation.monthly_income':+document.getElementById('f_monthly_income').value,
    'compensation.daily_rate':    +document.getElementById('f_daily_rate').value,
    'compensation.hourly_rate':   +document.getElementById('f_hourly_rate').value,
    'compensation.monthly_rate':  +document.getElementById('f_monthly_rate').value,
    'compensation.percent_salary_hike': +document.getElementById('f_salary_hike').value,
    'compensation.stock_option_level':  +document.getElementById('f_stock_option').value,
    'satisfaction.environment':   +document.getElementById('f_env_sat').value,
    'satisfaction.job':           +document.getElementById('f_job_sat').value,
    'satisfaction.relationship':  +document.getElementById('f_rel_sat').value,
    'satisfaction.work_life_balance': +document.getElementById('f_wlb').value,
    'satisfaction.job_involvement':   +document.getElementById('f_job_inv').value,
    'satisfaction.performance_rating':+document.getElementById('f_perf').value,
    'satisfaction.overall_index': +(document.getElementById('f_overall').value) / 10,
    'career.total_working_years': +document.getElementById('f_total_yrs').value,
    'career.num_companies_worked':+document.getElementById('f_companies').value,
    'career.years_at_company':    +document.getElementById('f_yrs_company').value,
    'career.years_in_current_role':    +document.getElementById('f_yrs_role').value,
    'career.years_since_last_promotion': +document.getElementById('f_yrs_promo').value,
    'career.years_with_curr_manager':  +document.getElementById('f_yrs_mgr').value,
    'career.training_times_last_year': +document.getElementById('f_training').value,
    overtime:       document.getElementById('f_overtime').checked,
    gender:         document.getElementById('f_gender').value,
    marital_status: document.getElementById('f_marital_status').value,
    business_travel:document.getElementById('f_business_travel').value,
    department:     document.getElementById('f_department').value,
    job_role:       document.getElementById('f_job_role').value,
    'education.field': document.getElementById('f_education_field').value,
  };

  try {
    const d = await api('/api/ml/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    renderPredictResult(d);
  } catch (e) {
    document.getElementById('predictResult').innerHTML = `<div class="error-msg">⚠️ ${e.message}<br/><small>Tip: Train the model first using Step 1.</small></div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = '🔮 Predict Attrition Risk';
  }
}

function renderPredictResult(d) {
  const tier = (d.risk_tier || 'Low').toLowerCase();
  const color = tier === 'high' ? 'var(--rose)' : tier === 'medium' ? 'var(--amber)' : 'var(--green)';
  const emoji = tier === 'high' ? '🚨' : tier === 'medium' ? '⚠️' : '✅';
  const maxImp = d.top_drivers?.length ? Math.max(...d.top_drivers.map(f => f.importance)) : 1;

  document.getElementById('predictResult').innerHTML = `
    <div class="predict-result-card ${tier}">
      <div style="display:flex;align-items:flex-start;gap:20px;flex-wrap:wrap">
        <div>
          <div class="predict-verdict">${emoji} ${d.prediction}</div>
          <div class="predict-score">${d.risk_pct}%</div>
          <div class="predict-meta">
            Tier: <strong style="color:${color}">${d.risk_tier}</strong> &nbsp;·&nbsp;
            Confidence: <strong>${d.confidence}%</strong> &nbsp;·&nbsp;
            <span style="color:var(--green);font-size:11px">✔ Saved to MongoDB prediction_log</span>
          </div>
        </div>
        <div style="flex:1;min-width:180px;padding-top:4px">
          <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px">Risk gauge</div>
          <div class="risk-gauge">
            <div class="risk-gauge-fill" style="width:${d.risk_pct}%"></div>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text-muted)">
            <span>Low</span><span>Medium (40%)</span><span>High (70%)</span>
          </div>
        </div>
      </div>
      <div style="margin-top:20px;font-size:11.5px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em">Top Feature Importances (model-wide)</div>
      <div class="drivers-grid">
        ${(d.top_drivers || []).map(f => `
          <div class="driver-chip">
            <div class="driver-chip-name">${f.feature}</div>
            <div class="driver-chip-bar">
              <div class="driver-chip-fill" style="width:${(f.importance / maxImp * 100).toFixed(1)}%"></div>
            </div>
            <div class="driver-chip-val">${f.importance.toFixed(4)}</div>
          </div>`).join('')}
      </div>
    </div>`;
}

// Quick-fill helpers
function fillHighRisk() {
  setV('f_age', 25); setV('f_distance', 28); setV('f_job_level', 1);
  setV('f_monthly_income', 2200); setV('f_daily_rate', 320);
  setV('f_hourly_rate', 40); setV('f_monthly_rate', 5000); setV('f_salary_hike', 11);
  setV('f_stock_option', 0); setS('f_gender', 'Male'); setS('f_marital_status', 'Single');
  setS('f_business_travel', 'Travel_Frequently'); setS('f_department', 'Sales');
  setS('f_job_role', 'Sales Representative'); setS('f_education_field', 'Marketing');
  setV('f_total_yrs', 3); setV('f_companies', 5); setV('f_yrs_company', 1);
  setV('f_yrs_role', 1); setV('f_yrs_promo', 3); setV('f_yrs_mgr', 0); setV('f_training', 2);
  setRange('f_env_sat', 1, 'envSatVal'); setRange('f_job_sat', 1, 'jobSatVal');
  setRange('f_rel_sat', 1, 'relSatVal'); setRange('f_wlb', 1, 'wlbVal');
  setRange('f_job_inv', 2, 'jobInvVal'); setRange('f_perf', 3, 'perfVal');
  setRangeF('f_overall', 18, 'overallVal');
  document.getElementById('f_overtime').checked = true;
  document.getElementById('overtimeLabel').textContent = 'Working overtime';
  document.getElementById('overtimeLabel').style.color = 'var(--rose)';
}

function fillLowRisk() {
  setV('f_age', 42); setV('f_distance', 5); setV('f_job_level', 4);
  setV('f_monthly_income', 12000); setV('f_daily_rate', 900);
  setV('f_hourly_rate', 90); setV('f_monthly_rate', 22000); setV('f_salary_hike', 18);
  setV('f_stock_option', 2); setS('f_gender', 'Female'); setS('f_marital_status', 'Married');
  setS('f_business_travel', 'Non-Travel'); setS('f_department', 'Research & Development');
  setS('f_job_role', 'Research Director'); setS('f_education_field', 'Life Sciences');
  setV('f_total_yrs', 18); setV('f_companies', 1); setV('f_yrs_company', 14);
  setV('f_yrs_role', 6); setV('f_yrs_promo', 1); setV('f_yrs_mgr', 8); setV('f_training', 4);
  setRange('f_env_sat', 4, 'envSatVal'); setRange('f_job_sat', 4, 'jobSatVal');
  setRange('f_rel_sat', 4, 'relSatVal'); setRange('f_wlb', 4, 'wlbVal');
  setRange('f_job_inv', 4, 'jobInvVal'); setRange('f_perf', 4, 'perfVal');
  setRangeF('f_overall', 45, 'overallVal');
  document.getElementById('f_overtime').checked = false;
  document.getElementById('overtimeLabel').textContent = 'No overtime';
  document.getElementById('overtimeLabel').style.color = 'var(--text-dim)';
}

function setV(id, v) { const el = document.getElementById(id); if (el) el.value = v; }
function setS(id, v) { const el = document.getElementById(id); if (el) el.value = v; }
function setRange(id, v, valId) { const el = document.getElementById(id); if (el) { el.value = v; document.getElementById(valId).textContent = v; } }
function setRangeF(id, v, valId) { const el = document.getElementById(id); if (el) { el.value = v; document.getElementById(valId).textContent = (v / 10).toFixed(1); } }

// ═══════════════════════════════════════════════════════════════════
// ML — WATCHLIST
// ═══════════════════════════════════════════════════════════════════
async function loadML() {
  document.getElementById('mlResult').innerHTML = `<div class="loading"><div class="loading-spinner"></div>Loading ML predictions from MongoDB…</div>`;
  try {
    const data = await api('/api/ml/watchlist');
    const tierMap = {};
    (data.risk_tiers || []).forEach(t => tierMap[t._id] = t.n);
    const model = data.last_model;

    const modelBanner = model ? `
      <div style="margin-bottom:20px;background:var(--surface2);border:1px solid var(--border);border-radius:16px;padding:16px">
        <div style="font-size:10px;font-weight:700;color:var(--purple-soft);text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px">Last Model Run</div>
        <div style="display:flex;gap:24px;flex-wrap:wrap;font-size:12.5px;color:var(--text-dim)">
          <span><strong style="color:var(--text)">${model.algorithm}</strong></span>
          <span>Trained: ${new Date(model.trained_at).toLocaleString()}</span>
          <span>Features: ${(model.features || []).length}</span>
        </div>
      </div>` : `<div class="error-msg" style="margin-bottom:16px">⚠️ No model found. Run <code>python ml_model.py</code> first.</div>`;

    const rows = (data.watchlist || []).map(w => {
      const risk = (w.attrition_risk * 100).toFixed(1);
      const tCls = (w.risk_tier || 'low').toLowerCase();
      return `<tr>
        <td><code style="color:var(--purple-soft)">${w.employee_id}</code></td>
        <td>${w.department}</td>
        <td>${w.job_role}</td>
        <td style="text-align:center">${w.job_level}</td>
        <td>$${(w.compensation?.monthly_income || 0).toLocaleString()}</td>
        <td style="text-align:center">${w.overtime ? '✔' : '—'}</td>
        <td>
          <div style="display:flex;align-items:center;gap:8px">
            <div style="flex:1;height:6px;background:var(--surface2);border-radius:3px;overflow:hidden;min-width:60px">
              <div style="height:100%;width:${risk}%;background:linear-gradient(90deg,var(--amber),var(--rose));border-radius:3px;transition:width .5s"></div>
            </div>
            <span style="font-size:12px;font-weight:700;color:var(--rose);min-width:36px">${risk}%</span>
          </div>
        </td>
        <td><span class="pill pill-${tCls}">${w.risk_tier}</span></td>
      </tr>`;
    }).join('');

    document.getElementById('mlResult').innerHTML = `
      ${modelBanner}
      <div class="ml-header">
        <div class="ml-stat"><div class="ml-stat-val" style="color:var(--rose)">${tierMap['High'] || 0}</div><div class="ml-stat-lab">High Risk</div></div>
        <div class="ml-stat"><div class="ml-stat-val" style="color:var(--amber)">${tierMap['Medium'] || 0}</div><div class="ml-stat-lab">Medium Risk</div></div>
        <div class="ml-stat"><div class="ml-stat-val" style="color:var(--green)">${tierMap['Low'] || 0}</div><div class="ml-stat-lab">Low Risk</div></div>
      </div>
      <p style="font-size:12.5px;color:var(--text-dim);margin-bottom:14px">
        <strong style="color:var(--rose)">${data.flagged_leavers}</strong> currently retained employees flagged as likely to leave
      </p>
      <div style="overflow-x:auto">
      <table class="data-table">
        <thead><tr>
          <th>Employee</th><th>Department</th><th>Role</th>
          <th>Lvl</th><th>Income</th><th>OT</th>
          <th>Risk Score</th><th>Tier</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`;
  } catch (e) {
    document.getElementById('mlResult').innerHTML = `<div class="error-msg">⚠️ ${e.message}</div>`;
  }
}

// ═══════════════════════════════════════════════════════════════════
// PREDICTION LOG
// ═══════════════════════════════════════════════════════════════════
async function loadPredictionLog() {
  document.getElementById('predictionLog').innerHTML = `<div class="loading"><div class="loading-spinner"></div>Loading from prediction_log collection…</div>`;
  try {
    const data = await api('/api/ml/prediction-log');
    if (!data.length) {
      document.getElementById('predictionLog').innerHTML = `<div class="empty-state"><div class="empty-icon">📋</div><div class="empty-text">No predictions yet. Use the form above to make your first prediction.</div></div>`;
      return;
    }
    const rows = data.map(r => {
      const tCls = (r.risk_tier || 'low').toLowerCase();
      return `<tr>
        <td>${new Date(r.predicted_at).toLocaleString()}</td>
        <td><span style="font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:700">${(r.attrition_risk * 100).toFixed(1)}%</span></td>
        <td><span class="pill pill-${tCls}">${r.risk_tier}</span></td>
        <td>${r.source || 'web_tester'}</td>
      </tr>`;
    }).join('');
    document.getElementById('predictionLog').innerHTML = `
      <div style="overflow-x:auto">
      <table class="log-table">
        <thead><tr><th>Predicted At</th><th>Risk Score</th><th>Tier</th><th>Source</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
      <div style="font-size:11.5px;color:var(--text-muted);margin-top:10px">Showing last ${data.length} predictions · Collection: <code>prediction_log</code></div>`;
  } catch (e) {
    document.getElementById('predictionLog').innerHTML = `<div class="error-msg">⚠️ ${e.message}</div>`;
  }
}

// ═══════════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════════
(async () => {
  await checkHealth();
  loadOverview();
})();
