export const styles = `
.dsh-collab-root {
  --collab-accent: var(--dsw-alias-state-business-primary, #638cff);
  --collab-cyan: #38d9ff;
  --collab-violet: #9a72ff;
  --collab-success: var(--dsw-alias-state-success-primary, #35d49a);
  --collab-error: var(--dsw-alias-state-error-primary, #ff6674);
  --collab-warning: #ffb84d;
  --collab-muted: var(--dsw-alias-label-tertiary, #8d95a6);
  position:relative; isolation:isolate; height:100%; min-height:0; overflow:hidden; box-sizing:border-box;
  display:flex; flex-direction:column; color:var(--dsw-alias-label-primary,#edf2ff);
  background:
    linear-gradient(rgba(99,140,255,.025) 1px,transparent 1px),
    linear-gradient(90deg,rgba(99,140,255,.025) 1px,transparent 1px),
    radial-gradient(circle at 48% 8%,color-mix(in srgb,var(--collab-accent) 20%,transparent),transparent 32%),
    var(--dsw-alias-bg-layer-1,#0e1119);
  background-size:28px 28px,28px 28px,auto,auto;
}
.dsh-collab-atmosphere { position:absolute; inset:0; z-index:-1; overflow:hidden; pointer-events:none; }
.dsh-collab-atmosphere i { position:absolute; width:280px; height:280px; border-radius:50%; filter:blur(80px); opacity:.11; animation:dsh-collab-drift 13s ease-in-out infinite alternate; }
.dsh-collab-atmosphere i:nth-child(1) { left:10%; top:8%; background:var(--collab-cyan); }
.dsh-collab-atmosphere i:nth-child(2) { right:8%; top:25%; background:var(--collab-violet); animation-delay:-5s; }
.dsh-collab-atmosphere i:nth-child(3) { left:42%; bottom:-180px; background:var(--collab-success); animation-delay:-9s; }
.dsh-collab-header { position:relative; padding:18px 24px 14px; border-bottom:1px solid color-mix(in srgb,var(--collab-accent) 18%,var(--dsw-alias-border-l2,#2c3240)); background:color-mix(in srgb,var(--dsw-alias-bg-layer-1,#0e1119) 82%,transparent); backdrop-filter:blur(16px); }
.dsh-collab-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.dsh-collab-heading h2 { margin:0; font-size:20px; letter-spacing:-.025em; background:linear-gradient(100deg,var(--dsw-alias-label-primary,#edf2ff),color-mix(in srgb,var(--collab-cyan) 78%,white)); -webkit-background-clip:text; background-clip:text; color:transparent; }
.dsh-collab-subtitle { margin:6px 0 0; font-size:12px; color:var(--dsw-alias-label-secondary,#adb5c7); }
.dsh-collab-live { display:inline-flex; align-items:center; gap:7px; padding:6px 10px; border:1px solid color-mix(in srgb,var(--collab-success) 42%,transparent); border-radius:999px; color:var(--collab-success); background:color-mix(in srgb,var(--collab-success) 10%,transparent); box-shadow:0 0 24px color-mix(in srgb,var(--collab-success) 10%,transparent); font-size:10px; font-weight:800; letter-spacing:.12em; }
.dsh-collab-live::before { content:""; width:7px; height:7px; border-radius:50%; background:currentColor; box-shadow:0 0 0 0 color-mix(in srgb,var(--collab-success) 40%,transparent); animation:dsh-collab-ping 1.6s infinite; }
.dsh-collab-live.replay { color:var(--collab-muted); border-color:var(--dsw-alias-border-l2,#2c3240); background:var(--dsw-alias-bg-layer-2,#171b25); box-shadow:none; }
.dsh-collab-live.replay::before { animation:none; }
.dsh-collab-metrics { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin-top:14px; }
.dsh-collab-metric { position:relative; overflow:hidden; padding:9px 12px; border:1px solid color-mix(in srgb,var(--collab-accent) 14%,var(--dsw-alias-border-l2,#2c3240)); border-radius:10px; background:color-mix(in srgb,var(--dsw-alias-bg-layer-2,#171b25) 84%,transparent); }
.dsh-collab-metric::after { content:""; position:absolute; inset:auto 0 0; height:1px; background:linear-gradient(90deg,transparent,var(--collab-accent),transparent); opacity:.45; }
.dsh-collab-metric strong { display:block; font-size:18px; line-height:1; font-variant-numeric:tabular-nums; }
.dsh-collab-metric span { display:block; margin-top:5px; font-size:10px; color:var(--collab-muted); }
.dsh-collab-content { min-height:0; flex:1; display:grid; grid-template-columns:minmax(600px,1fr) minmax(270px,340px); }
.dsh-collab-stage { min-height:0; overflow:auto; padding:18px 24px calc(var(--dsh-composer-height,152px) + 28px); border-right:1px solid var(--dsw-alias-border-l2,#2c3240); }
.dsh-collab-section-title { margin:0 0 15px; color:var(--collab-muted); font-size:10px; font-weight:800; letter-spacing:.15em; text-transform:uppercase; }
.dsh-collab-core-map { display:grid; grid-template-columns:minmax(150px,1fr) minmax(50px,.55fr) minmax(170px,1fr) minmax(50px,.55fr) minmax(150px,1fr); grid-template-rows:auto 54px auto; align-items:center; }
.dsh-collab-core-registry { grid-column:1; grid-row:1; }
.dsh-collab-core-discovery { grid-column:2; grid-row:1; }
.dsh-collab-core-coordinator { grid-column:3; grid-row:1; }
.dsh-collab-core-local { grid-column:4; grid-row:1; }
.dsh-collab-core-workspace { grid-column:5; grid-row:1; }
.dsh-collab-core-invocation { grid-column:3; grid-row:2; align-self:stretch; }
.dsh-collab-core-bridge { grid-column:3; grid-row:3; }
.dsh-collab-node { position:relative; z-index:2; min-width:0; box-sizing:border-box; padding:13px; border:1px solid color-mix(in srgb,var(--collab-accent) 12%,var(--dsw-alias-border-l2,#2c3240)); border-radius:14px; background:linear-gradient(145deg,color-mix(in srgb,var(--dsw-alias-bg-layer-2,#171b25) 97%,var(--collab-accent)),color-mix(in srgb,var(--dsw-alias-bg-layer-1,#0e1119) 96%,transparent)); box-shadow:0 10px 30px rgba(0,0,0,.18),inset 0 1px rgba(255,255,255,.035); transition:border-color .25s,transform .25s,box-shadow .25s; }
.dsh-collab-node-glow { position:absolute; z-index:-1; inset:-13px; border-radius:24px; opacity:0; background:radial-gradient(ellipse at center,color-mix(in srgb,var(--collab-accent) 48%,transparent),transparent 72%); filter:blur(13px); transform:scale(.95); transition:opacity .3s; }
.dsh-collab-node.discovered { border-color:color-mix(in srgb,var(--collab-cyan) 38%,transparent); animation:dsh-collab-materialize .55s cubic-bezier(.2,.8,.2,1) both; }
.dsh-collab-node.working { border-color:color-mix(in srgb,var(--collab-accent) 88%,white 6%); transform:translateY(-3px) scale(1.012); box-shadow:0 0 0 1px color-mix(in srgb,var(--collab-accent) 22%,transparent),0 0 34px color-mix(in srgb,var(--collab-accent) 24%,transparent),0 18px 38px rgba(0,0,0,.22); animation:dsh-collab-breathe 1.7s ease-in-out infinite; }
.dsh-collab-node.working .dsh-collab-node-glow { opacity:.62; animation:dsh-collab-glow-breathe 2.25s ease-in-out infinite; }
.dsh-collab-node.completed { border-color:color-mix(in srgb,var(--collab-success) 55%,transparent); box-shadow:0 0 22px color-mix(in srgb,var(--collab-success) 9%,transparent),0 10px 30px rgba(0,0,0,.16); }
.dsh-collab-node.error { border-color:color-mix(in srgb,var(--collab-error) 78%,transparent); box-shadow:0 0 28px color-mix(in srgb,var(--collab-error) 18%,transparent); }
.dsh-collab-node-coordinator { background:linear-gradient(145deg,color-mix(in srgb,var(--collab-accent) 22%,var(--dsw-alias-bg-layer-2,#171b25)),var(--dsw-alias-bg-layer-2,#171b25)); }
.dsh-collab-node-bridge { background:linear-gradient(145deg,color-mix(in srgb,var(--collab-violet) 19%,var(--dsw-alias-bg-layer-2,#171b25)),var(--dsw-alias-bg-layer-2,#171b25)); }
.dsh-collab-node-head { display:flex; gap:10px; align-items:center; }
.dsh-collab-avatar { flex:0 0 auto; width:34px; height:34px; display:grid; place-items:center; border-radius:11px; color:#fff; background:linear-gradient(135deg,var(--collab-accent),var(--collab-violet)); font-size:12px; font-weight:900; letter-spacing:-.04em; box-shadow:0 6px 18px color-mix(in srgb,var(--collab-accent) 25%,transparent); }
.dsh-collab-node-registry .dsh-collab-avatar { background:linear-gradient(135deg,#00a7a0,#45d6a3); }
.dsh-collab-node-workspace .dsh-collab-avatar { background:linear-gradient(135deg,#df7e27,#ffc257); }
.dsh-collab-node-bridge .dsh-collab-avatar { background:linear-gradient(135deg,#7458e8,#c35bff); font-size:9px; }
.dsh-collab-node-title { min-width:0; flex:1; }
.dsh-collab-node-title strong { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:12px; }
.dsh-collab-status { display:inline-flex; align-items:center; gap:5px; margin-top:3px; color:var(--collab-muted); font-size:10px; }
.dsh-collab-status::before { content:""; width:6px; height:6px; border-radius:50%; background:currentColor; box-shadow:0 0 8px currentColor; }
.dsh-collab-node.discovered .dsh-collab-status { color:var(--collab-cyan); }
.dsh-collab-node.working .dsh-collab-status { color:var(--collab-accent); }
.dsh-collab-node.completed .dsh-collab-status { color:var(--collab-success); }
.dsh-collab-node.error .dsh-collab-status { color:var(--collab-error); }
.dsh-collab-protocol { flex:0 0 auto; padding:3px 6px; border:1px solid color-mix(in srgb,var(--collab-cyan) 25%,transparent); border-radius:999px; color:var(--collab-cyan); background:color-mix(in srgb,var(--collab-cyan) 7%,transparent); font:800 8px/1 var(--ds-font-family-code,monospace); letter-spacing:.08em; }
.dsh-collab-description { display:-webkit-box; min-height:29px; margin:10px 0 0; overflow:hidden; -webkit-box-orient:vertical; -webkit-line-clamp:2; color:var(--collab-muted); font-size:10px; line-height:1.45; }
.dsh-collab-latest { min-height:30px; margin:10px 0 0; font-size:11px; line-height:1.45; color:var(--dsw-alias-label-secondary,#adb5c7); }
.dsh-collab-meta { margin-top:8px; display:grid; gap:3px; font-family:var(--ds-font-family-code,monospace); color:var(--collab-muted); font-size:8.5px; }
.dsh-collab-meta div { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.dsh-collab-route { position:relative; z-index:1; display:grid; place-items:center; min-width:0; }
.dsh-collab-route.horizontal { height:50px; }
.dsh-collab-route.vertical { width:100%; height:100%; }
.dsh-collab-route-track { position:absolute; overflow:hidden; color:var(--dsw-alias-border-l1,#3a4252); background:currentColor; box-shadow:0 0 0 transparent; transition:color .25s,box-shadow .25s; }
.dsh-collab-route.horizontal .dsh-collab-route-track { left:0; right:0; top:50%; height:2px; transform:translateY(-50%); }
.dsh-collab-route.vertical .dsh-collab-route-track { top:0; bottom:0; left:50%; width:2px; transform:translateX(-50%); }
.dsh-collab-route-track::after { content:""; position:absolute; width:7px; height:7px; border-top:2px solid currentColor; border-right:2px solid currentColor; }
.dsh-collab-route.horizontal .dsh-collab-route-track::after { right:1px; top:50%; transform:translateY(-50%) rotate(45deg); }
.dsh-collab-route.vertical .dsh-collab-route-track::after { bottom:1px; left:50%; transform:translateX(-50%) rotate(135deg); }
.dsh-collab-route-track i { position:absolute; display:block; border-radius:50%; opacity:0; background:#fff; box-shadow:0 0 4px #fff,0 0 15px currentColor,0 0 28px currentColor; }
.dsh-collab-route.horizontal .dsh-collab-route-track i { left:-20%; top:0; width:22%; height:100%; }
.dsh-collab-route.vertical .dsh-collab-route-track i { left:0; top:-20%; width:100%; height:22%; }
.dsh-collab-route-label { position:relative; z-index:2; padding:3px 6px; border-radius:999px; color:var(--collab-muted); background:var(--dsw-alias-bg-layer-1,#0e1119); font:800 8px/1 var(--ds-font-family-code,monospace); letter-spacing:.12em; }
.dsh-collab-route.working .dsh-collab-route-track { color:var(--collab-cyan); box-shadow:0 0 12px color-mix(in srgb,var(--collab-cyan) 65%,transparent); }
.dsh-collab-route.working .dsh-collab-route-track i { opacity:1; }
.dsh-collab-route.horizontal.working .dsh-collab-route-track i { animation:dsh-collab-flow-x 1.05s linear infinite; }
.dsh-collab-route.vertical.working .dsh-collab-route-track i { animation:dsh-collab-flow-y 1.05s linear infinite; }
.dsh-collab-route.working .dsh-collab-route-label { color:var(--collab-cyan); box-shadow:0 0 14px color-mix(in srgb,var(--collab-cyan) 13%,transparent); }
.dsh-collab-route.completed .dsh-collab-route-track,.dsh-collab-route.discovered .dsh-collab-route-track { color:color-mix(in srgb,var(--collab-success) 60%,var(--dsw-alias-border-l1,#3a4252)); }
.dsh-collab-route.error .dsh-collab-route-track { color:var(--collab-error); box-shadow:0 0 12px color-mix(in srgb,var(--collab-error) 45%,transparent); }
.dsh-collab-invocation-chain { position:relative; margin-top:18px; padding:14px; overflow:hidden; border:1px solid color-mix(in srgb,var(--collab-cyan) 22%,var(--dsw-alias-border-l2,#2c3240)); border-radius:16px; background:linear-gradient(135deg,color-mix(in srgb,var(--collab-cyan) 7%,var(--dsw-alias-bg-layer-2,#171b25)),color-mix(in srgb,var(--collab-violet) 6%,var(--dsw-alias-bg-layer-1,#0e1119))); box-shadow:inset 0 1px rgba(255,255,255,.035),0 14px 34px rgba(0,0,0,.13); }
.dsh-collab-invocation-chain::before { content:""; position:absolute; left:14px; right:14px; top:0; height:1px; background:linear-gradient(90deg,transparent,var(--collab-cyan),var(--collab-violet),transparent); opacity:.72; }
.dsh-collab-chain-head { display:flex; align-items:flex-start; justify-content:space-between; gap:14px; margin-bottom:12px; }
.dsh-collab-chain-head h3 { margin:0; font-size:12px; letter-spacing:.02em; }
.dsh-collab-chain-head p { margin:4px 0 0; color:var(--collab-muted); font-size:9px; }
.dsh-collab-chain-head > span { flex:0 0 auto; padding:4px 8px; border:1px solid color-mix(in srgb,var(--collab-cyan) 24%,transparent); border-radius:999px; color:var(--collab-cyan); background:color-mix(in srgb,var(--collab-cyan) 7%,transparent); font:700 8px/1 var(--ds-font-family-code,monospace); }
.dsh-collab-chain-list { display:grid; grid-auto-flow:column; grid-auto-columns:minmax(152px,1fr); gap:16px; overflow-x:auto; padding:2px 2px 5px; scrollbar-width:thin; }
.dsh-collab-chain-step { position:relative; min-width:0; }
.dsh-collab-chain-arrow { position:absolute; left:-16px; top:50%; width:16px; height:2px; overflow:hidden; transform:translateY(-50%); color:var(--collab-cyan); background:color-mix(in srgb,var(--collab-cyan) 44%,var(--dsw-alias-border-l1,#3a4252)); }
.dsh-collab-chain-arrow::after { content:""; position:absolute; right:1px; top:50%; width:6px; height:6px; border-top:2px solid currentColor; border-right:2px solid currentColor; transform:translateY(-50%) rotate(45deg); }
.dsh-collab-chain-arrow i { position:absolute; left:-35%; top:0; width:32%; height:100%; border-radius:50%; background:#fff; box-shadow:0 0 5px #fff,0 0 14px currentColor; animation:dsh-collab-flow-x 1.25s linear infinite; }
.dsh-collab-invocation-card { position:relative; min-width:0; padding:11px; overflow:hidden; border:1px solid hsl(var(--agent-hue) 72% 62% / .3); border-radius:13px; background:linear-gradient(145deg,hsl(var(--agent-hue) 65% 52% / .11),color-mix(in srgb,var(--dsw-alias-bg-layer-2,#171b25) 96%,transparent)); box-shadow:0 9px 24px rgba(0,0,0,.16); }
.dsh-collab-invocation-card.completed { border-color:color-mix(in srgb,var(--collab-success) 60%,transparent); }
.dsh-collab-invocation-card.blocked { border-color:color-mix(in srgb,var(--collab-warning) 72%,transparent); box-shadow:0 0 20px color-mix(in srgb,var(--collab-warning) 10%,transparent),0 9px 24px rgba(0,0,0,.16); }
.dsh-collab-invocation-card.error { border-color:color-mix(in srgb,var(--collab-error) 74%,transparent); }
.dsh-collab-invocation-card.working { border-color:hsl(var(--agent-hue) 82% 68% / .86); animation:dsh-collab-breathe 1.7s ease-in-out infinite; }
.dsh-collab-invocation-index { position:absolute; right:9px; top:8px; color:color-mix(in srgb,var(--collab-muted) 42%,transparent); font:900 18px/1 var(--ds-font-family-code,monospace); }
.dsh-collab-invocation-head { display:flex; align-items:center; gap:7px; padding-right:20px; }
.dsh-collab-invocation-head > div { min-width:0; flex:1; }
.dsh-collab-invocation-head strong { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:11px; }
.dsh-collab-invocation-head .dsh-collab-avatar { width:28px; height:28px; border-radius:9px; background:linear-gradient(135deg,hsl(var(--agent-hue) 70% 54%),hsl(calc(var(--agent-hue) + 52deg) 75% 62%)); font-size:9px; }
.dsh-collab-invocation-outcome { display:inline-flex; align-items:center; gap:5px; margin-top:4px; color:var(--collab-success); font-size:9px; }
.dsh-collab-invocation-outcome::before { content:""; width:5px; height:5px; border-radius:50%; background:currentColor; box-shadow:0 0 8px currentColor; }
.dsh-collab-invocation-card.blocked .dsh-collab-invocation-outcome { color:var(--collab-warning); }
.dsh-collab-invocation-card.error .dsh-collab-invocation-outcome { color:var(--collab-error); }
.dsh-collab-invocation-card.working .dsh-collab-invocation-outcome { color:var(--collab-accent); }
.dsh-collab-invocation-meta { display:grid; grid-template-columns:minmax(0,.75fr) minmax(0,1.25fr); gap:7px; margin-top:9px; padding-top:8px; border-top:1px solid color-mix(in srgb,var(--dsw-alias-border-l2,#2c3240) 72%,transparent); color:var(--collab-muted); font:8px/1.3 var(--ds-font-family-code,monospace); }
.dsh-collab-invocation-meta span,.dsh-collab-invocation-meta code { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:inherit; }
.dsh-collab-agent-fanout { position:relative; margin-top:0; padding-top:52px; }
.dsh-collab-fanout-spine { position:absolute; left:50%; top:0; width:2px; height:42px; overflow:hidden; transform:translateX(-50%); background:var(--dsw-alias-border-l1,#3a4252); color:var(--collab-cyan); }
.dsh-collab-fanout-spine::after { content:""; position:absolute; left:50%; bottom:0; width:8px; height:8px; border-right:2px solid currentColor; border-bottom:2px solid currentColor; transform:translate(-50%,-1px) rotate(45deg); }
.dsh-collab-fanout-spine i { position:absolute; left:0; top:-30%; width:100%; height:28%; border-radius:50%; opacity:0; background:#fff; box-shadow:0 0 7px #fff,0 0 18px var(--collab-cyan); }
.dsh-collab-agent-fanout.working .dsh-collab-fanout-spine { background:var(--collab-cyan); box-shadow:0 0 12px color-mix(in srgb,var(--collab-cyan) 60%,transparent); }
.dsh-collab-agent-fanout.working .dsh-collab-fanout-spine i { opacity:1; animation:dsh-collab-flow-y 1.05s linear infinite; }
.dsh-collab-agent-pool-head { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:13px; }
.dsh-collab-agent-pool-head h3 { margin:0; font-size:12px; letter-spacing:.02em; }
.dsh-collab-agent-pool-head span { color:var(--collab-cyan); font:700 9px/1 var(--ds-font-family-code,monospace); }
.dsh-collab-agent-empty { min-height:116px; display:grid; place-content:center; justify-items:center; gap:9px; border:1px dashed color-mix(in srgb,var(--collab-cyan) 25%,var(--dsw-alias-border-l2,#2c3240)); border-radius:16px; background:color-mix(in srgb,var(--dsw-alias-bg-layer-2,#171b25) 54%,transparent); color:var(--collab-muted); text-align:center; }
.dsh-collab-agent-empty span { width:34px; height:34px; display:grid; place-items:center; border:1px solid color-mix(in srgb,var(--collab-cyan) 36%,transparent); border-radius:50%; color:var(--collab-cyan); font-size:20px; animation:dsh-collab-empty-pulse 2s ease-in-out infinite; }
.dsh-collab-agent-empty p { max-width:320px; margin:0; font-size:11px; line-height:1.55; }
.dsh-collab-agents { position:relative; display:grid; grid-template-columns:repeat(auto-fit,minmax(188px,1fr)); align-items:start; gap:12px; padding-top:24px; }
.dsh-collab-agents::before { content:""; position:absolute; left:8%; right:8%; top:7px; height:1px; background:linear-gradient(90deg,transparent,color-mix(in srgb,var(--collab-cyan) 36%,var(--dsw-alias-border-l1,#3a4252)) 10% 90%,transparent); }
.dsh-collab-agent-slot { position:relative; min-width:0; padding-top:0; }
.dsh-collab-agent-link { position:absolute; z-index:0; left:50%; bottom:100%; width:2px; height:18px; overflow:hidden; transform:translateX(-50%); background:color-mix(in srgb,var(--collab-cyan) 28%,var(--dsw-alias-border-l1,#3a4252)); color:var(--collab-cyan); }
.dsh-collab-agent-link i { position:absolute; left:0; top:-40%; width:100%; height:36%; border-radius:50%; opacity:0; background:#fff; box-shadow:0 0 7px #fff,0 0 17px currentColor; }
.dsh-collab-agent-slot.working .dsh-collab-agent-link { background:var(--collab-cyan); box-shadow:0 0 11px color-mix(in srgb,var(--collab-cyan) 65%,transparent); }
.dsh-collab-agent-slot.working .dsh-collab-agent-link i { opacity:1; animation:dsh-collab-flow-y .8s linear infinite; }
.dsh-collab-agent-slot.completed .dsh-collab-agent-link { background:color-mix(in srgb,var(--collab-success) 65%,transparent); }
.dsh-collab-agent-slot.error .dsh-collab-agent-link { background:var(--collab-error); }
.dsh-collab-node-agent { min-height:171px; border-color:hsl(var(--agent-hue) 72% 62% / .28); background:linear-gradient(145deg,hsl(var(--agent-hue) 65% 52% / .11),color-mix(in srgb,var(--dsw-alias-bg-layer-2,#171b25) 95%,transparent)); }
.dsh-collab-node-agent .dsh-collab-avatar { background:linear-gradient(135deg,hsl(var(--agent-hue) 70% 54%),hsl(calc(var(--agent-hue) + 52deg) 75% 62%)); box-shadow:0 6px 18px hsl(var(--agent-hue) 72% 52% / .22); }
.dsh-collab-node-agent.working { border-color:hsl(var(--agent-hue) 82% 68% / .9); box-shadow:0 0 0 1px hsl(var(--agent-hue) 80% 60% / .22),0 0 38px hsl(var(--agent-hue) 80% 60% / .24),0 18px 38px rgba(0,0,0,.2); }
.dsh-collab-node-agent.working .dsh-collab-node-glow { background:radial-gradient(ellipse at center,hsl(var(--agent-hue) 86% 64% / .38),transparent 70%); }
.dsh-collab-timeline { min-height:0; overflow:auto; padding:18px 18px calc(var(--dsh-composer-height,152px) + 24px); background:color-mix(in srgb,var(--dsw-alias-bg-base,#0b0e14) 58%,transparent); backdrop-filter:blur(12px); }
.dsh-collab-empty { padding:24px 10px; text-align:center; color:var(--collab-muted); font-size:11px; line-height:1.6; }
.dsh-collab-events { list-style:none; margin:0; padding:0 0 0 11px; border-left:1px solid var(--dsw-alias-border-l2,#2c3240); }
.dsh-collab-event { position:relative; padding:0 0 16px 16px; opacity:.76; transition:opacity .2s,transform .2s; }
.dsh-collab-event.newest { opacity:1; }
.dsh-collab-event.newest::after { content:""; position:absolute; z-index:-1; inset:-8px -8px 8px 7px; border-radius:10px; background:linear-gradient(90deg,color-mix(in srgb,var(--collab-accent) 10%,transparent),transparent); animation:dsh-collab-event-in .45s ease-out both; }
.dsh-collab-event::before { content:""; position:absolute; left:-5px; top:3px; width:8px; height:8px; border-radius:50%; background:var(--dsw-alias-border-l1,#3a4252); border:2px solid var(--dsw-alias-bg-layer-1,#11141c); }
.dsh-collab-event.working::before { background:var(--collab-accent); box-shadow:0 0 12px color-mix(in srgb,var(--collab-accent) 70%,transparent); animation:dsh-collab-event-pulse 1.4s ease-in-out infinite; }
.dsh-collab-event.discovered::before { background:var(--collab-cyan); box-shadow:0 0 10px color-mix(in srgb,var(--collab-cyan) 55%,transparent); }
.dsh-collab-event.completed::before { background:var(--collab-success); }
.dsh-collab-event.error::before { background:var(--collab-error); }
.dsh-collab-event time { display:block; margin-bottom:4px; font-family:var(--ds-font-family-code,monospace); color:var(--collab-muted); font-size:9px; }
.dsh-collab-event strong { display:block; font-size:11px; line-height:1.4; }
.dsh-collab-event code { display:block; margin-top:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--collab-muted); font-family:var(--ds-font-family-code,monospace); font-size:9px; }
@keyframes dsh-collab-ping { 70% { box-shadow:0 0 0 7px transparent; } 100% { box-shadow:0 0 0 0 transparent; } }
@keyframes dsh-collab-drift { to { transform:translate3d(34px,20px,0) scale(1.12); } }
@keyframes dsh-collab-breathe { 0%,100% { filter:brightness(1); } 50% { filter:brightness(1.17) saturate(1.08); } }
@keyframes dsh-collab-glow-breathe { 0%,100% { opacity:.3; transform:scale(.95); } 50% { opacity:.9; transform:scale(1.085); } }
@keyframes dsh-collab-flow-x { from { transform:translateX(0); } to { transform:translateX(550%); } }
@keyframes dsh-collab-flow-y { from { transform:translateY(0); } to { transform:translateY(550%); } }
@keyframes dsh-collab-materialize { from { opacity:0; transform:translateY(12px) scale(.965); filter:blur(4px); } to { opacity:1; transform:none; filter:none; } }
@keyframes dsh-collab-empty-pulse { 50% { transform:scale(1.08); box-shadow:0 0 20px color-mix(in srgb,var(--collab-cyan) 22%,transparent); } }
@keyframes dsh-collab-event-in { from { opacity:0; transform:translateX(-8px); } to { opacity:1; transform:none; } }
@keyframes dsh-collab-event-pulse { 50% { box-shadow:0 0 18px color-mix(in srgb,var(--collab-accent) 90%,transparent); } }
@media (max-width:1100px) {
  .dsh-collab-content { grid-template-columns:1fr; overflow:auto; }
  .dsh-collab-stage,.dsh-collab-timeline { overflow:visible; border-right:0; }
  .dsh-collab-timeline { border-top:1px solid var(--dsw-alias-border-l2,#2c3240); }
}
@media (max-width:760px) {
  .dsh-collab-header { padding-inline:16px; }
  .dsh-collab-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .dsh-collab-stage { padding-inline:16px; }
  .dsh-collab-core-map { grid-template-columns:1fr 36px 1fr; grid-template-rows:auto 46px auto 46px auto; }
  .dsh-collab-core-registry { grid-column:1; grid-row:1; }
  .dsh-collab-core-discovery { grid-column:2; grid-row:1; }
  .dsh-collab-core-coordinator { grid-column:3; grid-row:1; }
  .dsh-collab-core-local { grid-column:3; grid-row:2; }
  .dsh-collab-core-workspace { grid-column:3; grid-row:3; }
  .dsh-collab-core-invocation { grid-column:3; grid-row:4; }
  .dsh-collab-core-bridge { grid-column:3; grid-row:5; }
  .dsh-collab-route-label { display:none; }
  .dsh-collab-agents { grid-template-columns:1fr; }
  .dsh-collab-agents::before { display:none; }
  .dsh-collab-agent-link { display:none; }
  .dsh-collab-chain-list { grid-auto-columns:minmax(210px,82%); }
}
@media (prefers-reduced-motion:reduce) {
  .dsh-collab-root * { animation-duration:.01ms !important; animation-iteration-count:1 !important; scroll-behavior:auto !important; }
}
`
