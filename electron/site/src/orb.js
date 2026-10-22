// Núcleo do ULTRON: um sol de vento, não mais anéis girando.
// Camadas: halo pulsante → filamentos de plasma → anel de horizonte → pupila.
// Tudo em "lighter" para somar luz, e o estado real do núcleo muda a energia.
// Traduz o status do núcleo em { rotulo, energia, brilho, dica }. `mem` guarda o instante da última fala sua.
export function estadoDoOrbe(s, mem, agora) {
  if (!s || s.core_running !== true) {
    return { rotulo: 'SEM NÚCLEO', dica: 'O núcleo local não respondeu. Abra pelo ULTRON.exe.', energia: 0, brilho: 0.25 };
  }
  if (s.microphone_error) {
    return { rotulo: 'MICROFONE', dica: String(s.microphone_error).slice(0, 120), energia: 0, brilho: 0.3 };
  }
  if (s.microphone_paused) {
    return { rotulo: 'EM SILÊNCIO', dica: 'Escuta pausada. Clique no microfone para retomar.', energia: 0, brilho: 0.35 };
  }
  if (s.speaking) return { rotulo: 'RESPONDENDO', dica: 'O ULTRON está falando.', energia: 0.75, brilho: 1 };
  if (s.microphone_state === 'processando') {
    return { rotulo: 'PENSANDO', dica: 'Processando o comando…', energia: 0.45, brilho: 1 };
  }
  const limiar = Number(s.microphone_threshold) || 0;
  if (s.microphone_capturing && limiar > 0 && Number(s.microphone_level) > limiar * 0.8) mem.ateFala = agora + 700;
  if (agora < (mem.ateFala || 0)) return { rotulo: 'OUVINDO VOCÊ', dica: 'Fale — estou captando sua voz.', energia: 1, brilho: 1 };
  if (s.microphone_state === 'calibrando' || s.microphone_state === 'iniciando') {
    return { rotulo: 'CALIBRANDO', dica: 'Medindo o ruído do ambiente…', energia: 0.25, brilho: 0.7 };
  }
  return { rotulo: 'À ESCUTA', dica: 'Diga “Ei, Ultron” ou escreva abaixo.', energia: 0, brilho: 0.85 };
}

function hexParaHsl(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex).trim());
  const n = m ? parseInt(m[1], 16) : 0xff3446;
  const r = (n >> 16 & 255) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min;
  let h = 0;
  if (d) h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return { h: (h * 60 + 360) % 360, s: d ? d / (1 - Math.abs(2 * l - 1)) : 0 };
}

export function criarOrbe(canvas) {
  const c = canvas.getContext('2d');
  const reduzir = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const FILAMENTOS = 5;
  const SEGMENTOS = 320;
  const filamentos = Array.from({ length: FILAMENTOS }, (_, f) => ({
    raio: 0.34 + f * 0.052,
    ondulacao: 0.035 + f * 0.011,
    // ordens de ruído diferentes por camada: nunca "pulsa em sincronia"
    k: 3 + f, m: 7 + (f % 3), p: f * 1.73, v: 0.7 + f * 0.23,
  }));
  let raf = 0, ultimo = 0, fase = 0, giro = 0, energia = 0, brilho = 0.8;
  let alvo = { energia: 0, brilho: 0.8 }, cor = hexParaHsl('#ff3446'), corLida = 0;
  let w = 0, h = 0, dpr = 1;

  function medir() {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    w = canvas.clientWidth || 320; h = canvas.clientHeight || 320;
    canvas.width = Math.max(1, Math.round(w * dpr));
    canvas.height = Math.max(1, Math.round(h * dpr));
  }
  new ResizeObserver(medir).observe(canvas);

  function linha(raio, amplitude, t, corDaCamada, grossura, alfa) {
    c.beginPath();
    for (let i = 0; i <= SEGMENTOS; i++) {
      const a = (i / SEGMENTOS) * Math.PI * 2;
      const r = raio * (1 + amplitude * (
        Math.sin(3 * a + fase * 1.1 + t.p) * 0.6 +
        Math.sin(5 * a - fase * 0.8 + t.p * 2) * 0.3 +
        Math.sin(8 * a + fase * 1.7 + t.v) * 0.18
      ));
      const x = Math.cos(a) * r, y = Math.sin(a) * r;
      i ? c.lineTo(x, y) : c.moveTo(x, y);
    }
    c.closePath();
    c.lineWidth = grossura;
    c.strokeStyle = corDaCamada;
    c.globalAlpha = alfa;
    c.stroke();
    c.globalAlpha = 1;
  }

  function quadro(t) {
    const dt = Math.min(0.05, (t - ultimo) / 1000 || 0.016);
    ultimo = t;
    if (t - corLida > 800) {          // a cor acompanha --core do tema
      cor = hexParaHsl(getComputedStyle(document.documentElement).getPropertyValue('--core'));
      corLida = t;
    }
    const ataque = alvo.energia > energia;
    energia += (alvo.energia - energia) * (1 - Math.exp(-dt * (ataque ? 9 : 2.2)));
    brilho += (alvo.brilho - brilho) * (1 - Math.exp(-dt * 3.4));
    const vel = reduzir ? 0.25 : 1;
    fase += dt * (0.6 + 3.4 * energia) * vel;
    giro += dt * (0.05 + 0.55 * energia) * vel;

    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, canvas.width, canvas.height);
    c.scale(dpr, dpr);
    c.translate(w / 2, h / 2);
    const R = Math.min(w, h) * 0.5;
    const sat = 62 + 38 * energia;
    const luz = 44 + 14 * energia;
    const intensidade = (0.55 + 0.45 * energia) * brilho;

    c.globalCompositeOperation = 'lighter';

    // 1) halo atmosférico
    const halo = c.createRadialGradient(0, 0, R * 0.1, 0, 0, R);
    halo.addColorStop(0, `hsla(${cor.h}, ${sat}%, ${luz}%, ${0.30 * intensidade})`);
    halo.addColorStop(0.42, `hsla(${cor.h}, ${sat}%, ${luz - 12}%, ${0.13 * intensidade})`);
    halo.addColorStop(1, `hsla(${cor.h}, ${sat}%, ${luz - 18}%, 0)`);
    c.fillStyle = halo;
    c.beginPath(); c.arc(0, 0, R, 0, Math.PI * 2); c.fill();

    // 2) coroa: filamentos irregulares
    c.save();
    c.rotate(giro);
    for (const f of filamentos) {
      const raio = R * f.raio * (1 + 0.03 * Math.sin(fase * 0.5 + f.p));
      linha(raio, f.ondulacao * (1 + energia * 1.6),
        f, `hsla(${cor.h}, ${sat}%, ${luz + 12}%, 1)`, 1.1 + energia * 0.5, 0.5 * brilho);
    }
    c.restore();

    // 3) horizonte: um anel nítido que "conserta" a instabilidade
    c.save();
    c.rotate(-giro * 0.6);
    c.beginPath(); c.arc(0, 0, R * 0.28, 0, Math.PI * 2);
    c.lineWidth = 1.6;
    c.strokeStyle = `hsla(${cor.h}, ${sat}%, ${luz + 22}%, ${0.85 * brilho})`;
    c.stroke();
    c.restore();

    // 4) pupila: luz concentrada, respira com a energia
    const pulso = 1 + 0.05 * Math.sin(fase * 1.6) + 0.12 * energia;
    const pupila = c.createRadialGradient(0, 0, 0, 0, 0, R * 0.22 * pulso);
    pupila.addColorStop(0, `hsla(${cor.h}, 30%, 96%, ${0.95 * brilho})`);
    pupila.addColorStop(0.35, `hsla(${cor.h}, ${sat}%, ${luz + 20}%, ${0.7 * brilho})`);
    pupila.addColorStop(1, `hsla(${cor.h}, ${sat}%, ${luz}%, 0)`);
    c.fillStyle = pupila;
    c.beginPath(); c.arc(0, 0, R * 0.24 * pulso, 0, Math.PI * 2); c.fill();

    c.globalCompositeOperation = 'source-over';
    raf = requestAnimationFrame(quadro);
  }

  return {
    iniciar() { if (!raf) { medir(); ultimo = performance.now(); raf = requestAnimationFrame(quadro); } },
    parar() { cancelAnimationFrame(raf); raf = 0; },
    definir(e) { alvo = e; },
    medir,
  };
}

// Campo de partículas do fundo: poeira lenta que reage à energia do núcleo.
export function criarCampo(canvas) {
  const c = canvas.getContext('2d');
  const reduzir = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  let w = 0, h = 0, dpr = 1, pontos = [], raf = 0, t0 = performance.now(), ultimo = performance.now();
  function medir() {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    w = window.innerWidth; h = window.innerHeight;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    const total = Math.round(Math.min(150, (w * h) / 16000));
    pontos = Array.from({ length: total }, () => ({
      x: Math.random() * w, y: Math.random() * h,
      r: 0.4 + Math.random() * 1.1, v: 0.02 + Math.random() * 0.08,
      p: Math.random() * Math.PI * 2,
    }));
  }
  window.addEventListener('resize', medir);
  function quadro(t) {
    const dt = Math.min(0.05, (t - ultimo) / 1000 || 0.016);
    ultimo = t;
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, canvas.width, canvas.height);
    c.scale(dpr, dpr);
    const cor = getComputedStyle(document.documentElement).getPropertyValue('--core').trim() || '#ff3446';
    for (const p of pontos) {
      if (!reduzir) {
        p.y -= p.v * 22 * dt;
        p.x += Math.sin((t / 1000) * 0.2 + p.p) * 0.06;
        if (p.y < -4) { p.y = h + 4; p.x = Math.random() * w; }
      }
      c.globalAlpha = 0.16 + 0.3 * (0.5 + 0.5 * Math.sin((t / 1000) * 0.6 + p.p));
      c.fillStyle = cor;
      c.beginPath(); c.arc(p.x, p.y, p.r, 0, Math.PI * 2); c.fill();
    }
    c.globalAlpha = 1;
    raf = requestAnimationFrame(quadro);
  }
  return {
    iniciar() { medir(); raf = requestAnimationFrame(quadro); },
    parar() { cancelAnimationFrame(raf); raf = 0; },
  };
}
