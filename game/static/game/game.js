const $ = (id) => document.getElementById(id);
const csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
let vocabulary = null;
let myStrategy = null;
let playbackHandle = null;

const simpleConditions = {
  ball_own:{label:"توپ در نیمه‌ی خودمان است",conditions:[{left:"ball_in_own_half",operator:"==",rightType:"value",right:true}]},
  ball_enemy:{label:"توپ در نیمه‌ی حریف است",conditions:[{left:"ball_in_enemy_half",operator:"==",rightType:"value",right:true}]},
  i_closer:{label:"من از حریف به توپ نزدیک‌ترم",conditions:[{left:"distance_to_ball",operator:"<",rightType:"sensor",right:"opponent_distance_to_ball"}]},
  opp_closer:{label:"حریف از من به توپ نزدیک‌تر است",conditions:[{left:"opponent_distance_to_ball",operator:"<",rightType:"sensor",right:"distance_to_ball"}]},
  can_kick:{label:"می‌توانم به توپ ضربه بزنم",conditions:[{left:"can_kick",operator:"==",rightType:"value",right:true}]},
  ball_above:{label:"توپ بالای سر من است",conditions:[{left:"ball_above_me",operator:"==",rightType:"value",right:true}]},
  incoming:{label:"توپ به سمت من می‌آید",conditions:[{left:"ball_moving_toward_me",operator:"==",rightType:"value",right:true}]},
  losing:{label:"از حریف عقب هستم",conditions:[{left:"score_difference",operator:"<",rightType:"value",right:0}]},
  winning:{label:"از حریف جلو هستم",conditions:[{left:"score_difference",operator:">",rightType:"value",right:0}]},
  last20:{label:"کمتر از ۲۰ ثانیه مانده",conditions:[{left:"remaining_time",operator:"<",rightType:"value",right:20}]}
};
const simpleActions = {
  MOVE_TO_BALL:"به سمت توپ برو",MOVE_TO_GOAL:"برگرد سمت دروازه",MOVE_TO_CENTER:"به مرکز زمین برو",
  JUMP:"بپر",KICK_LOW:"شوت زمینی بزن",KICK_HIGH:"شوت هوایی بزن",KICK_CLEAR:"توپ را محکم دفع کن",IDLE:"صبر کن"
};
let simpleRules = [];

function switchView(which){
  const builder=which==="builder";
  $("builderView").classList.toggle("active",builder);$("arenaView").classList.toggle("active",!builder);
  $("builderTab").classList.toggle("active",builder);$("arenaTab").classList.toggle("active",!builder);
}
function conditionOptions(selected){return Object.entries(simpleConditions).map(([k,v])=>`<option value="${k}" ${k===selected?"selected":""}>${v.label}</option>`).join("")}
function actionOptions(selected){return Object.entries(simpleActions).map(([k,v])=>`<option value="${k}" ${k===selected?"selected":""}>${v}</option>`).join("")}
function renderSimpleRules(){
  $("simpleRules").innerHTML=simpleRules.map((r,i)=>`<div class="simple-rule"><div class="simple-row"><b>تصمیم ${i+1}</b><span>اگر</span><select data-id="${r.id}" data-field="cond">${conditionOptions(r.cond)}</select><span>→</span><select data-id="${r.id}" data-field="action">${actionOptions(r.action)}</select><button data-up="${r.id}">↑</button><button data-down="${r.id}">↓</button><button data-remove="${r.id}">حذف</button></div></div>`).join("");
  document.querySelectorAll("[data-field]").forEach(el=>el.onchange=()=>{const row=simpleRules.find(r=>r.id===el.dataset.id);row[el.dataset.field]=el.value});
  document.querySelectorAll("[data-remove]").forEach(el=>el.onclick=()=>{simpleRules=simpleRules.filter(r=>r.id!==el.dataset.remove);renderSimpleRules()});
  document.querySelectorAll("[data-up]").forEach(el=>el.onclick=()=>moveRule(el.dataset.up,-1));
  document.querySelectorAll("[data-down]").forEach(el=>el.onclick=()=>moveRule(el.dataset.down,1));
}
function moveRule(id,dir){const i=simpleRules.findIndex(r=>r.id===id),j=i+dir;if(j<0||j>=simpleRules.length)return;[simpleRules[i],simpleRules[j]]=[simpleRules[j],simpleRules[i]];renderSimpleRules()}
function addSimple(cond="i_closer",action="MOVE_TO_BALL"){simpleRules.push({id:crypto.randomUUID(),cond,action});renderSimpleRules()}
function quickPreset(name){
  const id=()=>crypto.randomUUID();
  if(name==="attack")simpleRules=[{id:id(),cond:"can_kick",action:"KICK_LOW"},{id:id(),cond:"i_closer",action:"MOVE_TO_BALL"}];
  if(name==="defend")simpleRules=[{id:id(),cond:"ball_own",action:"MOVE_TO_GOAL"},{id:id(),cond:"can_kick",action:"KICK_CLEAR"}];
  if(name==="smart")simpleRules=[{id:id(),cond:"can_kick",action:"KICK_LOW"},{id:id(),cond:"opp_closer",action:"MOVE_TO_GOAL"},{id:id(),cond:"i_closer",action:"MOVE_TO_BALL"},{id:id(),cond:"ball_above",action:"JUMP"}];
  if(name==="late")simpleRules=[{id:id(),cond:"last20",action:"MOVE_TO_BALL"},{id:id(),cond:"losing",action:"MOVE_TO_BALL"},{id:id(),cond:"winning",action:"MOVE_TO_GOAL"},{id:id(),cond:"can_kick",action:"KICK_LOW"}];
  renderSimpleRules();
}
async function postJSON(url,payload){
  const response=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json","X-CSRFToken":csrf},body:JSON.stringify(payload)});
  const data=await response.json();if(!response.ok)throw new Error(data.error||"Request failed");return data;
}

const sensorFa = {
  my_x:"موقعیت من", opponent_x:"موقعیت حریف", ball_x:"موقعیت افقی توپ", ball_y:"ارتفاع توپ",
  ball_vx:"سرعت افقی توپ", ball_vy:"سرعت عمودی توپ", ball_speed:"سرعت توپ",
  distance_to_ball:"فاصله من تا توپ", opponent_distance_to_ball:"فاصله حریف تا توپ",
  distance_to_own_goal:"فاصله من تا دروازه خودی", distance_to_enemy_goal:"فاصله من تا دروازه حریف",
  ball_distance_to_own_goal:"فاصله توپ تا دروازه خودی", ball_distance_to_enemy_goal:"فاصله توپ تا دروازه حریف",
  predicted_ball_x:"موقعیت پیش‌بینی‌شده توپ", predicted_ball_y:"ارتفاع پیش‌بینی‌شده توپ",
  remaining_time:"زمان باقی‌مانده", my_score:"گل‌های من", opponent_score:"گل‌های حریف",
  score_difference:"اختلاف گل", can_kick:"امکان شوت", on_ground:"روی زمین بودن",
  ball_in_own_half:"توپ در نیمه خودی", ball_in_enemy_half:"توپ در نیمه حریف",
  ball_above_me:"توپ بالای سر من", ball_moving_toward_me:"توپ به سمت من"
};

function describeRight(cond){
  if(cond.rightType==="sensor") return sensorFa[cond.right] || cond.right;
  if(cond.right===true) return "بله";
  if(cond.right===false) return "خیر";
  return cond.right;
}
function describeCondition(cond){
  const opFa={"<":"کمتر از","<=":"کمتر یا مساوی",">":"بیشتر از",">=":"بیشتر یا مساوی","==":"برابر","!=":"نابرابر"};
  return `${sensorFa[cond.left] || cond.left} ${opFa[cond.operator] || cond.operator} ${describeRight(cond)}`;
}
function renderCompiledStrategy(strategy){
  myStrategy=strategy;
  $("jsonView").textContent=JSON.stringify(strategy,null,2);
  $("humanBrain").classList.remove("empty");
  $("humanBrain").innerHTML=[...strategy.rules]
    .sort((a,b)=>a.priority-b.priority)
    .map(r=>`<div class="brain-rule"><b>${r.priority}.</b> اگر ${r.conditions.map(describeCondition).join(" <b>و</b> ")}<br>→ <b>${simpleActions[r.action] || r.action}</b></div>`)
    .join("") + `<div class="brain-rule"><b>در غیر این صورت:</b> ${simpleActions[strategy.default_action] || strategy.default_action}</div>`;
  $("testBot").disabled=false;
  refreshOpponentMenus();
}
async function compileWithAI(){
  const text=$("strategyText").value.trim();
  if(!text){setFeedback("اول استراتژی را بنویس.","err");return}
  try{
    $("compileWithAI").disabled=true;
    $("compileWithAI").textContent="در حال فهمیدن استراتژی...";
    $("llmMeta").textContent="";
    const result=await postJSON("api/compile-strategy/",{text});
    const usage=result.usage || {};
    $("llmMeta").textContent=`مدل: ${result.model || "DeepSeek V4 Flash"} — Token: ${usage.total_tokens || 0} (ورودی ${usage.prompt_tokens || 0} / خروجی ${usage.completion_tokens || 0})`;
    if(!result.valid){
      const msg=(result.feedback || []).join(" ");
      setFeedback("❌ "+(msg || "استراتژی قابل تبدیل نبود."),"err");
      return;
    }
    renderCompiledStrategy(result.strategy);
    const extra=(result.feedback || []).join(" ");
    setFeedback("✅ استراتژی توسط مدل ساخته و توسط Validator بازی تأیید شد."+(extra ? " "+extra : ""),"ok");
  }catch(err){
    setFeedback("❌ "+err.message,"err");
  }finally{
    $("compileWithAI").disabled=false;
    $("compileWithAI").textContent="✨ تبدیل استراتژی";
  }
}

async function buildBot(){
  if(!simpleRules.length){setFeedback("حداقل یک تصمیم بساز.","err");return}
  const strategy={label:"My Bot",rules:simpleRules.map((r,i)=>({priority:i+1,conditions:simpleConditions[r.cond].conditions.map(c=>({...c})),action:r.action})),default_action:"IDLE"};
  try{
    await postJSON("api/validate/",{strategy});myStrategy=strategy;$("jsonView").textContent=JSON.stringify(strategy,null,2);$("humanBrain").classList.remove("empty");
    $("humanBrain").innerHTML=simpleRules.map((r,i)=>`<div class="brain-rule"><b>${i+1}.</b> اگر ${simpleConditions[r.cond].label}<br>→ <b>${simpleActions[r.action]}</b></div>`).join("")+`<div class="brain-rule"><b>در غیر این صورت:</b> صبر کن</div>`;
    $("testBot").disabled=false;setFeedback("✅ مغز ربات ساخته شد.","ok");refreshOpponentMenus();
  }catch(err){setFeedback("❌ "+err.message,"err")}
}
function setFeedback(text,kind=""){$("feedback").textContent=text;$("feedback").className="feedback "+kind}
function strategyPayload(selection){if(selection==="mybot"){if(!myStrategy)throw new Error("اول My Bot را بساز.");return{strategy:myStrategy}}return{preset:selection}}
async function runMatch(){
  if(playbackHandle)cancelAnimationFrame(playbackHandle);
  try{
    $("playMatch").disabled=true;const blue=$("blueSelect").value,red=$("redSelect").value;
    const result=await postJSON("api/simulate/",{blue:strategyPayload(blue),red:strategyPayload(red),seed:Number($("seedInput").value)||1});
    $("blueName").textContent=labelFor(blue);$("redName").textContent=labelFor(red);playFrames(result.frames,result.record_fps);
  }catch(err){alert(err.message)}finally{$("playMatch").disabled=false}
}
function playFrames(frames,fps){const start=performance.now(),frameMs=1000/fps;function tick(now){const idx=Math.min(frames.length-1,Math.floor((now-start)/frameMs));drawFrame(frames[idx]);if(idx<frames.length-1)playbackHandle=requestAnimationFrame(tick)}playbackHandle=requestAnimationFrame(tick)}
function drawFrame(frame){
  const canvas=$("game"),ctx=canvas.getContext("2d"),W=canvas.width,H=canvas.height,G=610,GW=105,GH=135;
  const grad=ctx.createLinearGradient(0,0,0,H);grad.addColorStop(0,"#74c9ff");grad.addColorStop(1,"#e5f6ff");ctx.fillStyle=grad;ctx.fillRect(0,0,W,H);
  ctx.fillStyle="#4dca69";ctx.fillRect(0,G,W,H-G);ctx.fillStyle="#38a957";ctx.fillRect(0,G+22,W,H-G-22);ctx.strokeStyle="rgba(255,255,255,.75)";ctx.lineWidth=4;ctx.beginPath();ctx.moveTo(W/2,G);ctx.lineTo(W/2,H);ctx.stroke();
  drawGoal(ctx,false,W,G,GW,GH);drawGoal(ctx,true,W,G,GW,GH);drawPlayer(ctx,frame.players[0],"#2f9bff",58,72,G);drawPlayer(ctx,frame.players[1],"#ff5262",58,72,G);
  ctx.fillStyle="#fff";ctx.beginPath();ctx.arc(frame.ball.x,frame.ball.y,22,0,Math.PI*2);ctx.fill();ctx.strokeStyle="#18263a";ctx.lineWidth=3;ctx.stroke();ctx.fillStyle="#18263a";ctx.beginPath();ctx.arc(frame.ball.x,frame.ball.y,7,0,Math.PI*2);ctx.fill();
  $("score").textContent=`${frame.score[0]} : ${frame.score[1]}`;$("time").textContent=`${frame.time.toFixed(1)}s`;const d0=frame.debug?.[0]||{},d1=frame.debug?.[1]||{};$("blueRule").textContent=d0.rule??"-";$("blueAction").textContent=d0.action??"IDLE";$("redRule").textContent=d1.rule??"-";$("redAction").textContent=d1.action??"IDLE";
}
function drawGoal(ctx,right,W,G,GW,GH){ctx.strokeStyle="#eff8ff";ctx.lineWidth=9;ctx.beginPath();if(!right){ctx.moveTo(0,G);ctx.lineTo(0,G-GH);ctx.lineTo(GW,G-GH)}else{ctx.moveTo(W,G);ctx.lineTo(W,G-GH);ctx.lineTo(W-GW,G-GH)}ctx.stroke()}
function drawPlayer(ctx,p,color,w,h,G){ctx.fillStyle="rgba(0,0,0,.16)";ctx.beginPath();ctx.ellipse(p.x+w/2,G+6,38,9,0,0,Math.PI*2);ctx.fill();ctx.fillStyle=color;ctx.beginPath();ctx.roundRect(p.x,p.y,w,h,16);ctx.fill();ctx.fillStyle="#101722";ctx.beginPath();ctx.roundRect(p.x+9,p.y+15,w-18,25,9);ctx.fill();ctx.fillStyle="#e5fbff";ctx.beginPath();ctx.arc(p.face>0?p.x+36:p.x+18,p.y+27,4,0,Math.PI*2);ctx.fill()}
async function runBatch(){
  try{$("runBatch").disabled=true;const blue=$("blueSelect").value,red=$("redSelect").value;const result=await postJSON("api/batch/",{blue:strategyPayload(blue),red:strategyPayload(red),matches:Number($("batchCount").value),seed:Number($("seedInput").value)||1});$("batchResult").innerHTML=`<b>${labelFor(blue)}</b>: ${result.blue_wins} برد — ${result.blue_goals} گل<br><b>${labelFor(red)}</b>: ${result.red_wins} برد — ${result.red_goals} گل<br>مساوی: ${result.draws}<br>میانگین گل: ${result.blue_goals_per_match} / ${result.red_goals_per_match}`}
  catch(err){$("batchResult").textContent=err.message}finally{$("runBatch").disabled=false}
}
function labelFor(key){if(key==="mybot")return"My Bot";return vocabulary?.presets?.[key]||key}
function refreshOpponentMenus(){
  const currentBlue=$("blueSelect").value||"predictive",currentRed=$("redSelect").value||"adaptive",options=[];
  if(myStrategy)options.push(`<option value="mybot">My Bot</option>`);Object.entries(vocabulary.presets).forEach(([k,label])=>options.push(`<option value="${k}">${label}</option>`));$("blueSelect").innerHTML=options.join("");$("redSelect").innerHTML=options.join("");
  if([...$("blueSelect").options].some(o=>o.value===currentBlue))$("blueSelect").value=currentBlue;else $("blueSelect").value="predictive";
  if([...$("redSelect").options].some(o=>o.value===currentRed))$("redSelect").value=currentRed;else $("redSelect").value="adaptive";
}
async function init(){
  vocabulary=await fetch("api/vocabulary/").then(r=>r.json());refreshOpponentMenus();quickPreset("smart");$("builderTab").onclick=()=>switchView("builder");$("arenaTab").onclick=()=>switchView("arena");$("addRule").onclick=()=>addSimple();$("buildBot").onclick=buildBot;$("compileWithAI").onclick=compileWithAI;$("fillAiSample").onclick=()=>{$("strategyText").value="اگر بتونم شوت کنم شوت زمینی بزن. اگر حریف از من به توپ نزدیک‌تر بود برگرد دفاع. اگر من نزدیک‌تر بودم برو سمت توپ. اگر توپ بالای سرم بود بپر."};$("testBot").onclick=()=>{refreshOpponentMenus();$("blueSelect").value="mybot";$("redSelect").value="adaptive";switchView("arena");runMatch()};document.querySelectorAll("[data-quick]").forEach(btn=>btn.onclick=()=>quickPreset(btn.dataset.quick));$("playMatch").onclick=runMatch;$("runBatch").onclick=runBatch;drawFrame({time:60,score:[0,0],players:[{x:255,y:538,face:1},{x:967,y:538,face:-1}],ball:{x:640,y:235},debug:[{},{}]});
}
init();
