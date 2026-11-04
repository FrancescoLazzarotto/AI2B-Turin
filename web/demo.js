/* Demo automatica di Bussola Welfare.
   Uso: copiare questo file nella stessa cartella di index.html, aggiungere prima di </body> la riga
   <script>if (/demo/.test(location.search)) { const d=document.createElement('script'); d.src='demo.js'; document.body.appendChild(d); }</script>
   e aprire index.html?demo=1 (oppure http://localhost:PORTA/?demo=1 se l'app è servita dal back end).
   Porta a termine un compito completo: scelte della fondazione, piano, mappa, scheda della zona, due domande al chatbot.
   Usa solo l'interfaccia: funziona anche se calcolo e chatbot arrivano dal back end. */
(function(){
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const $ = s => document.querySelector(s);
  const st = document.createElement('style');
  st.textContent = `.democap{position:fixed;left:50%;top:14px;transform:translate(-50%,-30px);opacity:0;z-index:3000;background:#111;color:#fff;border-radius:999px;padding:12px 22px;font:600 17px Urbanist,-apple-system,sans-serif;box-shadow:0 12px 30px rgba(0,0,0,.25);transition:transform .5s cubic-bezier(.2,.9,.25,1.12),opacity .3s;white-space:nowrap;max-width:calc(100% - 24px);overflow:hidden;text-overflow:ellipsis}
  .democap.on{transform:translate(-50%,0);opacity:1}
  .democap b{color:#f7cf6f;font-weight:700;margin-right:8px}
  .demo-hl{outline:3px solid #f7cf6f!important;outline-offset:3px}`;
  document.head.appendChild(st);
  const cap = document.createElement('div'); cap.className = 'democap'; document.body.appendChild(cap);
  const say = (n, t) => { cap.innerHTML = (n ? `<b>${n}</b>` : '') + t; cap.classList.add('on'); };

  async function tocca(sel){
    const el = $(sel); if (!el) { console.warn('demo: elemento non trovato', sel); return; }
    el.scrollIntoView({behavior:'smooth', block:'center'}); await wait(550);
    el.classList.add('demo-hl'); await wait(250); el.click(); await wait(450); el.classList.remove('demo-hl');
  }
  async function scrivi(el, testo, ms=55){ for (const c of testo){ el.value += c; el.dispatchEvent(new Event('input', {bubbles:true})); await wait(ms); } }
  async function aspetta(cond, max=15000){ const t0 = Date.now(); while (!cond() && Date.now()-t0 < max) await wait(200); return cond(); }
  async function chiedi(testo, attesa){
    const q = $('#q'), form = $('#askbar'); if (!q || !form) return;
    const prima = document.querySelectorAll('.qa').length;
    q.classList.add('demo-hl'); await scrivi(q, testo); await wait(400); form.requestSubmit(); q.classList.remove('demo-hl');
    await aspetta(() => document.querySelectorAll('.qa').length > prima, 20000);   // attende anche una risposta lenta dal back end
    await wait(attesa);
  }

  async function run(){
    location.hash = '#/'; await wait(900);
    say('1', 'Chi sei: una fondazione bancaria'); await tocca('#chi [data-v="fondazione"]'); await wait(700);
    say('2', 'Quanto investire: 150.000 €');
    const b = $('#budget');
    if (b){ b.scrollIntoView({behavior:'smooth', block:'center'}); await wait(500); b.classList.add('demo-hl'); b.value = ''; b.dispatchEvent(new Event('input', {bubbles:true})); await scrivi(b, '150000', 110); b.classList.remove('demo-hl'); }
    await wait(500);
    say('3', 'Cosa conta: isolamento demografico e carenza di servizi');
    await tocca('.need[data-k="iso"] .level [data-v="2"]'); await tocca('.need[data-k="ser"] .level [data-v="2"]'); await tocca('.need[data-k="lav"] .level [data-v="1"]'); await wait(400);
    say('4', 'Dove: escludiamo il centro, circoscrizione 1');
    const c1 = $('#circ [data-c="1"]'); if (c1 && c1.getAttribute('aria-pressed') !== 'false') await tocca('#circ [data-c="1"]');
    await wait(600);
    say('5', 'Genero il piano'); await tocca('#cta');
    await aspetta(() => location.hash === '#/mappa', 20000); await wait(3800);
    say('6', 'La mappa del rischio: in nero le zone scelte'); await wait(3200);
    // prima zona del piano: dallo stato dell'app se c'è, altrimenti dalla pagina Piano
    let primo = null;
    try { primo = S.plan.items[0].p; } catch(e) {}
    if (primo && typeof apriZona === 'function' && typeof F !== 'undefined'){
      say('7', `Apro ${primo.nome}: dati e fonti della zona`);
      apriZona(F.find(f => f.properties.id === primo.id)); await wait(4200);
      if (typeof chiudiZona === 'function') chiudiZona(); await wait(400);
    }
    say('8', 'Il piano: dove, con quale intervento, quanto'); location.hash = '#/piano'; await wait(2200);
    const nome = primo ? primo.nome : (($('.pc h3') || {}).textContent || '').trim();
    window.scrollTo({top: 420, behavior:'smooth'}); await wait(2200); window.scrollTo({top: 0, behavior:'smooth'}); await wait(900);
    say('9', 'Interrogo il chatbot sul piano generato'); location.hash = '#/chiedi'; await wait(1300);
    if (nome) await chiedi(`Perché ${nome}?`, 3800);
    await chiedi('Quanto è solido il piano?', 3600);
    say('', 'Fatto: il piano è pronto per il consiglio della fondazione');
  }
  if (document.readyState === 'complete') setTimeout(run, 600); else window.addEventListener('load', () => setTimeout(run, 600));
})();