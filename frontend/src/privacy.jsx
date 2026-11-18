import React from 'react';
import {ArrowUpRight} from 'lucide-react';

// Fill these in before launch (they are shown on the page as-is).
const ORG = {
  name: 'School of Law, SASTRA Deemed to be University',
  address: 'Thanjavur, Tamil Nadu, India',
  email: '127118023@sastra.ac.in',                 // TODO: privacy / data-request mailbox
  officer: 'Raghav Karthik, Student Convenor, School of Law',  // TODO: name and designation
  updated: '18 November 2026',
  retention: '12 months after the competition concludes',   // TODO: confirm
};
const L = ({items}) => <ul>{items.map((x, i) => <li key={i}>{x}</li>)}</ul>;

const SECTIONS = [
  ['who', '1. Who we are', <>
    <p>This policy applies to the <b>SASTRA International Commercial Arbitration Moot Competition 2027</b> (the "Competition"), its public website, the registration form, the Participant Portal and the Admin Portal (together, the "Site"). The Competition is organised by the <b>{ORG.name}</b>, {ORG.address} ("we", "us", "the organisers").</p>
    <p>For the purposes of the Digital Personal Data Protection Act, 2023 (India) ("DPDP Act") we are the <b>Data Fiduciary</b>; for the EU/UK General Data Protection Regulation ("GDPR") we are the <b>Controller</b>. Contact: <a href={`mailto:${ORG.email}`}>{ORG.email}</a>.</p></>],
  ['scope', '2. Who this policy covers', <>
    <p>It covers (a) <b>coaches / faculty conveners</b> who register a team, (b) <b>student participants</b> (speakers and researchers) named in a registration, and (c) <b>visitors</b> to the Site. If you give us another person's details (for example a coach registering students), you confirm that you are entitled to do so and have shown them this policy.</p></>],
  ['collect', '3. What personal data we collect', <>
    <p><b>3.1 Registration (provided by the coach):</b></p>
    <L items={['University / institution name and country', 'Coach: full name, email address, telephone number', 'Each participant (up to three): full name, email address, year of study, role (Speaker 1, Speaker 2 or Researcher)', 'A system-generated Request ID that identifies your registration']}/>
    <p><b>3.2 Participant Portal (selected teams):</b></p>
    <L items={['Portal login: your User ID (the Request ID) and a password. Passwords are stored only in hashed form by our authentication provider; we cannot read them.', 'Clarification questions your team submits and how many times they were edited', 'Memorial files you upload (two PDF and two Word documents) and their file names, sizes and upload times', 'Messages sent to your team by the organisers', 'Your team code and round status (pending, selected, rejected) and any note recorded with the decision']}/>
    <p><b>3.3 Administrators:</b> the email address, display name and role of organiser staff who sign in to the Admin Portal.</p>
    <p><b>3.4 Records we generate:</b> an audit log of actions (for example registration submitted, decision recorded, password issued or reset, files uploaded or downloaded) with the actor, action and timestamp; and records of emails sent about your registration.</p>
    <p><b>3.5 Technical data:</b> your IP address, browser type, device information and request time are processed by our hosting and security providers when you use the Site, and are used for security, abuse prevention (rate limiting) and troubleshooting. Our CAPTCHA provider analyses browser signals to tell humans from bots.</p>
    <p><b>3.6 What we do not collect:</b> we do not ask for government ID numbers, financial or payment details, health data, biometric data or other sensitive categories. Please do not include any in free-text fields, questions or uploaded files. We do not knowingly collect data for advertising or profiling.</p></>],
  ['why', '4. Why we use your data and our legal basis', <>
    <table className="policy-table"><thead><tr><th>Purpose</th><th>Legal basis</th></tr></thead><tbody>
      {[['Receive, review and decide registrations; select teams', 'Your consent and request to take part (DPDP Act s.6 and s.7; GDPR Art. 6(1)(a),(b))'],
        ['Create and secure Participant Portal accounts; run the clarification and memorial stages', 'Performance of the participation arrangement (GDPR Art. 6(1)(b)); consent (DPDP Act s.6)'],
        ['Send emails about your registration, decisions, credentials, schedule and organiser messages', 'Performance of the arrangement; legitimate interest in running the event (GDPR Art. 6(1)(b),(f))'],
        ['Security: authentication, CAPTCHA, rate limiting, audit logging, fraud and abuse prevention', 'Legitimate interest (GDPR Art. 6(1)(f)); reasonable security safeguards (DPDP Act s.8(5); IT Act s.43A)'],
        ['Fair judging, record-keeping, resolving disputes and appeals', 'Legitimate interest; legal claims (GDPR Art. 6(1)(f), 9(2)(f) where relevant)'],
        ['Compliance with law and lawful requests from authorities', 'Legal obligation (GDPR Art. 6(1)(c); DPDP Act s.7)'],
        ['Announcing results (for example names of winning teams and universities)', 'Your consent; you may ask us not to publish individual names']].map(([a, b]) => <tr key={a}><td>{a}</td><td>{b}</td></tr>)}
    </tbody></table>
    <p>We do not sell personal data, and we do not use it for automated decision-making that produces legal or similarly significant effects. Team selection is made by people.</p></>],
  ['consent', '5. Consent and withdrawing it', <>
    <p>By submitting the registration form you consent to the processing described here. You may withdraw consent at any time by writing to <a href={`mailto:${ORG.email}`}>{ORG.email}</a>. Withdrawal does not affect processing already carried out, and because we need your details to run the Competition, withdrawing may mean your team can no longer take part.</p></>],
  ['children', '6. Participants under 18 / minors', <>
    <p>Participants are expected to be university students. If a participant is under 18 (or under the age of majority where they live), the coach or institution must obtain verifiable consent from a parent or legal guardian before registering them. We do not track, profile or send targeted advertising to minors. Contact us if you believe a minor's data was submitted without proper consent and we will delete it.</p></>],
  ['share', '7. Who we share data with', <>
    <p>Within the organising committee, data is available only to authorised administrators. Judges and examiners may see team codes and submitted memorials; we avoid showing institution names where the rules call for anonymous judging. We use the following service providers (data processors) who process data on our behalf under their own security and data-protection terms:</p>
    <table className="policy-table"><thead><tr><th>Provider</th><th>What for</th><th>Data involved</th></tr></thead><tbody>
      {[['Supabase', 'Database, authentication and private file storage', 'All registration, portal and audit data; uploaded memorials'],
        ['Vercel', 'Website hosting and delivery', 'IP address, request metadata, request content in transit'],
        ['Cloudflare (Turnstile)', 'CAPTCHA / bot protection on registration and sign-in', 'IP address, browser signals'],
        ['Google (Gmail / SMTP)', 'Sending notification emails', 'Recipient emails, email content'],
        ['Google Fonts', 'Font delivery', 'IP address (the browser fetches fonts directly)'],
        ['SASTRA websites and other image hosts', 'Images shown on the Site', 'IP address (the browser fetches images directly)']].map(r => <tr key={r[0]}>{r.map((c, i) => <td key={i}>{c}</td>)}</tr>)}
    </tbody></table>
    <p>We may also disclose data if required by law, court order or a lawful request from a competent authority, or to protect the rights, safety and security of the Competition, its participants or the public. We do not otherwise disclose personal data to third parties.</p></>],
  ['transfer', '8. International transfers', <>
    <p>The Competition is international, and our providers may process data in countries other than your own, including India, the United States and the European Union. Where GDPR applies, we rely on appropriate safeguards such as the providers' Standard Contractual Clauses. Under the DPDP Act, transfers outside India are permitted except to countries the Government of India has restricted. Ask us for the current hosting region of your data.</p></>],
  ['retention', '9. How long we keep data', <>
    <L items={[`Registration and portal data, including memorials and questions: ${ORG.retention}, then deleted or anonymised.`, 'Audit logs and records needed to resolve a dispute or appeal: kept for as long as the dispute remains open, then deleted.', 'Rejected or incomplete registrations: deleted within the same period.', 'Backups and logs roll off on the providers’ normal schedules.', 'Aggregate, non-identifying statistics (for example number of teams per country) may be kept indefinitely.']}/>
    <p>We may keep data longer where the law requires it or where it is needed to establish, exercise or defend legal claims.</p></>],
  ['rights', '10. Your rights', <>
    <p><b>Under the DPDP Act (India)</b> you may: obtain a summary of the personal data we process and with whom it is shared; correct, complete or update it; have it erased; withdraw consent; seek grievance redressal; and nominate another person to exercise your rights if you die or become incapacitated.</p>
    <p><b>Under the GDPR (EU/UK)</b> you may: access your data; rectify it; have it erased; restrict or object to processing (including processing based on legitimate interest); receive it in a portable format; and withdraw consent. You also have the right to complain to your local supervisory authority.</p>
    <p>To exercise any right, email <a href={`mailto:${ORG.email}`}>{ORG.email}</a> from the address used in the registration, quoting your Request ID. We may need to verify your identity, and we will respond within <b>30 days</b> (GDPR) or the period required by law. Requests are free unless they are manifestly excessive. Participants may also ask their coach to write on the team's behalf.</p></>],
  ['security', '11. How we protect your data', <>
    <L items={['Encrypted connections (HTTPS/TLS) with HTTP Strict Transport Security and a restrictive Content Security Policy', 'Passwords hashed by the authentication provider; temporary passwords must be changed at first login', 'Row-level security on the database; role-based access so that only active administrators can see registrations', 'Private storage for uploaded memorials; organisers download them through short-lived signed links', 'CAPTCHA and rate limiting on registration and sign-in to deter automated abuse', 'An audit log of administrative actions', 'Restricted organiser access and use of two-factor authentication on provider accounts']}/>
    <p>No system is completely secure. Please keep your password confidential, do not share it outside your team, and tell us at once if you suspect misuse.</p></>],
  ['breach', '12. Data breaches', <>
    <p>If a personal data breach occurs we will contain it, assess the risk, and notify affected individuals and the relevant authorities as the law requires: the Data Protection Board of India under the DPDP Act, CERT-In under the IT Act directions (within six hours for reportable cyber incidents), and the competent GDPR supervisory authority within 72 hours where applicable.</p></>],
  ['cookies', '13. Cookies and similar technologies', <>
    <p>The Site does not use advertising or analytics cookies and does not build advertising profiles. Your sign-in session is kept in the page's memory and ends when you close or reload the tab. Our CAPTCHA provider (Cloudflare Turnstile) may use cookies or local storage strictly to distinguish humans from bots. Our hosting provider may keep technical server logs.</p></>],
  ['links', '14. Third-party links', <>
    <p>The Site links to the SASTRA University website and may link to other sites. We are not responsible for their content or privacy practices.</p></>],
  ['grievance', '15. Contact, grievance officer and complaints', <>
    <p><b>{ORG.officer}</b><br/>{ORG.name}, {ORG.address}<br/>Email: <a href={`mailto:${ORG.email}`}>{ORG.email}</a></p>
    <p>Please contact us first and we will try to resolve your concern promptly. If you are not satisfied you may complain to the Data Protection Board of India (once constituted), or, if you are in the EU/UK, to your local data protection authority.</p></>],
  ['changes', '16. Changes to this policy', <>
    <p>We may update this policy as the Competition, the Site or the law changes. The "last updated" date above shows the current version. We will notify registered teams by email of material changes.</p></>],
];

export default function Privacy() {
  const go = id => document.getElementById(id)?.scrollIntoView({behavior: 'smooth', block: 'start'});
  return <div className="app-shell"><header className="topbar"><a className="brand" href="./"><img className="logo" src="https://www.sastra.edu/templates/santosh/images/sastratransp.png" alt="SASTRA Deemed to be University"/><span className="brand-text"><strong>SCHOOL OF LAW</strong><small>THANJAVUR · INDIA</small></span></a>
    <nav className="main-nav"><span className="admin-badge">Privacy policy</span><a className="navlink" href="./">← Public site</a></nav></header>
    <main><article className="policy form-card">
      <div className="section-kicker">LEGAL</div><h1>Privacy Policy</h1>
      <p className="muted">SASTRA International Commercial Arbitration Moot Competition 2027 · Last updated {ORG.updated}</p>
      <p>We take your privacy seriously. This policy explains what personal data the Competition collects, why, how it is protected, who it is shared with, how long it is kept, and the rights you have under the Digital Personal Data Protection Act 2023, the Information Technology Act 2000 (and its SPDI Rules 2011), the GDPR and similar laws.</p>
      <nav className="policy-toc" aria-label="Contents">{SECTIONS.map(([id, t]) => <button key={id} onClick={() => go(id)}>{t}</button>)}</nav>
      {SECTIONS.map(([id, t, body]) => <section key={id} id={id}><h2>{t}</h2>{body}</section>)}
      <p><a className="primary" href="./" style={{display: 'inline-flex', textDecoration: 'none'}}>Back to the Competition site <ArrowUpRight size={17}/></a></p>
    </article></main></div>;
}
