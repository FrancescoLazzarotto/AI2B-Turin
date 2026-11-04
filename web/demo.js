/* Demo automatica di Welfare Compass.
   Uso: copiare questo file nella stessa cartella di index.html, aggiungere prima di </body> la riga
   <script>if (/demo/.test(location.search)) { const d=document.createElement('script'); d.src='demo.js'; document.body.appendChild(d); }</script>
   e aprire index.html?demo=1 (oppure http://localhost:PORTA/?demo=1 se l'app è servita dal back end).
   Porta a termine un compito completo: profilo compilato dall'AI dal testo libero, piano, mappa, scheda della zona, due domande al chatbot.
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
    await aspetta(() => document.querySelectorAll('.qa').length > prima, 20000);
    await aspetta(() => { const a = [...document.querySelectorAll('.qa .a')].pop(); return a && !/sta cercando/.test(a.textContent); }, 60000);
    const ultima = [...document.querySelectorAll('.qa')].pop(); if (ultima) ultima.scrollIntoView({behavior:'smooth', block:'center'});
    await wait(attesa);
  }

  async function run(){
    location.hash = '#/'; await wait(1500);
    const testo = 'Siamo la Fondazione Torino Solidale, una fondazione bancaria. Vogliamo investire 150.000 euro contro la solitudine degli anziani e la carenza di servizi sanitari di prossimità, con 6 operatori, nelle circoscrizioni 2, 5 e 6.';
    const o = $('#orgText');
    if (o){
      say('1', 'Descrivo l\'organizzazione con parole mie');
      o.scrollIntoView({behavior:'smooth', block:'center'}); await wait(600);
      o.classList.add('demo-hl'); o.value = ''; await scrivi(o, testo, 28); o.classList.remove('demo-hl'); await wait(800);
      say('2', 'L\'AI legge il testo e compila il profilo'); await tocca('#orgParse');
      await aspetta(() => !$('#orgParse').disabled, 60000); await wait(2500);
    }
    say('3', 'Chi sei: fondazione bancaria');
    $('#chi').scrollIntoView({behavior:'smooth', block:'center'}); await wait(3000);
    say('4', 'Budget 150.000 € e bisogni, impostati dall\'AI');
    $('.bento').scrollIntoView({behavior:'smooth', block:'center'}); await wait(3500);
    say('5', 'Dove: circoscrizioni 2, 5 e 6');
    $('#circ').scrollIntoView({behavior:'smooth', block:'center'}); await wait(3000);
    say('6', 'Genero il piano'); await tocca('#cta');
    await aspetta(() => location.hash === '#/mappa', 20000); await wait(3500);
    say('7', 'La mappa del rischio: in nero le zone scelte'); await wait(5500);
    // prima zona del piano: dallo stato dell'app se c'è, altrimenti dalla pagina Piano
    let primo = null;
    try { primo = S.plan.items[0].p; } catch(e) {}
    if (primo && typeof apriZona === 'function' && typeof F !== 'undefined'){
      say('8', `Apro ${primo.nome}: dati e fonti della zona`);
      apriZona(F.find(f => f.properties.id === primo.id)); await wait(5500);
      if (typeof chiudiZona === 'function') chiudiZona(); await wait(800);
    }
    say('9', 'Il piano: dove, con quale intervento, quanto'); location.hash = '#/piano'; await wait(4000);
    const nome = primo ? primo.nome : (($('.pc h3') || {}).textContent || '').trim();
    window.scrollTo({top: 420, behavior:'smooth'}); await wait(3500); window.scrollTo({top: 0, behavior:'smooth'}); await wait(1500);
    say('10', 'Come funziona: metodo e fonti dei dati'); await tocca('#infoBtn'); await wait(8000);
    await tocca('#sheetClose'); await wait(600);
    say('11', 'Interrogo il chatbot sul piano generato'); location.hash = '#/chiedi'; await wait(2000);
    if (nome) await chiedi(`Perché ${nome}?`, 5000);
    await chiedi('Quanto è solido il piano?', 4500);
    say('', 'Fatto: il piano è pronto per il consiglio della fondazione');
  }
  if (document.readyState === 'complete') setTimeout(run, 600); else window.addEventListener('load', () => setTimeout(run, 600));
})();