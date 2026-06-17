const $ = (s) => document.querySelector(s);
const money = (n) => (n < 0 ? "-$" : "$") + Math.abs(Math.round(n)).toLocaleString("en-US");
const money2 = (n) => (n < 0 ? "-$" : "$") + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
let DATA = null;
let didAutoSync = false;

async function api(p, o) {
  const r = await fetch(p, o);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

async function load() {
  DATA = await api("/api/dashboard");
  const history = await api("/api/history").catch(() => []);
  drawTicks();
  renderCore(history);
  drawChart(history);
  renderAccounts();
  renderGauge();
  renderDonut();
  renderGoals();
  renderRoad();
  renderFlow();
  renderPlan();
  renderEnvelopes();
  renderRecurring();
  renderActivity();
  let synced = "AWAITING LINK";
  if (DATA.last_sync) { const d = new Date(DATA.last_sync); synced = isNaN(d) ? "DEMO MODE" : d.toLocaleString(); }
  $("#footStatus").textContent = synced + " · " + DATA.plaid_env.toUpperCase();
  $("#liveTxt").textContent = DATA.accounts.length ? "SYNCED" : "OFFLINE";
  $("#connectBtn").classList.toggle("hidden", DATA.accounts.length > 0);

  // Fully automatic: refresh from your banks once each time you open the app.
  if (DATA.accounts.length && !didAutoSync) {
    didAutoSync = true;
    $("#liveTxt").textContent = "SYNCING";
    api("/api/sync", { method: "POST" }).then(() => load()).catch(() => {});
  }
}

function drawTicks() {
  const g = $("#ticks"); g.innerHTML = "";
  for (let i = 0; i < 60; i++) {
    const a = (i / 60) * Math.PI * 2, big = i % 5 === 0;
    const r1 = big ? 84 : 88, r2 = 92;
    const x1 = 120 + Math.cos(a) * r1, y1 = 120 + Math.sin(a) * r1;
    const x2 = 120 + Math.cos(a) * r2, y2 = 120 + Math.sin(a) * r2;
    g.insertAdjacentHTML("beforeend", `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" style="opacity:${big ? .5 : .22}"/>`);
  }
}

function renderCore(history) {
  $("#netWorth").textContent = money(DATA.net_worth.net_worth);
  if (history.length > 1) {
    const first = history[0].net_worth, last = history[history.length - 1].net_worth;
    const pct = first ? ((last - first) / first) * 100 : 0;
    const up = pct >= 0;
    const el = $("#nwDelta");
    el.textContent = `${up ? "▲" : "▼"} ${money(Math.abs(last - first))}  (${up ? "+" : ""}${pct.toFixed(1)}%) · 45D`;
    el.classList.toggle("down", !up);
  }
}

function drawChart(history) {
  const svg = $("#chart");
  if (history.length < 2) { svg.innerHTML = ""; $("#chartReadout").textContent = ""; return; }
  const W = 600, H = 200, pad = 14;
  const vals = history.map((h) => h.net_worth);
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  const X = (i) => (i / (history.length - 1)) * W;
  const Y = (v) => H - pad - ((v - min) / span) * (H - pad * 2);
  let d = `M ${X(0)} ${Y(vals[0])}`;
  for (let i = 1; i < vals.length; i++) d += ` L ${X(i)} ${Y(vals[i])}`;
  const area = d + ` L ${W} ${H} L 0 ${H} Z`;
  const ex = X(vals.length - 1), ey = Y(vals[vals.length - 1]);
  svg.innerHTML = `
    <defs>
      <linearGradient id="cyanGrad" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="#3B82F6"/><stop offset="1" stop-color="#34E3FF"/></linearGradient>
      <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="rgba(52,227,255,.28)"/><stop offset="1" stop-color="rgba(52,227,255,0)"/></linearGradient>
    </defs>
    <path class="chart-area" d="${area}"/>
    <path class="chart-line" d="${d}" id="cline"/>
    <circle class="chart-dot" cx="${ex}" cy="${ey}" r="4"/>`;
  const line = $("#cline"), len = line.getTotalLength();
  line.style.strokeDasharray = len; line.style.strokeDashoffset = len;
  requestAnimationFrame(() => { line.style.transition = "stroke-dashoffset 1.4s ease"; line.style.strokeDashoffset = 0; });
  $("#chartReadout").textContent = `${money(min)} – ${money(max)}`;
  $("#chartRange").textContent = `${history[0].date.slice(5)} → ${history[history.length - 1].date.slice(5)}`;
}

function renderAccounts() {
  const el = $("#accounts");
  if (!DATA.accounts.length) { el.innerHTML = `<div class="acct"><div class="a-name">No accounts linked</div><div class="a-type">TAP LINK ACCOUNT</div><div class="a-bal">—</div></div>`; return; }
  const maxBal = Math.max(...DATA.accounts.map((a) => Math.abs(a.current || 0)), 1);
  el.innerHTML = DATA.accounts.map((a, i) => {
    const inv = a.type === "investment";
    const w = Math.max(12, (Math.abs(a.current || 0) / maxBal) * 100);
    return `<div class="acct ${inv ? "inv" : ""} stagger" style="animation-delay:${i * 70}ms">
      <div class="a-name">${a.name}</div>
      <div class="a-type">${(a.subtype || a.type || "").toUpperCase()}</div>
      <div class="a-bal">${money(a.current || 0)}</div>
      <div class="a-bar" style="width:${w}%"></div></div>`;
  }).join("");
}

function renderGauge() {
  const w = DATA.wealth, C = 2 * Math.PI * 64;
  const frac = w.checking > 0 ? Math.min(1, w.safe_to_invest / w.checking) : 0;
  const f = $("#gFill");
  f.style.strokeDasharray = `${C} ${C}`;
  f.style.strokeDashoffset = C;
  requestAnimationFrame(() => { f.style.strokeDashoffset = C * (1 - frac); });
  $("#safeInvest").textContent = money(w.safe_to_invest);
  $("#investNote").innerHTML =
    `Buffer held: <b style="color:var(--text)">${money(w.buffer_target)}</b> · budget reserved: <b style="color:var(--text)">${money(w.committed_to_budget)}</b>` +
    (w.income_this_month ? `<br>Pay yourself first: <b style="color:var(--mint)">${money(w.pay_yourself_first)}</b> (${w.savings_rate_pct}%)` : "");
}

function renderDonut() {
  const nw = DATA.net_worth, C = 2 * Math.PI * 64;
  const segs = [
    { k: "Cash", v: Math.max(0, nw.cash), c: "#34E3FF" },
    { k: "Investments", v: Math.max(0, nw.investments), c: "#3DF5A0" },
    { k: "Debt", v: Math.max(0, nw.debt), c: "#FF5C7A" },
  ];
  const total = segs.reduce((s, x) => s + x.v, 0) || 1;
  let off = 0, circles = `<circle class="g-track" cx="80" cy="80" r="64"/>`;
  segs.forEach((s) => {
    const len = (s.v / total) * C;
    circles += `<circle cx="80" cy="80" r="64" fill="none" stroke="${s.c}" stroke-width="12"
      stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-off}"
      style="filter:drop-shadow(0 0 5px ${s.c}aa);transition:stroke-dasharray 1s ease"/>`;
    off += len;
  });
  $("#donut").innerHTML = circles;
  $("#allocLegend").innerHTML = segs.map((s) =>
    `<div class="leg"><span class="sw" style="background:${s.c};box-shadow:0 0 6px ${s.c}"></span>${s.k}<span class="v">${money(s.v)}</span></div>`
  ).join("");
}

function renderGoals() {
  const C = 2 * Math.PI * 40;
  $("#goals").innerHTML = (DATA.goals || []).map((g, i) => {
    const off = C * (1 - g.pct / 100);
    return `<div class="goal stagger" style="animation-delay:${i * 80}ms">
      <div class="gring"><svg viewBox="0 0 96 96">
        <circle class="gt" cx="48" cy="48" r="40"/>
        <circle class="gf" cx="48" cy="48" r="40" stroke="${g.accent}"
          stroke-dasharray="${C}" stroke-dashoffset="${C}" data-off="${off}"
          style="filter:drop-shadow(0 0 5px ${g.accent}aa)"/></svg>
        <div class="gpct" style="color:${g.accent}">${Math.round(g.pct)}%</div></div>
      <div class="gname">${g.name}</div>
      <div class="gval">${money(g.saved)} / ${money(g.target)}</div></div>`;
  }).join("");
  requestAnimationFrame(() => document.querySelectorAll("#goals .gf").forEach((c) => { c.style.strokeDashoffset = c.dataset.off; }));
}

function renderRoad() {
  const r = DATA.road;
  if (!r) { $("#road").innerHTML = ""; return; }
  const W = 560, H = 60, s = r.series, mn = Math.min(...s), mx = Math.max(...s), sp = mx - mn || 1;
  const X = (i) => (i / (s.length - 1)) * W, Y = (v) => H - ((v - mn) / sp) * H;
  let d = `M ${X(0)} ${Y(s[0])}`;
  for (let i = 1; i < s.length; i++) d += ` L ${X(i)} ${Y(s[i])}`;
  $("#road").innerHTML = `
    <div class="road-top">
      <div><div class="road-now">${money(r.current)}</div><div class="eyebrow tiny">OF $100,000 GOAL</div></div>
      <div class="road-pct">${r.pct}%</div>
    </div>
    <div class="road-bar"><div class="road-fill" style="width:0%" data-w="${r.pct}%"></div></div>
    <svg class="road-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
      <defs><linearGradient id="rg" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#3DF5A0"/><stop offset="1" stop-color="#34E3FF"/></linearGradient></defs>
      <path d="${d}" fill="none" stroke="url(#rg)" stroke-width="2.5" style="filter:drop-shadow(0 0 6px rgba(61,245,160,.5))"/></svg>
    <div class="road-foot">On pace: <b>~${r.years} yrs</b> · ETA <b style="color:var(--mint)">${r.eta}</b>
      &nbsp;·&nbsp; investing <b>${money(r.monthly_contribution)}/mo</b> at ${r.annual_return_pct}% est.</div>`;
  requestAnimationFrame(() => { const f = $("#road .road-fill"); if (f) f.style.width = f.dataset.w; });
}

function renderFlow() {
  const a = DATA.allocation;
  if (!a) { $("#flow").innerHTML = ""; return; }
  $("#incomeTag").textContent = money(a.income) + "/MO";
  const segs = a.buckets.map((b) =>
    `<div class="flow-seg" style="flex:${b.pct};background:${b.accent}"></div>`).join("");
  const rows = a.buckets.map((b) => {
    const st = b.status === "over" ? "over" : b.status === "under" ? "under" : "ok";
    const stxt = b.status === "over" ? "over plan" : b.status === "under" ? "room left" : "on track";
    return `<div class="flow-row">
      <span class="flow-dot" style="background:${b.accent};box-shadow:0 0 6px ${b.accent}"></span>
      <span class="flow-name">${b.name}</span><span class="flow-pct">${b.pct}%</span>
      <span class="flow-vals">${money(b.actual)} <span class="muted">/ ${money(b.target)}</span></span>
      <span class="flow-status ${st}">${stxt}</span></div>`;
  }).join("");
  $("#flow").innerHTML = `
    <div class="flow-summary">
      <div class="fs-row"><span>Income</span><span class="fs-v">${money(a.income)}</span></div>
      <div class="fs-row sub"><span>− Bills (wired out)</span><span class="fs-v">${money(a.bills)}</span></div>
      <div class="fs-row total"><span>Spendable</span><span class="fs-v">${money(a.spendable)}</span></div>
    </div>
    <div class="eyebrow tiny" style="margin:4px 0 10px;color:var(--cyan-dim)">PAY YOURSELF FIRST · split of spendable</div>
    <div class="flow-bar">${segs}</div><div class="flow-rows">${rows}</div>`;
}

function renderPlan() {
  const p = DATA.plan;
  if (!p) { $("#waterfall").innerHTML = ""; return; }
  $("#surplusTag").textContent = "+" + money(p.monthly_surplus) + "/MO FREE";
  $("#waterfall").innerHTML = p.stages.map((s) => {
    const state = s.done ? "done" : s.n === p.active ? "active" : s.n < p.active ? "done" : "locked";
    const tag = state === "done" ? "✓ DONE" : state === "active" ? "IN PROGRESS" : "LOCKED";
    return `<div class="stage ${state}">
      <div class="badge">${state === "done" ? "✓" : s.n}</div>
      <div class="stage-body">
        <div class="stage-top"><span class="stage-title">${s.title}</span>
        ${state !== "locked" ? `<span class="stage-tag">${tag}</span>` : ""}</div>
        <div class="stage-target">${s.target}</div>
        <div class="stage-why">${s.why}</div></div></div>`;
  }).join("");
}

function renderEnvelopes() {
  const left = DATA.envelopes.reduce((s, e) => s + Math.max(0, e.remaining), 0);
  $("#leftTag").textContent = money(left) + " LEFT";
  const el = $("#envelopes");
  el.innerHTML = DATA.envelopes.filter((e) => e.allocated > 0 || e.spent > 0).map((e) => {
    const cls = e.remaining < 0 ? "over" : e.pct_used >= 80 ? "warn" : "good";
    return `<div class="env ${cls}">
      <div class="env-top"><div><span class="env-name">${e.name}</span><span class="env-meta">${money(e.spent)} / ${money(e.allocated)}</span></div>
      <div class="env-remaining">${money(e.remaining)}</div></div>
      <div class="track"><div class="fill" style="width:${Math.min(100, e.pct_used)}%"></div></div></div>`;
  }).join("");
}

function renderRecurring() {
  const r = DATA.recurring;
  if (!r || !r.items.length) { $("#recurList").innerHTML = `<div style="color:var(--muted);padding:16px;font-size:13px">No recurring charges detected yet.</div>`; $("#recurTag").textContent = ""; return; }
  $("#recurTag").textContent = money(r.total) + "/MO";
  $("#recurList").innerHTML = r.items.map((i) =>
    `<div class="txn"><div><div class="n">${i.name}</div>
      <div class="c">${i.envelope}${i.count > 1 ? " · " + i.count + "x" : " · monthly"}</div></div>
      <div class="amt">${money2(i.amount)}</div></div>`).join("");
}

async function renderActivity() {
  const txns = await api("/api/transactions?limit=40").catch(() => []);
  const el = $("#txnList");
  if (!txns.length) { el.innerHTML = `<div style="color:var(--muted);padding:16px;font-size:13px">No activity yet. Sync after linking.</div>`; return; }
  el.innerHTML = txns.map((t) => {
    const inflow = t.amount < 0;
    return `<div class="txn"><div><div class="n">${t.merchant || t.name}${t.pending ? '<span class="tpill">PENDING</span>' : ""}</div>
      <div class="c">${t.date} · ${t.envelope}</div></div>
      <div class="amt ${inflow ? "in" : ""}">${inflow ? "+" : ""}${money2(Math.abs(t.amount))}</div></div>`;
  }).join("");
}

$("#syncBtn").addEventListener("click", async () => {
  $("#liveTxt").textContent = "SYNCING";
  try { await api("/api/sync", { method: "POST" }); await load(); } catch (e) { alert(e.message); $("#liveTxt").textContent = "ERROR"; }
});

async function connect() {
  let lt;
  try { lt = (await api("/api/link-token")).link_token; } catch (e) { alert(e.message); return; }
  try { localStorage.setItem("cockpit_link_token", lt); } catch (e) {}
  openLink(lt);
}

function openLink(token, receivedRedirectUri) {
  const cfg = {
    token,
    onSuccess: async (pt) => {
      try { await api("/api/exchange", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ public_token: pt }) }); await load(); }
      catch (e) { alert(e.message); }
    },
  };
  if (receivedRedirectUri) cfg.receivedRedirectUri = receivedRedirectUri;
  Plaid.create(cfg).open();
}

// If a bank (e.g. Chase) sent us back via OAuth, resume the Link flow.
function resumeOAuthIfNeeded() {
  if (window.location.search.includes("oauth_state_id")) {
    let lt = null;
    try { lt = localStorage.getItem("cockpit_link_token"); } catch (e) {}
    if (lt) openLink(lt, window.location.href);
  }
}
$("#connectBtn").addEventListener("click", connect);

$("#addEnvelope").addEventListener("click", () => {
  $("#budgetEditor").innerHTML = DATA.envelopes.map((e) =>
    `<div class="belem"><label>${e.name}</label><input type="number" inputmode="decimal" data-name="${e.name}" value="${e.allocated}"></div>`).join("");
  $("#sheet").classList.remove("hidden");
});
$("#closeSheet").addEventListener("click", async () => {
  for (const i of document.querySelectorAll("#budgetEditor input"))
    await api("/api/envelopes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: i.dataset.name, allocation: parseFloat(i.value || "0") }) });
  $("#sheet").classList.add("hidden");
  await load();
});

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
resumeOAuthIfNeeded();
load().catch((e) => { $("#netWorth").textContent = "ERROR"; $("#footStatus").textContent = e.message; });
