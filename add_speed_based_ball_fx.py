from pathlib import Path
import sys

ENGINE = Path("game/engine.py")
GAME_JS = Path("game/static/game/game.js")

for path in (ENGINE, GAME_JS):
    if not path.exists():
        print(f"ERROR: {path} not found. Run this script from the repository root.")
        sys.exit(1)

def read_file(path: Path):
    raw = path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline, raw

def write_file(path: Path, text: str, newline: str, raw: str, suffix: str):
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists():
        backup.write_text(raw, encoding="utf-8")
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    path.write_text(text, encoding="utf-8", newline="")
    print(f"Updated: {path}")
    print(f"Backup:  {backup}")

# ---------------------------------------------------------------------------
# engine.py — expose ball velocity in replay frames.
# ---------------------------------------------------------------------------
text, newline, raw = read_file(ENGINE)

old_ball_frame = '''        "ball": {
            "x": round(world.ball.x, 3),
            "y": round(world.ball.y, 3),
        },
'''
new_ball_frame = '''        "ball": {
            "x": round(world.ball.x, 3),
            "y": round(world.ball.y, 3),
            "vx": round(world.ball.vx, 3),
            "vy": round(world.ball.vy, 3),
        },
'''

if new_ball_frame not in text:
    if old_ball_frame not in text:
        print("ERROR: Could not find current replay ball block in game/engine.py")
        print("No files were changed.")
        sys.exit(2)
    text = text.replace(old_ball_frame, new_ball_frame, 1)

write_file(ENGINE, text, newline, raw, ".before-speed-fx.bak")

# ---------------------------------------------------------------------------
# game.js — speed-responsive trail, glow and stretch.
# ---------------------------------------------------------------------------
text, newline, raw = read_file(GAME_JS)

old_call = '''  drawBall(ctx,frame.ball.x,frame.ball.y,BR);
'''
new_call = '''  drawBall(ctx,frame.ball,BR);
'''
if new_call not in text:
    if old_call not in text:
        print("ERROR: Could not find drawBall() call in game/static/game/game.js")
        sys.exit(3)
    text = text.replace(old_call, new_call, 1)

old_draw_ball = '''function drawBall(ctx,x,y,r){
  ctx.save();ctx.translate(x,y);ctx.rotate((x/r)*0.15);
  const g=ctx.createRadialGradient(-r*.32,-r*.32,r*.2,0,0,r);
  g.addColorStop(0,"#ffffff");g.addColorStop(1,"#e0e8f0");
  ctx.fillStyle=g;ctx.beginPath();ctx.arc(0,0,r,0,Math.PI*2);ctx.fill();
  // Classic panel: center pentagon + seams to the rim.
  ctx.fillStyle="#1b2a3d";drawPentagon(ctx,0,0,r*0.42,-Math.PI/2);
  ctx.strokeStyle="#1b2a3d";ctx.lineWidth=2;
  for(let i=0;i<5;i++){const a=-Math.PI/2+i*(2*Math.PI/5);ctx.beginPath();ctx.moveTo(Math.cos(a)*r*0.42,Math.sin(a)*r*0.42);ctx.lineTo(Math.cos(a)*r*0.96,Math.sin(a)*r*0.96);ctx.stroke();}
  ctx.strokeStyle="#16233a";ctx.lineWidth=3;ctx.beginPath();ctx.arc(0,0,r,0,Math.PI*2);ctx.stroke();
  ctx.restore();
}
'''

new_draw_ball = '''function drawBall(ctx,ball,r){
  const x=ball.x,y=ball.y;
  const vx=isFiniteNumber(ball.vx)?ball.vx:0;
  const vy=isFiniteNumber(ball.vy)?ball.vy:0;
  const speed=Math.hypot(vx,vy);

  // Physics caps the ball around 1450 px/s. Start the visual effect only after
  // ~250 px/s so slow dribbles still look like a normal football.
  const speedFx=Math.max(0,Math.min(1,(speed-250)/1050));
  const angle=speed>1?Math.atan2(vy,vx):0;

  // ---- Speed trail -------------------------------------------------------
  // The canvas is fully redrawn each frame, so the trail is reconstructed from
  // the current velocity vector instead of leaving permanent pixels behind.
  if(speedFx>0.03){
    const ux=vx/speed,uy=vy/speed;
    const trailLength=18+speedFx*92;
    const pieces=6;

    ctx.save();
    ctx.globalCompositeOperation="source-over";
    for(let i=pieces;i>=1;i--){
      const t=i/pieces;
      const tx=x-ux*trailLength*t;
      const ty=y-uy*trailLength*t;
      const alpha=(1-t)*0.05+speedFx*(0.13*(1-t)+0.025);
      const size=r*(0.35+0.48*(1-t));

      ctx.fillStyle=`rgba(255,72,45,${alpha})`;
      ctx.beginPath();
      ctx.ellipse(
        tx,ty,
        size*(1+speedFx*.65),
        Math.max(2,size*.45),
        angle,
        0,Math.PI*2
      );
      ctx.fill();
    }
    ctx.restore();
  }

  // ---- Hot glow ----------------------------------------------------------
  if(speedFx>0.12){
    ctx.save();
    const glow=ctx.createRadialGradient(x,y,r*.72,x,y,r*(1.35+speedFx*.75));
    glow.addColorStop(0,"rgba(255,95,50,0)");
    glow.addColorStop(.60,`rgba(255,95,50,${0.05+speedFx*.08})`);
    glow.addColorStop(1,"rgba(255,45,35,0)");
    ctx.fillStyle=glow;
    ctx.beginPath();
    ctx.arc(x,y,r*(1.35+speedFx*.75),0,Math.PI*2);
    ctx.fill();
    ctx.restore();
  }

  // ---- Ball body ---------------------------------------------------------
  ctx.save();
  ctx.translate(x,y);
  ctx.rotate(angle);

  // Stretch in the direction of travel.
  const stretchX=1+speedFx*.20;
  const stretchY=1-speedFx*.09;
  ctx.scale(stretchX,stretchY);

  // Keep the panel rotation lively while the whole ball is oriented to travel.
  ctx.rotate((x/r)*0.15);

  const g=ctx.createRadialGradient(-r*.32,-r*.32,r*.2,0,0,r);
  g.addColorStop(0,"#ffffff");
  g.addColorStop(1,speedFx>.65?"#ffd8d0":"#e0e8f0");
  ctx.fillStyle=g;
  ctx.beginPath();
  ctx.arc(0,0,r,0,Math.PI*2);
  ctx.fill();

  // Classic panel: center pentagon + seams to the rim.
  ctx.fillStyle="#1b2a3d";
  drawPentagon(ctx,0,0,r*0.42,-Math.PI/2);
  ctx.strokeStyle="#1b2a3d";
  ctx.lineWidth=2;
  for(let i=0;i<5;i++){
    const a=-Math.PI/2+i*(2*Math.PI/5);
    ctx.beginPath();
    ctx.moveTo(Math.cos(a)*r*.42,Math.sin(a)*r*.42);
    ctx.lineTo(Math.cos(a)*r*.96,Math.sin(a)*r*.96);
    ctx.stroke();
  }

  // Border changes smoothly from navy to red/orange as speed rises.
  const hot=Math.round(70+185*speedFx);
  const green=Math.round(35+30*(1-speedFx));
  ctx.strokeStyle=speedFx>.08?`rgb(${hot},${green},35)`:"#16233a";
  ctx.lineWidth=3+speedFx*2.5;
  ctx.beginPath();
  ctx.arc(0,0,r,0,Math.PI*2);
  ctx.stroke();

  if(speedFx>.28){
    ctx.fillStyle=`rgba(255,255,255,${0.16+speedFx*.20})`;
    ctx.beginPath();
    ctx.ellipse(-r*.30,-r*.36,r*.25,r*.11,-.4,0,Math.PI*2);
    ctx.fill();
  }

  ctx.restore();
}
'''

if new_draw_ball not in text:
    if old_draw_ball not in text:
        print("ERROR: Could not find the current drawBall() implementation in game.js")
        sys.exit(4)
    text = text.replace(old_draw_ball, new_draw_ball, 1)

write_file(GAME_JS, text, newline, raw, ".before-speed-fx.bak")

print()
print("OK: speed-based ball visuals applied.")
print("No physics values were changed.")
print("Effects:")
print("  - slow ball: normal football")
print("  - medium speed: short red/orange trail + mild stretch")
print("  - fast shot: longer trail + red glow/border + stronger stretch")
