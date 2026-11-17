import React, {useEffect, useState} from 'react';
import {Download, LogOut, Search, Users, Clock3, CheckCircle2, XCircle, ChevronRight, FileClock, KeyRound, Send, ArrowLeft} from 'lucide-react';

const when = s => s ? new Date(s).toLocaleString('en-IN', {day:'numeric', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit'}) : '—';
const day = s => s ? new Date(s).toLocaleDateString('en-IN', {day:'numeric', month:'short', year:'numeric'}) : '—';
const ROUND = {PENDING:'Pending', SELECTED:'Selected', REJECTED:'Rejected'};
const mailNote = m => m === 'sent' ? 'The email was sent to the coach and participants.' : m === 'skipped' ? 'The email was NOT sent (email is not configured on the server).' : 'The email FAILED to send.';

function Status({status}) {
  const cls = status === 'APPROVED' ? 'approved' : status === 'REJECTED' ? 'rejected' : 'pending';
  const Icon = status === 'APPROVED' ? CheckCircle2 : status === 'REJECTED' ? XCircle : Clock3;
  const label = status === 'REVIEW_PENDING' ? 'Review pending' : status === 'APPROVED' ? 'Selected' : 'Rejected';
  return <span className={`status-pill ${cls}`}><Icon size={13}/>{label}</span>;
}
function RoundPill({value}) {
  const cls = value === 'SELECTED' ? 'approved' : value === 'REJECTED' ? 'rejected' : 'pending';
  return <span className={`status-pill ${cls}`}>{ROUND[value] || value}</span>;
}
const Stat = ({label, value, icon}) => <div className="stat-card"><span className="stat-icon">{icon}</span><small>{label}</small><strong>{value}</strong></div>;

// Admin portal: Registrations (primary), Team management, Site content (secondary).
export function Admin({token, admin, API, setError, onSignOut, siteTab}) {
  const [tab, setTab] = useState('registrations'), [open, setOpen] = useState(null);
  const call = async (path, opt = {}) => {
    const r = await fetch(API + path, {...opt, headers:{Authorization:`Bearer ${token}`, ...(typeof opt.body === 'string' ? {'Content-Type':'application/json'} : {}), ...(opt.headers || {})}});
    const d = await r.json().catch(() => ({detail:'Unexpected server response'}));
    if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : 'Request failed');
    return d;
  };
  const download = async (path, name) => {
    try {
      const r = await fetch(API + path, {headers:{Authorization:`Bearer ${token}`}});
      if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || 'Download failed'); }
      const url = URL.createObjectURL(await r.blob()), a = document.createElement('a');
      a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
    } catch (e) { setError(e.message); }
  };
  const goTeam = id => { setOpen(id); setTab('teams'); };
  const tabs = [['registrations', 'Registrations'], ['teams', 'Team management'], ['site', 'Site content']];
  return <section className="admin-panel">
    <div className="admin-title"><div><div className="section-kicker">ADMINISTRATION</div><h2>Admin portal</h2><p className="muted">Welcome, {admin?.display_name || 'Admin'}.</p></div>
      <div className="admin-actions"><button className="secondary" onClick={onSignOut}><LogOut size={16}/> Sign out</button></div></div>
    <div className="admin-tabs" role="tablist">{tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => { setTab(k); if (k === 'teams') setOpen(null); }}>{l}</button>)}</div>
    {tab === 'registrations' && <Registrations call={call} download={download} setError={setError} goTeam={goTeam}/>}
    {tab === 'teams' && <Teams call={call} setError={setError} open={open} setOpen={setOpen}/>}
    {tab === 'site' && siteTab}
  </section>;
}

function Registrations({call, download, setError, goTeam}) {
  const [items, setItems] = useState([]), [filter, setFilter] = useState('ALL'), [query, setQuery] = useState(''), [sel, setSel] = useState(null), [audit, setAudit] = useState(null),
    [note, setNote] = useState(''), [code, setCode] = useState(''), [busy, setBusy] = useState(false), [notice, setNotice] = useState('');
  const load = async () => { try { setItems((await call('/api/admin/registrations')).items); } catch (e) { setError(e.message); } };
  useEffect(() => { load(); }, []);
  useEffect(() => { if (sel) document.getElementById('request-details')?.scrollIntoView({behavior:'smooth', block:'start'}); }, [sel]);
  const filtered = items.filter(x => (filter === 'ALL' || x.status === filter) && [x.university, x.coach_name, x.request_id].join(' ').toLowerCase().includes(query.toLowerCase()));
  const count = s => items.filter(x => x.status === s).length;
  async function decide(decision) {
    setBusy(true); setError(''); setNotice('');
    try {
      const r = await call(`/api/admin/registrations/${sel.request_id}/decision`, {method:'POST', body:JSON.stringify({decision, note, team_code:code})});
      setNotice(decision === 'APPROVED' ? `${sel.university} has been selected. Its login (User ID ${sel.request_id}) was created. ${mailNote(r.email)}${r.email !== 'sent' ? ' Open the team page and use "Reset password" to send the login details again.' : ''}` : `${sel.university} was rejected. ${mailNote(r.email)}`);
      setSel(null); setAudit(null); setNote(''); setCode(''); await load();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function show(row) { setSel(row); setAudit(null); setNote(''); setCode(''); try { setAudit(await call(`/api/admin/audit/${row.request_id}`)); } catch (e) { setError(e.message); } }
  const parts = sel ? [1, 2, 3].filter(i => sel[`participant${i}_name`]) : [];
  return <>
    <div className="dl-bar">
      <button className="secondary" onClick={() => download('/api/admin/export/clarifications.xlsx', 'sastra-clarification-questions.xlsx')}><Download size={16}/> All clarification questions (Excel)</button>
      <button className="secondary" onClick={() => download('/api/admin/export/participants.xlsx', 'sastra-participants.xlsx')}><Download size={16}/> All participants (Excel)</button>
      <button className="secondary" onClick={() => download('/api/admin/export.xlsx', 'sastra-registrations.xlsx')}><Download size={16}/> Registrations (Excel)</button>
    </div>
    {notice && <div className="notice"><CheckCircle2 size={18}/><span>{notice}</span><button onClick={() => setNotice('')} aria-label="Dismiss">×</button></div>}
    <div className="stats-grid"><Stat label="Registrations" value={items.length} icon={<Users/>}/><Stat label="Pending review" value={count('REVIEW_PENDING')} icon={<Clock3/>}/><Stat label="Selected" value={count('APPROVED')} icon={<CheckCircle2/>}/><Stat label="Rejected" value={count('REJECTED')} icon={<XCircle/>}/></div>
    <div className="table-card">
      <div className="table-toolbar">
        <div className="searchbox"><Search size={17}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search universities, contacts, request IDs"/></div>
        <select value={filter} onChange={e => setFilter(e.target.value)}><option value="ALL">All statuses</option><option value="REVIEW_PENDING">Pending review</option><option value="APPROVED">Selected</option><option value="REJECTED">Rejected</option></select>
      </div>
      <div className="table-scroll"><table><thead><tr><th>UNIVERSITY</th><th>REQUEST ID</th><th>SUBMITTED</th><th>STATUS</th><th>ACTIONS</th></tr></thead><tbody>
        {filtered.map(r => <tr key={r.request_id}><td><b>{r.university}</b><small>{r.country || ''}</small></td><td className="mono">{r.request_id}</td><td>{day(r.created_at)}</td><td><Status status={r.status}/></td>
          <td><button className="text-action" onClick={() => show(r)}>{r.status === 'REVIEW_PENDING' ? 'Review' : 'Details & audit'} <ChevronRight size={14}/></button></td></tr>)}
        {filtered.length === 0 && <tr><td colSpan="5" className="empty">No registrations found for this filter.</td></tr>}
      </tbody></table></div>
    </div>
    {sel && <div className="detail-card" id="request-details">
      <div className="detail-head"><div><div className="section-kicker">REGISTRATION</div><h3>{sel.university} <span className="mono">{sel.request_id}</span></h3></div><button className="icon-button" onClick={() => { setSel(null); setAudit(null); }}>×</button></div>
      <div className="detail-grid">
        <div><small>UNIVERSITY</small><b>{sel.university}, {sel.country}</b></div>
        <div><small>COACH</small><b>{sel.coach_name}</b><span>{sel.coach_email} · {sel.coach_phone}</span></div>
        <div><small>PARTICIPANTS</small>{parts.map(i => <span key={i}>{sel[`participant${i}_name`]} · {sel[`participant${i}_email`]} · {sel[`participant${i}_year`]} · {sel[`participant${i}_role`] || '—'}</span>)}</div>
        <div><small>DECISION NOTE</small><span>{sel.decision_note || 'No note provided'}</span></div>
      </div>
      {sel.status === 'REVIEW_PENDING' && <>
        <p className="muted">Selecting a team creates its Participant Portal login (User ID = the Request ID, with a generated 10-character password) and emails the details to the coach and all participants.</p>
        <div className="decision-row decision-stack">
          <input value={note} onChange={e => setNote(e.target.value)} placeholder="Optional note (included in the email)"/>
          <input value={code} onChange={e => setCode(e.target.value)} placeholder="Team code (optional), e.g. T-07" maxLength={40}/>
          <button className="approve" disabled={busy} onClick={() => decide('APPROVED')}><CheckCircle2 size={15}/> Select team</button>
          <button className="reject" disabled={busy} onClick={() => decide('REJECTED')}><XCircle size={15}/> Reject</button>
        </div></>}
      {sel.status === 'APPROVED' && <div className="decision-row"><button className="secondary" onClick={() => goTeam(sel.request_id)}>Open team page <ChevronRight size={14}/></button></div>}
      <div className="audit-title"><FileClock size={16}/> Audit trail</div>
      {!audit ? <p className="muted">Loading audit history…</p> : audit.events.length === 0 ? <p className="muted">No audit events recorded yet.</p> :
        <div className="timeline">{audit.events.map((ev, i) => <div className="timeline-item" key={i}><span className="timeline-dot"/><div><b>{ev.action.replaceAll('_', ' ')}</b><small>{when(ev.timestamp)} · {ev.actor}</small><p>{ev.details || `${ev.from_status || '—'} → ${ev.to_status || '—'}`}</p></div></div>)}</div>}
    </div>}
  </>;
}

function Teams({call, setError, open, setOpen}) {
  const [items, setItems] = useState(null), [q, setQ] = useState('');
  useEffect(() => { if (!open) call('/api/admin/teams').then(d => setItems(d.items)).catch(e => setError(e.message)); }, [open]);
  if (open) return <TeamPage id={open} back={() => setOpen(null)} call={call} setError={setError}/>;
  const rows = (items || []).filter(t => [t.university, t.team_code, t.request_id, t.coach_name].join(' ').toLowerCase().includes(q.toLowerCase()));
  return <div className="table-card">
    <div className="table-toolbar"><div className="searchbox"><Search size={17}/><input value={q} onChange={e => setQ(e.target.value)} placeholder="Search selected teams by university, team code or request ID"/></div></div>
    <div className="table-scroll"><table><thead><tr><th>TEAM CODE</th><th>UNIVERSITY</th><th>REQUEST ID</th><th>QUESTIONS</th><th>MEMORIAL FILES</th><th>ROUND STATUS</th><th></th></tr></thead><tbody>
      {rows.map(t => <tr key={t.request_id}><td><b>{t.team_code || '—'}</b></td><td><b>{t.university}</b><small>{t.country}</small></td><td className="mono">{t.request_id}</td><td>{t.questions}</td><td>{t.files} / 4</td><td><RoundPill value={t.round_status}/></td>
        <td><button className="text-action" onClick={() => setOpen(t.request_id)}>Manage <ChevronRight size={14}/></button></td></tr>)}
      {items && rows.length === 0 && <tr><td colSpan="7" className="empty">{items.length ? 'No teams match your search.' : 'No teams have been selected yet. Select a registration under the Registrations tab.'}</td></tr>}
      {!items && <tr><td colSpan="7" className="empty">Loading…</td></tr>}
    </tbody></table></div>
  </div>;
}

const NAV = [['details', 'Team details'], ['questions', 'Clarification questions'], ['memorial', 'Memorial submission'], ['status', 'Status'], ['message', 'Send message']];

function TeamPage({id, back, call, setError}) {
  const [t, setT] = useState(null), [sec, setSec] = useState('details');
  const reload = () => call(`/api/admin/teams/${id}`).then(setT).catch(e => setError(e.message));
  useEffect(() => { reload(); }, [id]);
  if (!t) return <p className="muted">Loading team…</p>;
  const props = {t, call, reload, setError};
  return <div className="team-page">
    <button className="text-action back" onClick={back}><ArrowLeft size={15}/> All teams</button>
    <div className="team-head"><div><div className="section-kicker">TEAM {t.team_code ? `· ${t.team_code}` : ''}</div><h3>{t.registration.university}</h3><span className="mono">{t.request_id}</span></div><RoundPill value={t.round_status}/></div>
    <div className="team-layout">
      <nav className="team-nav" aria-label="Team sections">{NAV.map(([k, l]) => <button key={k} className={sec === k ? 'on' : ''} onClick={() => setSec(k)}>{l}</button>)}</nav>
      <div className="team-body">
        {sec === 'details' && <TeamDetails {...props}/>}
        {sec === 'questions' && <TeamQuestions {...props}/>}
        {sec === 'memorial' && <TeamMemorial {...props}/>}
        {sec === 'status' && <TeamStatus {...props}/>}
        {sec === 'message' && <TeamMessage {...props}/>}
      </div>
    </div>
  </div>;
}

function TeamDetails({t, call, reload, setError}) {
  const [code, setCode] = useState(t.team_code || ''), [msg, setMsg] = useState(''), [busy, setBusy] = useState(false);
  const r = t.registration;
  async function run(fn, ok) { setBusy(true); setError(''); setMsg(''); try { setMsg(await fn() || ok); await reload(); } catch (e) { setError(e.message); } finally { setBusy(false); } }
  const saveCode = () => run(async () => { await call(`/api/admin/teams/${t.request_id}`, {method:'PATCH', body:JSON.stringify({team_code:code})}); }, 'Team code saved.');
  const reset = () => confirm('Generate a new temporary password and email it to the team? Their current password will stop working.') && run(async () => { const d = await call(`/api/admin/teams/${t.request_id}/reset-password`, {method:'POST'}); return `New password generated. ${mailNote(d.email)}`; });
  return <>
    <h4>Team details</h4>
    <div className="detail-grid">
      <div><small>UNIVERSITY</small><b>{r.university}</b><span>{r.country}</span></div>
      <div><small>USER ID (REQUEST ID)</small><b className="mono">{t.request_id}</b><span>{t.must_change_password ? 'Has not changed the temporary password yet' : 'Password changed by the team'}</span></div>
      <div><small>COACH</small><b>{r.coach_name}</b><span>{r.coach_email} · {r.coach_phone}</span></div>
      <div><small>TEAM CODE</small><div className="inline-edit"><input value={code} onChange={e => setCode(e.target.value)} placeholder="e.g. T-07" maxLength={40}/><button className="secondary" disabled={busy || code.trim() === (t.team_code || '')} onClick={saveCode}>Save</button></div></div>
    </div>
    <div className="table-scroll"><table><thead><tr><th>#</th><th>NAME</th><th>EMAIL</th><th>YEAR / COURSE</th><th>ROLE</th></tr></thead><tbody>
      {r.participants.map(p => <tr key={p.position}><td>{p.position}</td><td><b>{p.name}</b></td><td>{p.email}</td><td>{p.year}</td><td>{p.role || '—'}</td></tr>)}
    </tbody></table></div>
    <div className="decision-row"><button className="secondary" disabled={busy} onClick={reset}><KeyRound size={15}/> Reset password</button>{msg && <span className="muted">{msg}</span>}</div>
  </>;
}

function TeamQuestions({t}) {
  const qs = t.clarification_questions;
  return <>
    <h4>Clarification questions</h4>
    <p className="muted">Edits used: <b>{t.clarification_edits_used} of 4</b>. Teams can submit questions once the moot proposition is released.</p>
    {qs.length === 0 ? <p className="empty-note">No questions submitted yet.</p> :
      <ol className="qlist">{qs.map(q => <li key={q.id}>{q.question}<small>Last edited {when(q.updated_at)}</small></li>)}</ol>}
  </>;
}

function TeamMemorial({t}) {
  const fs = t.memorial_files;
  return <>
    <h4>Memorial submission</h4>
    <p className="muted">Up to 4 files per team (2 PDF and 2 documents), 2 MB each. <b>{fs.length} of 4</b> uploaded.</p>
    {fs.length === 0 ? <p className="empty-note">No files submitted yet.</p> :
      <div className="table-scroll"><table><thead><tr><th>SLOT</th><th>FILE</th><th>TYPE</th><th>SIZE</th><th>UPLOADED</th></tr></thead><tbody>
        {fs.map(f => <tr key={f.id}><td>{f.slot}</td><td><b>{f.file_name}</b></td><td>{f.kind === 'pdf' ? 'PDF' : 'Document'}</td><td>{(f.size_bytes / 1024).toFixed(0)} KB</td><td>{when(f.uploaded_at)}</td></tr>)}
      </tbody></table></div>}
  </>;
}

function TeamStatus({t, call, reload, setError}) {
  const [v, setV] = useState(t.round_status), [msg, setMsg] = useState(''), [busy, setBusy] = useState(false);
  async function save() { setBusy(true); setError(''); setMsg(''); try { await call(`/api/admin/teams/${t.request_id}`, {method:'PATCH', body:JSON.stringify({round_status:v})}); setMsg('Status saved.'); await reload(); } catch (e) { setError(e.message); } finally { setBusy(false); } }
  return <>
    <h4>Status</h4>
    <p className="muted">Release the team's status after reviewing its submissions. Use "Send message" to tell the team.</p>
    <div className="decision-row">
      <select value={v} onChange={e => setV(e.target.value)}>{Object.entries(ROUND).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
      <button className="approve" disabled={busy || v === t.round_status} onClick={save}>Save status</button>{msg && <span className="muted">{msg}</span>}
    </div>
  </>;
}

function TeamMessage({t, call, reload, setError}) {
  const [text, setText] = useState(''), [busy, setBusy] = useState(false), [note, setNote] = useState('');
  async function send() {
    setBusy(true); setError(''); setNote('');
    try { const d = await call(`/api/admin/teams/${t.request_id}/messages`, {method:'POST', body:JSON.stringify({body:text})}); setText(''); setNote(`Message sent. ${mailNote(d.email)}`); await reload(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <>
    <h4>Send message</h4>
    <p className="muted">The message is emailed to the coach and all participants of this team (organisers copied).</p>
    <textarea className="admin-textarea" rows="6" maxLength={3000} value={text} onChange={e => setText(e.target.value)} placeholder="Type your message to the team…"/>
    <div className="decision-row"><button className="approve" disabled={busy || !text.trim()} onClick={send}><Send size={15}/> Send message</button>{note && <span className="muted">{note}</span>}</div>
    <div className="audit-title">Sent messages</div>
    {t.messages.length === 0 ? <p className="empty-note">No messages sent yet.</p> :
      <div className="timeline">{t.messages.map(m => <div className="timeline-item" key={m.id}><span className="timeline-dot"/><div><small>{when(m.sent_at)} · {m.sender}</small><p className="msg-text">{m.body}</p></div></div>)}</div>}
  </>;
}
