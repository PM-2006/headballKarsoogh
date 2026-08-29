from pathlib import Path
import sys

path = Path("game/static/game/game.js")
if not path.exists():
    print(f"ERROR: {path} not found. Run this from the repository root.")
    sys.exit(1)

raw = path.read_text(encoding="utf-8")
newline = "\r\n" if "\r\n" in raw else "\n"
text = raw.replace("\r\n", "\n")

old = '  drawGoal(ctx,false,W,G,GW,GH);drawGoal(ctx,true,W,G,GW,GH);drawPlayer(ctx,frame.players[0],"#2f9bff",58,72,G);drawPlayer(ctx,frame.players[1],"#ff5262",58,72,G);\n  ctx.fillStyle="#fff";ctx.beginPath();ctx.arc(frame.ball.x,frame.ball.y,22,0,Math.PI*2);ctx.fill();ctx.strokeStyle="#18263a";ctx.lineWidth=3;ctx.stroke();ctx.fillStyle="#18263a";ctx.beginPath();ctx.arc(frame.ball.x,frame.ball.y,7,0,Math.PI*2);ctx.fill();\n  $("score").textContent=`${frame.score[0]} : ${frame.score[1]}`;$("time").textContent=`${frame.time.toFixed(1)}s`;const d0=frame.debug?.[0]||{},d1=frame.debug?.[1]||{};$("blueRule").textContent=d0.rule??"-";$("blueAction").textContent=d0.action??"IDLE";$("redRule").textContent=d1.rule??"-";$("redAction").textContent=d1.action??"IDLE";\n}\nfunction drawGoal(ctx,right,W,G,GW,GH){ctx.strokeStyle="#eff8ff";ctx.lineWidth=9;ctx.beginPath();if(!right){ctx.moveTo(0,G);ctx.lineTo(0,G-GH);ctx.lineTo(GW,G-GH)}else{ctx.moveTo(W,G);ctx.lineTo(W,G-GH);ctx.lineTo(W-GW,G-GH)}ctx.stroke()}\n'

new = '  drawGoal(ctx,false,W,G,GW,GH,"#2f9bff");\n  drawGoal(ctx,true,W,G,GW,GH,"#ff5262");\n  drawPlayer(ctx,frame.players[0],"#2f9bff",58,72,G);\n  drawPlayer(ctx,frame.players[1],"#ff5262",58,72,G);\n  drawBall(ctx,frame.ball,22);\n  $("score").textContent=`${frame.score[0]} : ${frame.score[1]}`;$("time").textContent=`${frame.time.toFixed(1)}s`;const d0=frame.debug?.[0]||{},d1=frame.debug?.[1]||{};$("blueRule").textContent=d0.rule??"-";$("blueAction").textContent=d0.action??"IDLE";$("redRule").textContent=d1.rule??"-";$("redAction").textContent=d1.action??"IDLE";\n}\nfunction drawGoal(ctx,right,W,G,GW,GH,accent){\n  const backX=right?W:0;\n  const frontX=right?W-GW:GW;\n  const left=Math.min(backX,frontX);\n  const top=G-GH;\n\n  ctx.save();\n\n  const shade=ctx.createLinearGradient(left,top,left,G);\n  shade.addColorStop(0,"rgba(255,255,255,.10)");\n  shade.addColorStop(1,"rgba(20,35,55,.10)");\n  ctx.fillStyle=shade;\n  ctx.fillRect(left,top,GW,GH);\n\n  ctx.strokeStyle="rgba(255,255,255,.58)";\n  ctx.lineWidth=1.5;\n  const cols=6,rows=7;\n  for(let i=1;i<cols;i++){\n    const x=left+GW*i/cols;\n    ctx.beginPath();\n    ctx.moveTo(x,top+3);\n    ctx.lineTo(x,G-2);\n    ctx.stroke();\n  }\n  for(let j=1;j<rows;j++){\n    const y=top+GH*j/rows;\n    ctx.beginPath();\n    ctx.moveTo(left+2,y);\n    ctx.lineTo(left+GW-2,y);\n    ctx.stroke();\n  }\n\n  ctx.fillStyle=accent+"22";\n  ctx.fillRect(left,top,GW,GH);\n\n  ctx.strokeStyle="#f7fbff";\n  ctx.lineWidth=10;\n  ctx.lineCap="round";\n  ctx.lineJoin="round";\n  ctx.beginPath();\n  ctx.moveTo(backX,G-1);\n  ctx.lineTo(backX,top);\n  ctx.lineTo(frontX,top);\n  ctx.stroke();\n\n  ctx.strokeStyle="rgba(33,52,72,.22)";\n  ctx.lineWidth=3;\n  ctx.beginPath();\n  ctx.moveTo(backX+(right?-3:3),G-2);\n  ctx.lineTo(backX+(right?-3:3),top+3);\n  ctx.lineTo(frontX,top+3);\n  ctx.stroke();\n\n  ctx.fillStyle="#fff";\n  ctx.beginPath();\n  ctx.arc(frontX,top,7,0,Math.PI*2);\n  ctx.fill();\n  ctx.strokeStyle=accent;\n  ctx.lineWidth=2;\n  ctx.stroke();\n\n  ctx.fillStyle=accent;\n  ctx.beginPath();\n  roundedRectPath(ctx,right?backX-18:backX,G-8,18,8,4);\n  ctx.fill();\n\n  ctx.restore();\n}\nfunction drawBall(ctx,ball,r){\n  const x=ball.x,y=ball.y;\n\n  ctx.save();\n\n  const shadowY=Math.min(608,y+34);\n  const heightFactor=Math.max(.28,1-Math.max(0,588-y)/520);\n  ctx.fillStyle=`rgba(0,0,0,${.18*heightFactor})`;\n  ctx.beginPath();\n  ctx.ellipse(x,shadowY,18*heightFactor,5*heightFactor,0,0,Math.PI*2);\n  ctx.fill();\n\n  ctx.translate(x,y);\n  ctx.rotate((ball.x+ball.y*.35)*.025);\n\n  const grad=ctx.createRadialGradient(-7,-9,3,0,0,r);\n  grad.addColorStop(0,"#ffffff");\n  grad.addColorStop(.68,"#f5f7fa");\n  grad.addColorStop(1,"#cfd6df");\n  ctx.fillStyle=grad;\n  ctx.beginPath();\n  ctx.arc(0,0,r,0,Math.PI*2);\n  ctx.fill();\n  ctx.strokeStyle="#26313e";\n  ctx.lineWidth=2.4;\n  ctx.stroke();\n\n  function polygon(cx,cy,radius,sides,rotation){\n    ctx.beginPath();\n    for(let i=0;i<sides;i++){\n      const a=rotation+i*Math.PI*2/sides;\n      const px=cx+Math.cos(a)*radius;\n      const py=cy+Math.sin(a)*radius;\n      if(i===0)ctx.moveTo(px,py);else ctx.lineTo(px,py);\n    }\n    ctx.closePath();\n  }\n\n  ctx.fillStyle="#202a35";\n  polygon(0,1,6.5,5,-Math.PI/2);\n  ctx.fill();\n\n  const patches=[];\n  for(let i=0;i<5;i++){\n    const a=-Math.PI/2+i*Math.PI*2/5;\n    patches.push({x:Math.cos(a)*14.2,y:Math.sin(a)*14.2,a});\n  }\n\n  ctx.strokeStyle="#596572";\n  ctx.lineWidth=1.2;\n  for(const p of patches){\n    ctx.beginPath();\n    ctx.moveTo(Math.cos(p.a)*5.8,1+Math.sin(p.a)*5.8);\n    ctx.lineTo(p.x*.76,p.y*.76);\n    ctx.stroke();\n  }\n\n  ctx.fillStyle="#26313c";\n  for(const p of patches){\n    polygon(p.x,p.y,4.6,5,p.a+Math.PI/2);\n    ctx.fill();\n  }\n\n  ctx.fillStyle="rgba(255,255,255,.60)";\n  ctx.beginPath();\n  ctx.ellipse(-7,-9,5,3,-.45,0,Math.PI*2);\n  ctx.fill();\n\n  ctx.restore();\n}\n'

if "function drawBall(ctx,ball,r)" in text:
    print("Already applied: drawBall() is present.")
    sys.exit(0)

count = text.count(old)
if count != 1:
    print(f"ERROR: Expected exactly one matching UI block, found {count}.")
    print("No file was changed.")
    sys.exit(2)

backup = path.with_suffix(path.suffix + ".bak")
backup.write_text(raw, encoding="utf-8")

updated = text.replace(old, new, 1)
if newline == "\r\n":
    updated = updated.replace("\n", "\r\n")

path.write_text(updated, encoding="utf-8", newline="")
print("OK: goal + ball UI applied.")
print(f"Backup: {backup}")
