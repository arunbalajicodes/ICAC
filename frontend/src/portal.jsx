import React, {useEffect, useState} from 'react';
import {ArrowUpRight, LogOut, Plus, Trash2, Upload, FileText, CheckCircle2} from 'lucide-react';

const when = s => s ? new Date(s).toLocaleString('en-IN', {day:'numeric', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit'}) : '—';
const MAX_FILE = 2 * 1024 * 1024;
const SLOTS = [[1, 'Memorial PDF 1', 'pdf'], [2, 'Memorial PDF 2', 'pdf'], [3, 'Document 1 (Word)', 'doc'], [4, 'Document 2 (Word)', 'doc']];
const NAV = [['details', 'Team details'], ['questions', 'Clarification questions'], ['memorial', 'Memorial submission'], ['messages', 'Messages']];

function Field({label, type = 'text', value, onChange, autoComplete}) {
  return <label className="field"><span>{label}<i> *</i></span><input type={type} required value={value} autoComplete={autoComplete} onChange={e => onChange(e.target.value)}/></label>;
}

// Participant portal (/#portal): teams sign in with their Request ID (User ID) and password.
export function Portal({API, sbToken}) {
  const [domain, setDomain] = useState(''), [cred, setCred] = useState({ref:'', password:''}), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [token, setToken] = useState(''), [refresh, setRefresh] = useState(''), [me, setMe] = useState(null), [sec, setSec] = useState('details');
  useEffect(() => { fetch(API + '/api/config').then(r => r.json()).then(d => setDomain(d.team_email_domain)).catch(() => setError('Could not reach the server. Please try again.')); }, []);
  const call = async (path, opt = {}, tok = token) => {
    const r = await fetch(API + path, {...opt, headers:{Authorization:`Bearer ${tok}`, ...(typeof opt.body === 'string' ? {'Content-Type':'application/json'} : {}), ...(opt.headers || {})}});
    const d = await r.json().catch(() => ({detail:'Unexpected server response'}));
    if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : 'Request failed');
    return d;
  };
  const loadMe = (tok = token) => call('/api/team/me', {}, tok).then(setMe);
  const email = ref => `${ref.trim().toLowerCase()}@${domain}`;
  async function signIn(ref, password) {
    const s = await sbToken('password', {email:email(ref), password});
    await loadMe(s.access_token);
    setToken(s.access_token); setRefresh(s.refresh_token);
  }
  async function onLogin(e) {
    e.preventDefault(); setBusy(true); setError('');
    try { await signIn(cred.ref, cred.password); }
    catch (err) { setError(/invalid login/i.test(err.message) ? 'Invalid User ID or password.' : err.message); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    if (!refresh) return;
    const t = setTimeout(async () => { try { const s = await sbToken('refresh_token', {refresh_token:refresh}); setToken(s.access_token); setRefresh(s.refresh_token); } catch { out('Your session expired. Please sign in again.'); } }, 50 * 60 * 1000);
    return () => clearTimeout(t);
  }, [refresh]);
  const out = msg => { setToken(''); setRefresh(''); setMe(null); setSec('details'); setError(msg || ''); };
  const reload = () => loadMe().catch(e => setError(e.message));
  const props = {me, call, reload, setError};

  return <div className="app-shell"><header className="topbar"><a className="brand" href="./"><img className="logo" src="https://www.sastra.edu/templates/santosh/images/sastratransp.png" alt="SASTRA Deemed to be University"/><span className="brand-text"><strong>SCHOOL OF LAW</strong><small>THANJAVUR · INDIA</small></span></a>
    <nav className="main-nav"><span className="admin-badge">Participant portal</span><a className="navlink" href="./">← Public site</a></nav><div className="secure"><span className="live-dot"/> Secure sign-in</div></header>
    <main>
      {error && <div className="alert error"><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss">×</button></div>}
      {!me && <section className="admin-login form-card"><div className="section-kicker">PARTICIPANT PORTAL</div><h2>Team sign in</h2>
        <p className="muted">Sign in with the User ID and temporary password emailed to your coach and team when you were selected.</p>
        <form onSubmit={onLogin}>
          <Field label="User ID (Request ID)" value={cred.ref} onChange={v => setCred({...cred, ref:v})} autoComplete="username"/>
          <Field label="Password" type="password" value={cred.password} onChange={v => setCred({...cred, password:v})} autoComplete="current-password"/>
          <button className="primary full" disabled={busy || !domain}>{busy ? 'Signing in…' : 'Sign in'} <ArrowUpRight size={17}/></button>
        </form>
        <p className="fineprint">Forgotten your password? Contact the organising committee to have a new one issued.</p></section>}
      {me && me.must_change_password && <ChangePassword me={me} call={call} onDone={async pw => { setBusy(true); try { await signIn(me.request_id, pw); } catch (e) { out('Password changed. Please sign in again with your new password.'); } finally { setBusy(false); } }} setError={setError} signOut={() => out()}/>}
      {me && !me.must_change_password && <section className="admin-panel">
        <div className="admin-title"><div><div className="section-kicker">PARTICIPANT PORTAL{me.team_code ? ` · TEAM ${me.team_code}` : ''}</div><h2>{me.registration.university}</h2><p className="muted">Signed in as <span className="mono">{me.request_id}</span></p></div>
          <div className="admin-actions"><button className="secondary" onClick={() => out()}><LogOut size={16}/> Sign out</button></div></div>
        <div className="team-layout portal-layout">
          <nav className="team-nav" aria-label="Portal sections">{NAV.map(([k, l]) => <button key={k} className={sec === k ? 'on' : ''} onClick={() => setSec(k)}>{l}</button>)}</nav>
          <div className="team-body">
            {sec === 'details' && <Details me={me}/>}
            {sec === 'questions' && <Questions {...props}/>}
            {sec === 'memorial' && <Memorial {...props}/>}
            {sec === 'messages' && <Messages me={me}/>}
          </div>
        </div>
      </section>}
    </main></div>;
}

function ChangePassword({me, call, onDone, setError, signOut}) {
  const [a, setA] = useState(''), [b, setB] = useState(''), [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault(); setError('');
    if (a.length < 8 || !/[A-Za-z]/.test(a) || !/\d/.test(a)) return setError('Your new password must be at least 8 characters and include a letter and a digit.');
    if (a !== b) return setError('The two passwords do not match.');
    setBusy(true);
    try { await call('/api/team/password', {method:'POST', body:JSON.stringify({new_password:a})}); await onDone(a); }
    catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  return <section className="admin-login form-card"><div className="section-kicker">FIRST SIGN-IN</div><h2>Choose a new password</h2>
    <p className="muted">For your team's security, please replace the temporary password with one of your own before continuing. Use at least 8 characters, including a letter and a digit.</p>
    <form onSubmit={submit}>
      <Field label="New password" type="password" value={a} onChange={setA} autoComplete="new-password"/>
      <Field label="Confirm new password" type="password" value={b} onChange={setB} autoComplete="new-password"/>
      <button className="primary full" disabled={busy}>{busy ? 'Saving…' : 'Save password and continue'} <ArrowUpRight size={17}/></button>
    </form>
    <p className="fineprint"><button type="button" className="text-action" onClick={signOut}>Sign out</button></p></section>;
}

function Details({me}) {
  const r = me.registration;
  return <>
    <h4>Team details</h4>
    <div className="detail-grid">
      <div><small>TEAM CODE</small><b className="team-code">{me.team_code || 'Not assigned yet'}</b></div>
      <div><small>USER ID (REQUEST ID)</small><b className="mono">{me.request_id}</b></div>
      <div><small>UNIVERSITY</small><b>{r.university}</b><span>{r.country}</span></div>
      <div><small>COACH</small><b>{r.coach_name}</b><span>{r.coach_email} · {r.coach_phone}</span></div>
    </div>
    <div className="table-scroll"><table><thead><tr><th>#</th><th>NAME</th><th>EMAIL</th><th>YEAR / COURSE</th><th>ROLE</th></tr></thead><tbody>
      {r.participants.map(p => <tr key={p.position}><td>{p.position}</td><td><b>{p.name}</b></td><td>{p.email}</td><td>{p.year}</td><td>{p.role || '—'}</td></tr>)}
    </tbody></table></div>
  </>;
}

function Questions({me, call, reload, setError}) {
  const saved = me.questions.map(q => q.question);
  const [list, setList] = useState(saved), [draft, setDraft] = useState(''), [busy, setBusy] = useState(false), [msg, setMsg] = useState('');
  useEffect(() => { setList(saved); }, [JSON.stringify(saved)]);   // follow the server after a save
  const left = me.max_edits - me.edits_used, hasSaved = saved.length > 0, locked = hasSaved && left <= 0;
  const final = draft.trim() ? [...list, draft.trim()] : list;
  const dirty = JSON.stringify(final) !== JSON.stringify(saved);
  const notes = <div className="info-note">
    <p><b>Clarifications will be released on the public website.</b> Official responses to the questions raised by teams will be published on the competition website for all participants; they will not be sent to individual teams.</p>
    <p><b>Editing is limited.</b> Once your questions are saved, you may edit them a maximum of <b>{me.max_edits} times</b>.</p>
  </div>;
  if (!me.clarifications_open) return <><h4>Clarification questions</h4><p className="empty-note">Clarification questions will open once the moot proposition is released.</p>{notes}</>;
  const add = () => { const q = draft.trim(); if (q && list.length < 20) { setList([...list, q]); setDraft(''); } };
  async function save() {
    if (hasSaved && !confirm(`Saving these changes will use 1 of your ${me.max_edits} edits (${left} remaining). Continue?`)) return;
    setBusy(true); setError(''); setMsg('');
    try { await call('/api/team/questions', {method:'PUT', body:JSON.stringify({questions:final})}); setMsg('Your questions have been saved.'); setDraft(''); await reload(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <>
    <h4>Clarification questions</h4>
    {notes}
    <p className="muted">{hasSaved ? <>Edits used: <b>{me.edits_used} of {me.max_edits}</b>{locked ? ' — no further edits are allowed.' : ` — ${left} remaining.`}</> : 'Add your questions below, then save. Your first save does not count as an edit.'}</p>
    {list.length > 0 && <ol className="qlist">{list.map((q, i) => <li key={i}>
      {locked ? q : <div className="q-row"><textarea className="admin-textarea" rows="2" maxLength={1000} value={q} onChange={e => setList(list.map((x, j) => j === i ? e.target.value : x))}/><button type="button" className="icon-button" aria-label="Remove question" onClick={() => setList(list.filter((_, j) => j !== i))}><Trash2 size={16}/></button></div>}
    </li>)}</ol>}
    {!locked && <div className="q-add"><textarea className="admin-textarea" rows="2" maxLength={1000} value={draft} onChange={e => setDraft(e.target.value)} placeholder="Type a clarification question…" disabled={list.length >= 20}/>
      <button type="button" className="secondary q-plus" onClick={add} disabled={!draft.trim() || list.length >= 20} aria-label="Add question"><Plus size={18}/></button></div>}
    {!locked && <div className="decision-row"><button className="approve" disabled={busy || !dirty || final.length === 0} onClick={save}>{hasSaved ? 'Save changes' : 'Save questions'}</button>{msg && <span className="muted"><CheckCircle2 size={14}/> {msg}</span>}</div>}
  </>;
}

function Memorial({me, call, reload, setError}) {
  const [busy, setBusy] = useState(0);
  const byslot = Object.fromEntries(me.files.map(f => [f.slot, f]));
  async function upload(slot, f) {
    if (!f) return;
    if (f.size > MAX_FILE) return setError('Each file must be 2 MB or smaller.');
    setBusy(slot); setError('');
    try { await call(`/api/team/memorial/${slot}`, {method:'PUT', headers:{'X-File-Name':encodeURIComponent(f.name), 'Content-Type':'application/octet-stream'}, body:f}); await reload(); }
    catch (e) { setError(e.message); } finally { setBusy(0); }
  }
  async function remove(slot) { if (!confirm('Remove this file?')) return; setBusy(slot); setError(''); try { await call(`/api/team/memorial/${slot}`, {method:'DELETE'}); await reload(); } catch (e) { setError(e.message); } finally { setBusy(0); } }
  return <>
    <h4>Memorial submission</h4>
    <p className="muted">Upload up to four files: two PDFs and two Word documents (.doc or .docx). Each file must be 2 MB or smaller. You can replace or remove a file at any time.</p>
    {!me.memorial_open ? <p className="empty-note">Memorial submission will open once the memorial guidelines are released.</p> :
      <div className="slots">{SLOTS.map(([slot, label, kind]) => { const f = byslot[slot]; return <div className="slot" key={slot}>
        <div><b>{label}</b>{f ? <small><FileText size={13}/> {f.file_name} · {(f.size_bytes / 1024).toFixed(0)} KB · {when(f.uploaded_at)}</small> : <small>No file uploaded</small>}</div>
        <div className="se-actions">
          <label className={`secondary${busy === slot ? ' busy' : ''}`}><Upload size={14}/> {busy === slot ? 'Uploading…' : f ? 'Replace' : 'Choose file'}
            <input type="file" hidden disabled={!!busy} accept={kind === 'pdf' ? 'application/pdf,.pdf' : '.doc,.docx,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document'} onChange={e => { const file = e.target.files[0]; e.target.value = ''; upload(slot, file); }}/></label>
          {f && <button type="button" className="secondary" disabled={!!busy} onClick={() => remove(slot)}>Remove</button>}
        </div></div>; })}</div>}
  </>;
}

function Messages({me}) {
  return <>
    <h4>Messages from the organisers</h4>
    {me.messages.length === 0 ? <p className="empty-note">No messages yet. Messages from the organising committee will also be sent to your coach's email.</p> :
      <div className="timeline">{me.messages.map(m => <div className="timeline-item" key={m.id}><span className="timeline-dot"/><div><small>{when(m.sent_at)} · Organising Committee</small><p className="msg-text">{m.body}</p></div></div>)}</div>}
  </>;
}
