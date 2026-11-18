import React, {useEffect, useRef} from 'react';
export const TS_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY;
export function Turnstile({onToken}) {
  const box = useRef(null);
  useEffect(() => {
    if (!TS_KEY) return;
    let id; const draw = () => { id = window.turnstile.render(box.current, {sitekey: TS_KEY, callback: onToken, 'expired-callback': () => onToken(''), 'error-callback': () => onToken('')}) };
    if (window.turnstile) draw(); else { const sc = document.createElement('script'); sc.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'; sc.async = true; sc.onload = draw; document.head.appendChild(sc) }
    return () => { try { window.turnstile?.remove(id) } catch {} };
  }, []);
  return TS_KEY ? <div ref={box} style={{margin:'12px 0'}}/> : null;
}
