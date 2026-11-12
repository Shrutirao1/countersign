// =========================================================
// Countersign web app
// Four tabs: Courtroom (run a live case), Receipts, Dashboard, Evaluation.
// It talks to the Python server through /api/... routes.
// =========================================================

// ---------- Small helpers ----------
function $(selector) {
  return document.querySelector(selector);
}

function money(amount) {
  return '$' + Number(amount).toFixed(2);
}

// Escape text before putting it into HTML, so merchant text can't break the page.
function esc(text) {
  return String(text ?? '').replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}

function percent(value) {
  if (value === null || value === undefined) return 'n/a';
  return Math.round(value * 100) + '%';
}

function sleep(ms) {
  return new Promise(function (resolve) { setTimeout(resolve, ms); });
}

async function getJSON(url) {
  const response = await fetch(url);
  return response.json();
}

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  return { ok: response.ok, data: await response.json() };
}

// ---------- App state ----------
let config = null;          // settings from the server
let running = false;        // true while a case is running
const rounds = new Map();   // round number -> its HTML element

// =========================================================
// Start-up
// =========================================================
init();

async function init() {
  config = await getJSON('/api/config');
  showModes();
  fillScenarios();
  setUpPayPal();
  $('#resetDemo').addEventListener('click', resetDemo);
  $('#verifyChain').addEventListener('click', verifyChain);
  $('#runPicker').addEventListener('change', function () { showOfferTable(); });
  window.addEventListener('hashchange', showTab);
  showTab();
  loadPrecedents();
}

// The coloured pills in the header.
function showModes() {
  const aiLabels = { live: 'AI agents: live', mock: 'AI agents: mock (simulated delay)', offline: 'AI agents: offline analyzer' };
  const efficient = config.flags.skipTrialOnRuleFail && config.flags.parallel && config.flags.useCache && !config.flags.shopperUsesAi;
  $('#modes').innerHTML =
    '<span class="pill ' + (config.paypalMode === 'sandbox' ? 'on' : '') + '">PayPal: ' + config.paypalMode + '</span>' +
    '<span class="pill ' + (config.aiMode === 'live' ? 'on' : '') + '">' + aiLabels[config.aiMode] + '</span>' +
    '<span class="pill ' + (efficient ? 'on' : '') + '">Design: ' + (efficient ? 'efficient' : 'old (benchmark)') + '</span>';
}

// =========================================================
// Tabs (the part after # in the address picks the tab)
// =========================================================
function showTab() {
  let name = location.hash.replace('#', '');
  if (!['court', 'receipts', 'dashboard', 'eval'].includes(name)) name = 'court';
  document.querySelectorAll('.view').forEach(function (view) { view.classList.add('hidden'); });
  $('#view-' + name).classList.remove('hidden');
  document.querySelectorAll('.tabs a').forEach(function (link) {
    link.classList.toggle('active', link.dataset.tab === name);
  });
  if (name === 'receipts') loadReceipts();
  if (name === 'dashboard') loadDashboard();
  if (name === 'eval') loadEval();
}

// =========================================================
// Courtroom: the guardian's rules
// =========================================================
function fillScenarios() {
  const select = $('#scenario');
  select.innerHTML = config.scenarios.map(function (s) {
    return '<option value="' + s.id + '">' + esc(s.label) + '</option>';
  }).join('');
  select.addEventListener('change', applyScenario);
  applyScenario();
}

function currentScenario() {
  return config.scenarios.find(function (s) { return s.id === $('#scenario').value; });
}

function applyScenario() {
  const scenario = currentScenario();
  $('#requestText').textContent = '"' + scenario.request + '"';
  $('#protected').textContent = scenario.protectedPerson;
  $('#budget').value = scenario.defaultRules.budget;
  $('#noSubscriptions').checked = scenario.defaultRules.noSubscriptions;
  $('#requireFreeReturns').checked = scenario.defaultRules.requireFreeReturns;
  $('#noHiddenFees').checked = scenario.defaultRules.noHiddenFees;
}

function readRules() {
  return {
    budget: Number($('#budget').value),
    noSubscriptions: $('#noSubscriptions').checked,
    maxMonthly: 0,
    requireFreeReturns: $('#requireFreeReturns').checked,
    noHiddenFees: $('#noHiddenFees').checked,
  };
}

// =========================================================
// Courtroom: PayPal
// =========================================================
function setUpPayPal() {
  // With sandbox keys: the real PayPal button. Without: a simulated button.
  if (config.paypalMode === 'sandbox' && config.paypalClientId) {
    const script = document.createElement('script');
    script.src = 'https://www.paypal.com/sdk/js?client-id=' + encodeURIComponent(config.paypalClientId) + '&currency=USD&intent=authorize';
    script.onload = function () {
      window.paypal.Buttons({
        style: { layout: 'vertical', shape: 'rect', label: 'paypal' },
        createOrder: async function () { return (await createMandate()).id; },
        onApprove: async function (data) { await runCase(data.orderID); },
        onError: function (err) { showError('PayPal error: ' + err); },
      }).render('#paypal-buttons');
    };
    script.onerror = function () { $('#simApprove').classList.remove('hidden'); };
    document.head.appendChild(script);
  } else {
    $('#simApprove').classList.remove('hidden');
  }
  $('#simApprove').addEventListener('click', async function () {
    if (running) return;
    const order = await createMandate();
    if (order) await runCase(order.id);
  });
}

// Ask the server to create the PayPal order (the hold) for the budget.
async function createMandate() {
  const result = await postJSON('/api/mandate', { scenarioId: currentScenario().id, rules: readRules() });
  if (!result.ok) {
    showError(result.data.error || 'Could not create the PayPal order');
    return null;
  }
  return result.data;
}

async function resetDemo() {
  await postJSON('/api/demo/reset');
  loadPrecedents();
}

async function loadPrecedents() {
  const list = await getJSON('/api/precedents');
  if (list.length === 0) {
    $('#precedentList').innerHTML = '<li class="muted">No precedents yet.</li>';
    return;
  }
  $('#precedentList').innerHTML = list.slice(-6).reverse().map(function (p) {
    return '<li><b>' + esc(p.merchantId) + '</b>: ' + esc((p.issues[0] || '').slice(0, 80)) + '</li>';
  }).join('');
}

// =========================================================
// Courtroom: run a case and show each step as it arrives
// =========================================================
function clearCaseView() {
  rounds.clear();
  $('#docket').innerHTML = '';
  $('#summary').className = 'summary-text muted';
  $('#summary').textContent = 'Case in progress...';
  $('#counterfactual').classList.add('hidden');
  $('#receiptCard').classList.add('hidden');
  setMetrics('–', '–', '–', '–');
  $('#metricsNote').textContent = 'Measured on the server for every case.';
}

async function runCase(orderId) {
  running = true;
  $('#simApprove').disabled = true;
  clearCaseView();

  const response = await fetch('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ orderId: orderId, scenarioId: currentScenario().id, rules: readRules() }),
  });

  // The server sends one JSON event per line. We queue them and show them at a
  // steady pace, so people watching the demo can follow each step.
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const queue = [];
  let leftover = '';
  let finished = false;

  const player = (async function () {
    while (!finished || queue.length > 0) {
      if (queue.length === 0) { await sleep(50); continue; }
      const event = queue.shift();
      render(event);
      await sleep(PACE[event.type] || 300);
    }
  })();

  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    leftover += decoder.decode(chunk.value, { stream: true });
    const lines = leftover.split('\n');
    leftover = lines.pop();
    lines.forEach(function (line) { if (line.trim()) queue.push(JSON.parse(line)); });
  }
  finished = true;
  await player;

  running = false;
  $('#simApprove').disabled = false;
  loadPrecedents();
}

// Milliseconds to pause after showing each kind of event.
const PACE = {
  hold: 500, reading: 700, proposal: 700, risk: 600, facts: 600, rules: 700, trial_open: 500,
  argument: 1100, escalate: 700, verdict: 1100, sent_back: 800, payment: 700,
};

function render(event) {
  const round = rounds.get(event.round);
  const body = round ? round.querySelector('.round-body') : null;

  switch (event.type) {
    case 'hold':
      $('#hold').className = 'hold held';
      $('#hold').innerHTML = 'PayPal holding <b>' + money(event.amount) + '</b>';
      addToDocket('<div class="notice-line">PayPal placed a hold of <b>' + money(event.amount) + '</b> <span class="mono">' +
        esc(event.authorizationId) + '</span>. No money has moved.</div>');
      break;

    case 'reading': {
      const total = event.offers.length;
      let text = 'Read the fine print of ' + total + ' offer(s) ' + (event.parallel ? 'all at once (parallel).' : 'one at a time.');
      if (event.fromCache === total) {
        text = 'Fine print of ' + total + ' offer(s) already read before: <b>all from cache, no AI calls</b>.';
      } else if (event.fromCache > 0) {
        text = text + ' <b>' + event.fromCache + ' from cache</b>, no AI needed.';
      }
      addToDocket('<div class="notice-line">' + text + '</div>');
      break;
    }

    case 'proposal': {
      const tested = event.offer.trialTested ? '<span class="badge tested">Trial-Tested</span>' : '';
      const el = document.createElement('article');
      el.className = 'round';
      el.innerHTML =
        '<div class="round-head"><span class="round-num">Round ' + event.round + '</span><span class="muted">Shopping agent proposes</span></div>' +
        '<div class="offer"><div>' +
          '<h3>' + esc(event.offer.title) + '</h3>' +
          '<p class="merchant">' + esc(event.offer.merchant) + ' ' + tested + '</p>' +
          '<p class="reason">"' + esc(event.reason) + '"</p>' +
        '</div><div class="price">' + money(event.offer.advertised) + '<small>advertised</small></div></div>' +
        '<details class="evidence"><summary>Fine print on file (' + event.offer.evidence.length + ' lines)</summary><ul>' +
          event.offer.evidence.map(function (line) {
            return '<li data-ev="' + line.id + '"><span class="chip">' + line.id + '</span> <em>' + esc(line.source) + '</em> ' + esc(line.text) + '</li>';
          }).join('') +
        '</ul></details>' +
        '<div class="round-body"></div>';
      $('#docket').appendChild(el);
      rounds.set(event.round, el);
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      break;
    }

    case 'risk':
      addBlock(body,
        '<div class="block"><div class="row"><span class="label">Risk score (code, instant)</span>' +
        '<span class="tierbadge ' + event.tier + '">' + event.tier.toUpperCase() + ' · ' + event.score + '</span></div><ul>' +
        event.reasons.map(function (r) {
          return '<li><span class="pts ' + (r.points < 0 ? 'neg' : '') + '">' + (r.points > 0 ? '+' : '') + r.points + '</span>' + esc(r.label) + '</li>';
        }).join('') + '</ul></div>');
      break;

    case 'facts': {
      const f = event.facts;
      addBlock(body,
        '<div class="block"><div class="row"><span class="label">Fine print turned into numbers</span>' + modeTag(event.mode) + '</div>' +
        '<div class="facts-grid">' +
          fact('Due today', money(f.totalDueToday), false) +
          fact('Recurring', f.recurring ? money(f.recurring.amount) + '/' + f.recurring.interval : 'None', !!f.recurring) +
          fact('Cost to return', f.returnCost === null ? 'Unknown' : (f.returnCost === 0 ? 'Free' : money(f.returnCost)), f.returnCost > 0) +
          fact('First-year cost', money(f.yearCost), f.yearCost > f.totalDueToday + 0.01) +
        '</div>' +
        ((f.safetyNet || []).length
          ? '<p class="muted small">Safety net: the pattern checker also caught the ' + esc(f.safetyNet.join(', ')) + ' the AI missed.</p>'
          : '') +
        '</div>');
      break;
    }

    case 'rules':
      addBlock(body,
        '<div class="block rules"><div class="row"><span class="label">Guardian rules, checked by code</span><span class="muted small">' + esc(event.source) + '</span></div><ul>' +
        event.results.map(function (r) {
          return '<li class="' + (r.passed ? 'pass' : 'fail') + '"><span class="mark">' + (r.passed ? '✓' : '✕') + '</span><span><b>' +
            esc(r.rule) + '</b> ' + esc(r.detail) + ' ' + chips(r.evidence, event.round) + '</span></li>';
        }).join('') + '</ul></div>');
      break;

    case 'escalate':
      addBlock(body, '<div class="notice">' + esc(event.reason) + '</div>');
      break;

    case 'trial_open':
      addBlock(body, '<div class="session">Court is in session</div>');
      break;

    case 'argument': {
      let title = 'Defense';
      if (event.agent === 'prosecutor') title = event.quick ? 'Quick check' : 'Prosecution';
      const points = event.arguments.length
        ? '<ul>' + event.arguments.map(function (a) {
            return '<li><span class="sev ' + a.severity + '">' + a.severity + '</span>' + esc(a.point) + ' ' + chips(a.evidence, event.round) + '</li>';
          }).join('') + '</ul>'
        : '<p class="muted small">No issues raised.</p>';
      const dropped = event.dropped ? '<p class="muted small">' + event.dropped + ' point(s) dropped for citing evidence that does not exist.</p>' : '';
      addBlock(body,
        '<div class="block argument ' + event.agent + '"><div class="row"><span class="label">' + title + '</span>' + modeTag(event.mode) + '</div>' +
        points + dropped + '</div>');
      break;
    }

    case 'verdict': {
      const decidedLabels = {
        'code': 'Decided by code · no AI needed',
        'quick check': 'Decided by one quick AI check',
        'trial': 'Decided at trial',
      };
      const findings = (event.keyFindings || []).length
        ? '<ul class="findings">' + event.keyFindings.map(function (k) { return '<li>' + esc(k.point) + ' ' + chips(k.evidence, event.round) + '</li>'; }).join('') + '</ul>'
        : '';
      addBlock(body,
        '<div class="verdict ' + (event.verdict === 'APPROVE' ? 'ok' : 'no') + '">' +
        '<div class="stamp">' + (event.verdict === 'APPROVE' ? 'APPROVED' : 'REJECTED') + '</div><div>' +
        '<span class="decided">' + esc(decidedLabels[event.decidedBy] || event.decidedBy) + '</span>' +
        '<p>' + esc(event.reasoning) + '</p>' +
        (event.overruled ? '<p class="overruled">' + esc(event.overruled) + '</p>' : '') +
        findings + '</div></div>');
      break;
    }

    case 'sent_back':
      addBlock(body, '<div class="notice back">' +
        (event.remaining ? 'Agent sent back to find a better deal. ' + event.remaining + ' option(s) left.' : 'No options left.') + '</div>');
      break;

    case 'payment':
      if (event.action === 'capture') {
        addToDocket('<div class="payment capture"><b>PayPal captured ' + money(event.amount) + '</b> for the approved purchase. ' +
          money(event.released) + ' of the hold released. <span class="mono">' + esc(event.captureId) + '</span></div>');
        $('#hold').className = 'hold capture';
        $('#hold').textContent = 'Captured ' + money(event.amount);
      } else {
        addToDocket('<div class="payment void"><b>PayPal voided the hold.</b> ' + money(event.released) + ' released. Nothing was charged.</div>');
        $('#hold').className = 'hold void';
        $('#hold').textContent = 'Hold voided';
      }
      break;

    case 'counterfactual':
      showCounterfactual(event);
      break;

    case 'metrics':
      showCaseMetrics(event);
      break;

    case 'summary':
      $('#summary').className = 'summary-text';
      $('#summary').innerHTML = event.text.split('\n').map(function (line) { return '<p>' + esc(line) + '</p>'; }).join('');
      break;

    case 'receipt':
      $('#receiptCard').classList.remove('hidden');
      $('#receiptCard').innerHTML =
        '<h2>Receipt ' + esc(event.id) + '</h2>' +
        '<p class="muted small">Saved and chained to the previous receipt.</p>' +
        '<div class="hash">' + esc(event.hash.slice(0, 32)) + '…</div>' +
        '<p><a href="#receipts" data-open="' + esc(event.id) + '" class="open-receipt">Open in Receipts →</a></p>';
      break;

    case 'error':
      showError(event.message);
      break;
  }
}

function addToDocket(html) {
  $('#docket').insertAdjacentHTML('beforeend', html);
  $('#docket').lastElementChild.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function addBlock(container, html) {
  if (!container) return;
  container.insertAdjacentHTML('beforeend', html);
  container.lastElementChild.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function fact(label, value, alarm) {
  return '<div class="fact ' + (alarm ? 'alarm' : '') + '"><span>' + label + '</span><b>' + value + '</b></div>';
}

function modeTag(mode) {
  const labels = { live: 'AI', mock: 'AI (mock)', offline: 'offline analyzer', cache: 'from cache · no AI' };
  if (!mode) return '';
  return '<span class="mode ' + mode + '">' + (labels[mode] || mode) + '</span>';
}

// Evidence chips: click one to highlight the exact line of fine print it cites.
function chips(ids, round) {
  return (ids || []).map(function (id) {
    return '<button class="chip" type="button" data-round="' + round + '" data-ev="' + esc(id) + '">' + esc(id) + '</button>';
  }).join('');
}

document.addEventListener('click', function (event) {
  const chip = event.target.closest('button.chip');
  if (chip) {
    const round = rounds.get(Number(chip.dataset.round));
    if (!round) return;
    const details = round.querySelector('details.evidence');
    details.open = true;
    const line = details.querySelector('li[data-ev="' + chip.dataset.ev + '"]');
    if (line) {
      line.classList.remove('flash');
      void line.offsetWidth;   // restart the animation
      line.classList.add('flash');
      line.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
  const openLink = event.target.closest('a.open-receipt');
  if (openLink) {
    selectedReceipt = openLink.dataset.open;
  }
});

function setMetrics(calls, seconds, byCode, cache) {
  const values = [calls, seconds, byCode, cache];
  document.querySelectorAll('#caseMetrics .metric b').forEach(function (b, i) { b.textContent = values[i]; });
}

function showCaseMetrics(m) {
  setMetrics(m.aiCalls, m.seconds.toFixed(2), m.decidedByCode, m.cacheHits);
  let note = '';
  if (m.aiMode === 'offline') {
    note = 'Offline analyzer: no AI used (' + m.offlineSteps + ' offline steps).';
  } else {
    const tokens = m.inputTokens + m.outputTokens;
    const cost = m.pricesSet ? '$' + m.cost.toFixed(4) : 'add prices in .env to see cost';
    note = m.aiMode + ' AI · ' + tokens.toLocaleString() + ' tokens · ' + cost + (m.fallbacks ? ' · ' + m.fallbacks + ' fallback(s)' : '');
  }
  $('#metricsNote').textContent = note;
}

function showCounterfactual(cf) {
  const card = $('#counterfactual');
  card.classList.remove('hidden');
  let chosen = '<div class="cf-row"><span>With Countersign</span><b>Nothing bought: $0.00</b></div>';
  if (cf.chosenTitle) {
    chosen = '<div class="cf-row"><span>With Countersign: ' + esc(cf.chosenTitle) + '</span><b>' + money(cf.chosenYearCost) + '</b></div>';
  }
  card.innerHTML =
    '<h2>Without Countersign</h2>' +
    '<p class="muted small">A naive agent buys the cheapest-looking offer.</p>' +
    '<div class="cf-row"><span>' + esc(cf.naiveTitle) + ' (' + money(cf.naiveAdvertised) + ' advertised), first year</span><b>' + money(cf.naiveYearCost) + '</b></div>' +
    chosen +
    (cf.saved > 0
      ? '<div class="cf-saved">Saved ' + money(cf.saved) + ' in the first year</div>'
      : '<div class="cf-saved">The cheapest offer was already safe.</div>');
}

function showError(message) {
  addToDocket('<div class="payment void"><b>Error:</b> ' + esc(message) + '</div>');
  $('#summary').textContent = 'The case stopped with an error.';
}

// =========================================================
// Receipts tab
// =========================================================
let selectedReceipt = null;

async function loadReceipts() {
  const list = await getJSON('/api/receipts');
  if (list.length === 0) {
    $('#receiptList').innerHTML = '<li class="muted">No receipts yet. Run a case in the Courtroom.</li>';
    return;
  }
  $('#receiptList').innerHTML = list.map(function (r) {
    const outcome = r.outcome === 'approved' ? 'Paid ' + money(r.amount) : 'Voided';
    return '<li data-id="' + r.id + '"><div class="r-top"><span>' + r.id + '</span><span>' + outcome + '</span></div>' +
      '<div class="muted small">' + esc(r.request) + '</div>' +
      '<div class="mono muted">' + r.hash.slice(0, 16) + '… · ' + new Date(r.createdAt).toLocaleString() + '</div></li>';
  }).join('');
  document.querySelectorAll('#receiptList li[data-id]').forEach(function (li) {
    li.addEventListener('click', function () { showReceipt(li.dataset.id); });
  });
  showReceipt(selectedReceipt || list[0].id);
}

async function showReceipt(id) {
  selectedReceipt = id;
  document.querySelectorAll('#receiptList li').forEach(function (li) { li.classList.toggle('selected', li.dataset.id === id); });
  const receipt = await getJSON('/api/receipts/' + id);
  if (receipt.error) return;
  const b = receipt.body;
  const offers = b.offers.map(function (o) {
    return '<tr><td>' + esc(o.merchant) + '</td><td>' + o.tier + '</td><td>' + esc(o.decidedBy) + '</td><td>' + o.verdict + '</td><td class="num">' + money(o.facts.yearCost) + '</td></tr>';
  }).join('');
  $('#receiptDetail').innerHTML =
    '<h2>' + receipt.id + '</h2>' +
    '<div class="kv">' +
      '<span>Request</span><b>' + esc(b.request) + '</b>' +
      '<span>Outcome</span><b>' + (b.outcome === 'approved' ? 'Approved, ' + money(b.payment.amount) + ' captured' : 'Voided, nothing charged') + '</b>' +
      '<span>PayPal mode</span><b>' + b.payment.paypalMode + '</b>' +
      '<span>PayPal order</span><span class="mono">' + esc(b.payment.orderId || '–') + '</span>' +
      '<span>Authorization</span><span class="mono">' + esc(b.payment.authorizationId) + '</span>' +
      '<span>Capture</span><span class="mono">' + esc(b.payment.captureId || '–') + '</span>' +
      '<span>AI mode</span><b>' + b.aiMode + ' · ' + b.metrics.aiCalls + ' AI calls · ' + b.metrics.seconds.toFixed(2) + ' s</b>' +
      '<span>Saved vs naive agent</span><b>' + money(b.counterfactual.saved) + ' in the first year</b>' +
      '<span>Created</span><span>' + new Date(receipt.createdAt).toLocaleString() + '</span>' +
    '</div>' +
    '<h3>Hash chain</h3>' +
    '<p class="muted small">This receipt\'s hash</p><div class="hash">' + receipt.hash + '</div>' +
    '<p class="muted small">Previous receipt\'s hash</p><div class="hash">' + receipt.previousHash + '</div>' +
    '<h3 style="margin-top:14px">Offers</h3>' +
    '<div class="table-wrap"><table><thead><tr><th>Merchant</th><th>Risk</th><th>Decided by</th><th>Verdict</th><th>First-year cost</th></tr></thead><tbody>' + offers + '</tbody></table></div>' +
    '<details style="margin-top:12px"><summary>Full receipt (JSON)</summary><pre class="json">' + esc(JSON.stringify(receipt, null, 2)) + '</pre></details>';
}

async function verifyChain() {
  const result = await getJSON('/api/receipts/verify');
  if (result.ok) {
    $('#chainStatus').innerHTML = '<div class="status-banner ok">✓ Chain verified: all ' + result.checked + ' receipt(s) are untouched and correctly linked.</div>';
  } else {
    $('#chainStatus').innerHTML = '<div class="status-banner bad">✕ Chain broken at ' + esc(result.brokenAt) + ': ' + esc(result.problem) + '.</div>';
  }
}

// =========================================================
// Dashboard tab
// =========================================================
async function loadDashboard() {
  const s = await getJSON('/api/stats');
  const tiles = [
    ['Cases run', s.cases, ''],
    ['Approved spend', money(s.approvedSpend), 'captured through PayPal'],
    ['First-year charges blocked', money(s.blockedFirstYear), 'vs a naive agent'],
    ['Offers decided by code', s.decidedByCodePercent + '%', 'no AI needed'],
    ['AI calls per case', s.avgAiCalls, 'average'],
    ['Seconds per case', s.avgSeconds, 'average'],
    ['Trials held', s.trials, 'gray areas only'],
  ];
  $('#tiles').innerHTML = tiles.map(function (t) {
    return '<div class="tile"><span>' + t[0] + '</span><b>' + t[1] + '</b><small>' + t[2] + '</small></div>';
  }).join('');
  if (s.recent.length === 0) {
    $('#recentTable').innerHTML = '<tr><td class="muted">No cases yet. Run one in the Courtroom.</td></tr>';
    return;
  }
  $('#recentTable').innerHTML =
    '<thead><tr><th>Receipt</th><th>Request</th><th>Outcome</th><th>Charged</th><th>Saved</th><th>AI calls</th><th>Seconds</th><th>AI mode</th></tr></thead><tbody>' +
    s.recent.map(function (r) {
      return '<tr><td>' + r.id + '</td><td>' + esc(r.request) + '</td><td>' + r.outcome + '</td><td class="num">' + money(r.amount) +
        '</td><td class="num">' + money(r.saved) + '</td><td class="num">' + r.aiCalls + '</td><td class="num">' + r.seconds.toFixed(2) + '</td><td>' + r.aiMode + '</td></tr>';
    }).join('') + '</tbody>';
}

// =========================================================
// Evaluation tab
// =========================================================
let evalData = null;

async function loadEval() {
  evalData = await getJSON('/api/eval');
  showScoreboard();
  showBenchmark();
  $('#runPicker').innerHTML = evalData.runs.map(function (run, i) {
    return '<option value="' + i + '">' + run.config + ' / ' + run.split + '</option>';
  }).join('');
  showOfferTable();
}

function calls(count) {
  return count + (count === 1 ? ' AI call' : ' AI calls');
}

function barChip(bar) {
  if (!bar || bar.passed === null) return '<span class="na-chip">n/a</span>';
  return bar.passed ? '<span class="pass-chip">PASS</span>' : '<span class="fail-chip">FAIL</span>';
}

function showScoreboard() {
  if (evalData.runs.length === 0) {
    $('#scoreboard').innerHTML = '<tr><td class="muted">No results yet. Run: python -m evals.run --config offline --split dev</td></tr>';
    return;
  }
  $('#scoreboard').innerHTML =
    '<thead><tr><th>Configuration</th><th>Split</th><th>Accuracy</th><th>Traps approved</th><th>Good offers blocked</th><th>Field accuracy</th><th>Fallback rate</th><th>Median s</th><th>AI calls / offer</th><th>Cost / offer</th></tr></thead><tbody>' +
    evalData.runs.map(function (run) {
      const s = run.summary;
      const bar = function (name) { return s.bars.find(function (b) { return b.metric === name; }); };
      return '<tr><td><b>' + run.config + '</b><div class="muted small">' + (run.config === 'offline' ? 'no AI model' : esc(run.models.fast) + ' / ' + esc(run.models.judge)) + '</div></td>' +
        '<td>' + run.split + ' · ' + s.offers + ' × ' + run.repeats + '</td>' +
        '<td class="num">' + percent(s.accuracy) + '</td>' +
        '<td class="num">' + s.falseApprovals.length + barChip(bar('Traps approved')) + '</td>' +
        '<td class="num">' + s.falseRejections.length + barChip(bar('Good offers blocked')) + '</td>' +
        '<td class="num">' + percent(s.fieldAccuracy) + barChip(bar('Field accuracy')) + '</td>' +
        '<td class="num">' + percent(s.fallbackRate) + barChip(bar('Fallback rate')) + '</td>' +
        '<td class="num">' + s.medianSeconds.toFixed(2) + '</td>' +
        '<td class="num">' + s.avgAiCalls.toFixed(1) + '</td>' +
        '<td class="num">$' + s.avgCost.toFixed(4) + '</td></tr>';
    }).join('') + '</tbody>';
  $('#scoreNote').textContent = 'The offline analyzer is the baseline without AI. Run the "mixed" configuration with your key to score the real agents; the bar to ship is 0 traps approved on the test split.';
}

function showBenchmark() {
  const b = evalData.benchmark;
  if (!b) {
    $('#benchmark').innerHTML = '<p class="muted">No benchmark yet. Run: python -m evals.benchmark</p>';
    return;
  }
  let most = 1;
  b.comparison.forEach(function (row) { most = Math.max(most, row.oldCalls, row.newCalls); });
  $('#benchmark').innerHTML =
    '<p class="muted small">' + esc(b.note) + ' Same verdicts in both designs: ' +
    (b.comparison.every(function (r) { return r.sameVerdicts; }) ? 'yes' : 'NO') + '.</p>' +
    '<div class="bars">' + b.comparison.map(function (row) {
      // Each bar is as long as its number of AI calls; the label sits next to it.
      const oldWidth = Math.max(1, 70 * row.oldCalls / most);
      const newWidth = Math.max(1, 70 * row.newCalls / most);
      return '<div class="bar-row"><div><b>' + esc(row.scenario) + '</b><div class="muted small">' + row.run + '</div></div>' +
        '<div class="bar-pair">' +
        '<div class="bar-line"><div class="bar old" style="width:' + oldWidth + '%"></div><span>Old: ' + calls(row.oldCalls) + ' · ' + row.oldSeconds.toFixed(1) + ' s</span></div>' +
        '<div class="bar-line"><div class="bar new" style="width:' + newWidth + '%"></div><span><b>New: ' + calls(row.newCalls) + ' · ' + row.newSeconds.toFixed(1) + ' s</b></span></div>' +
        '</div></div>';
    }).join('') + '</div>';
}

function showOfferTable() {
  if (!evalData || evalData.runs.length === 0) {
    $('#offerTable').innerHTML = '';
    return;
  }
  const run = evalData.runs[Number($('#runPicker').value || 0)];
  const check = function (ok) { return ok ? '✓' : '<b style="color:var(--no)">✕</b>'; };
  $('#offerTable').innerHTML =
    '<thead><tr><th>Offer</th><th>Group</th><th>Expected</th><th>Got</th><th>Decided by</th><th>Total</th><th>Recurring</th><th>Return cost</th><th>Hidden fees</th><th>Seconds</th><th>Why</th></tr></thead><tbody>' +
    run.rows.map(function (r) {
      return '<tr class="' + (r.correct ? '' : 'miss') + '"><td><b>' + r.id + '</b> ' + esc(r.title) + '</td><td>' + r.group + '</td><td>' + r.expected +
        '</td><td>' + r.got + '</td><td>' + esc(r.decidedBy) + '</td><td>' + check(r.fieldChecks.total) + '</td><td>' + check(r.fieldChecks.recurring) +
        '</td><td>' + check(r.fieldChecks.returnCost) + '</td><td>' + check(r.fieldChecks.hiddenFees) + '</td><td class="num">' + r.seconds.toFixed(2) +
        '</td><td class="muted small">' + esc(r.reason) + '</td></tr>';
    }).join('') + '</tbody>';
}
