// Small celebrations that make practice feel good. They respect "reduce motion".

export function confetti(count = 90) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const canvas = document.createElement("canvas");
  Object.assign(canvas.style, { position: "fixed", inset: "0", width: "100%", height: "100%", pointerEvents: "none", zIndex: "80" });
  canvas.width = innerWidth; canvas.height = innerHeight;
  document.body.append(canvas);
  const ctx = canvas.getContext("2d");
  const colours = ["#8c2a1c", "#a67c1f", "#2c5a3c", "#201b15", "#c27803", "#5b6f8a"];
  const bits = Array.from({ length: count }, () => ({
    x: canvas.width / 2 + (Math.random() - 0.5) * 200, y: canvas.height * 0.35,
    vx: (Math.random() - 0.5) * 12, vy: -Math.random() * 12 - 4, size: 6 + Math.random() * 6,
    colour: colours[(Math.random() * colours.length) | 0], spin: Math.random() * 6, life: 0,
  }));
  let frame = 0;
  (function tick() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const b of bits) {
      b.vy += 0.35; b.x += b.vx; b.y += b.vy; b.spin += 0.2; b.life += 1;
      ctx.save(); ctx.translate(b.x, b.y); ctx.rotate(b.spin);
      ctx.globalAlpha = Math.max(0, 1 - b.life / 110);
      ctx.fillStyle = b.colour; ctx.fillRect(-b.size / 2, -b.size / 4, b.size, b.size / 2);
      ctx.restore();
    }
    if (++frame < 110) requestAnimationFrame(tick); else canvas.remove();
  })();
}
