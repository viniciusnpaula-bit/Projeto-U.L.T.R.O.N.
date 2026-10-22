import { criarOrbe } from './src/orb.js';

/* Janela flutuante: recebe um retrato pronto do núcleo (via main.js) e ecoa
   verbos aprovados. Não fala com a API; não tem token; não inventa estado. */
const $ = id => document.getElementById(id);
const orb = criarOrbe($('hudOrb'));
orb.iniciar();

$('hudReturn').onclick = () => window.ultron?.returnToMain?.();

/* o painel principal publica os snapshots; aqui só pintamos */
function pintar(snapshot) {
  if (!snapshot) return;
  document.documentElement.dataset.theme = snapshot.theme || 'ultron';
  $('hudResponse').textContent = snapshot.response || 'aguardando o núcleo';
  $('hudCoreText').textContent = snapshot.core || '—';
  $('hudMicText').textContent = snapshot.microphone || '—';
  const online = snapshot.core === 'Online' && snapshot.api === 'Conectada';
  $('hudDot').className = `hud-dot ${online ? 'online' : snapshot.core ? 'warn' : 'error'}`;
  $('hudCore').className = snapshot.core === 'Online' ? 'online' : snapshot.core === 'Parado' ? 'error' : '';
  $('hudMic').className = /captur/i.test(snapshot.microphone || '') ? 'online' : /erro/i.test(snapshot.microphone || '') ? 'error' : '';
  const falando = /respond/i.test(snapshot.response || '');
  orb.definir({ energia: falando ? 0.7 : 0.15, brilho: online ? 0.9 : 0.4 });
}

window.ultron?.onHudSnapshot?.(pintar);
window.ultron?.getHudSnapshot?.().then(snapshot => { if (snapshot) pintar(snapshot); });

/* verbos: só os nomes permitidos; o painel principal executa e devolve o aceite */
document.querySelectorAll('[data-hud-action]').forEach(botao => {
  botao.onclick = async () => {
    const alvo = botao.dataset.hudAction;
    botao.disabled = true;
    try { await window.ultron?.runHudAction?.(alvo); }
    finally { setTimeout(() => { botao.disabled = false; }, 600); }
  };
});

document.addEventListener('visibilitychange', () => {
  document.hidden ? orb.parar() : orb.iniciar();
});
