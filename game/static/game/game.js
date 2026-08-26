const $ = (id) => document.getElementById(id);
const csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
let vocabulary = null;
let myStrategy = null;
let playbackHandle = null;

// Fixed conditions carry a ready `conditions` array. Parametric conditions
// carry a `param` whose number the student fills in ("…" in the label is
// replaced by that value). Both kinds can be combined with AND inside one rule.
const simpleConditions = {
  ball_own:{label:"توپ در نیمه‌ی خودمان است",conditions:[{left:"ball_in_own_half",operator:"==",rightType:"value",right:true}]},
  ball_enemy:{label:"توپ در نیمه‌ی حریف است",conditions:[{left:"ball_in_enemy_half",operator:"==",rightType:"value",right:true}]},
  i_closer:{label:"من از حریف به توپ نزدیک‌ترم",conditions:[{left:"distance_to_ball",operator:"<",rightType:"sensor",right:"opponent_distance_to_ball"}]},
  opp_closer:{label:"حریف از من به توپ نزدیک‌تر است",conditions:[{left:"opponent_distance_to_ball",operator:"<",rightType:"sensor",right:"distance_to_ball"}]},
  can_kick:{label:"می‌توانم به توپ ضربه بزنم",conditions:[{left:"can_kick",operator:"==",rightType:"value",right:true}]},
  ball_above:{label:"توپ بالای سر من است",conditions:[{left:"ball_above_me",operator:"==",rightType:"value",right:true}]},
  incoming:{label:"توپ به سمت من می‌آید",conditions:[{left:"ball_moving_toward_me",operator:"==",rightType:"value",right:true}]},
  on_ground:{label:"روی زمین هستم",conditions:[{left:"on_ground",operator:"==",rightType:"value",right:true}]},
  losing:{label:"از حریف عقب هستم",conditions:[{left:"score_difference",operator:"<",rightType:"value",right:0}]},
  winning:{label:"از حریف جلو هستم",conditions:[{left:"score_difference",operator:">",rightType:"value",right:0}]},
  time_left_lt:{label:"کمتر از … ثانیه مانده",param:{left:"remaining_time",operator:"<",unit:"ثانیه",default:30}},
  time_left_gt:{label:"بیشتر از … ثانیه مانده",param:{left:"remaining_time",operator:">",unit:"ثانیه",default:30}},
  ball_near:{label:"فاصله‌ام تا توپ کمتر از …",param:{left:"distance_to_ball",operator:"<",unit:"پیکسل",default:150}},
  lead_gt:{label:"اختلاف گلم بیشتر از …",param:{left:"score_difference",operator:">",unit:"گل",default:1}},
};
function newCond(key){const def=simpleConditions[key];return {key,value:def&&def.param?def.param.default:null}}
function mkRule(condKeys,action){return {id:crypto.randomUUID(),conds:condKeys.map(newCond),action}}
function ruleConditionsJSON(rule){
  return rule.conds.flatMap(ci=>{
    const def=simpleConditions[ci.key];
    if(def&&def.param)return [{left:def.param.left,operator:def.param.operator,rightType:"value",right:Number(ci.value)}];
    return def.conditions.map(c=>({...c}));
  });
}
function condInstanceLabel(ci){
  const def=simpleConditions[ci.key]||{};
  if(def.param)return def.label.replace("…",ci.value);
  return def.label||ci.key;
}
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
function condRowHTML(ruleId,ci,index,canRemove){
  const def=simpleConditions[ci.key]||{};
  const valInput=def.param?`<input class="cond-val" type="number" data-rule="${ruleId}" data-ci="${index}" data-field="value" value="${ci.value}">`:"";
  const unit=def.param?`<span class="muted">${def.param.unit}</span>`:"";
  const removeBtn=canRemove?`<button class="mini danger" data-rule="${ruleId}" data-ci="${index}" data-remove-cond="1" title="حذف این شرط">✕</button>`:"";
  return `<div class="cond-line"><select data-rule="${ruleId}" data-ci="${index}" data-field="cond">${conditionOptions(ci.key)}</select>${valInput}${unit}${removeBtn}</div>`;
}
function renderSimpleRules(){
  $("simpleRules").innerHTML=simpleRules.map((r,i)=>{
    const conds=r.conds.map((ci,ci_i)=>condRowHTML(r.id,ci,ci_i,r.conds.length>1)).join(`<div class="and-tag">و</div>`);
    return `<div class="simple-rule">
      <div class="rule-head"><b>تصمیم ${i+1}</b><span class="spacer"></span><button class="mini" data-up="${r.id}" title="بالا">↑</button><button class="mini" data-down="${r.id}" title="پایین">↓</button><button class="mini danger" data-remove="${r.id}">حذف</button></div>
      <div class="rule-body"><span class="kw">اگر</span><div class="conds">${conds}</div><button class="mini add-cond" data-add-cond="${r.id}" title="افزودن شرط با «و»">＋ و</button></div>
      <div class="rule-action"><span class="kw">آنگاه →</span><select data-rule="${r.id}" data-field="action">${actionOptions(r.action)}</select></div>
    </div>`;
  }).join("");
  bindRuleEvents();
}
function bindRuleEvents(){
  const Q=s=>document.querySelectorAll(s);
  Q("[data-field='cond']").forEach(el=>el.onchange=()=>{
    const r=simpleRules.find(x=>x.id===el.dataset.rule);const ci=r.conds[+el.dataset.ci];
    ci.key=el.value;const def=simpleConditions[ci.key];ci.value=def&&def.param?def.param.default:null;renderSimpleRules();
  });
  Q("[data-field='value']").forEach(el=>el.oninput=()=>{simpleRules.find(x=>x.id===el.dataset.rule).conds[+el.dataset.ci].value=el.value});
  Q("[data-field='action']").forEach(el=>el.onchange=()=>{simpleRules.find(x=>x.id===el.dataset.rule).action=el.value});
  Q("[data-add-cond]").forEach(el=>el.onclick=()=>{simpleRules.find(x=>x.id===el.dataset.addCond).conds.push(newCond("ball_own"));renderSimpleRules()});
  Q("[data-remove-cond]").forEach(el=>el.onclick=()=>{simpleRules.find(x=>x.id===el.dataset.rule).conds.splice(+el.dataset.ci,1);renderSimpleRules()});
  Q("[data-remove]").forEach(el=>el.onclick=()=>{simpleRules=simpleRules.filter(r=>r.id!==el.dataset.remove);renderSimpleRules()});
  Q("[data-up]").forEach(el=>el.onclick=()=>moveRule(el.dataset.up,-1));
  Q("[data-down]").forEach(el=>el.onclick=()=>moveRule(el.dataset.down,1));
}
function moveRule(id,dir){const i=simpleRules.findIndex(r=>r.id===id),j=i+dir;if(j<0||j>=simpleRules.length)return;[simpleRules[i],simpleRules[j]]=[simpleRules[j],simpleRules[i]];renderSimpleRules()}
function addSimple(){simpleRules.push(mkRule(["i_closer"],"MOVE_TO_BALL"));renderSimpleRules()}
function quickPreset(name){
  if(name==="attack")simpleRules=[mkRule(["can_kick"],"KICK_LOW"),mkRule(["i_closer"],"MOVE_TO_BALL")];
  if(name==="defend")simpleRules=[mkRule(["ball_own"],"MOVE_TO_GOAL"),mkRule(["can_kick"],"KICK_CLEAR")];
  if(name==="smart")simpleRules=[mkRule(["can_kick"],"KICK_LOW"),mkRule(["opp_closer"],"MOVE_TO_GOAL"),mkRule(["i_closer"],"MOVE_TO_BALL"),mkRule(["ball_above"],"JUMP")];
  if(name==="late")simpleRules=[mkRule(["time_left_lt","losing"],"MOVE_TO_BALL"),mkRule(["time_left_lt","winning"],"MOVE_TO_GOAL"),mkRule(["can_kick"],"KICK_LOW")];
  renderSimpleRules();
}
async function postJSON(url,payload){
  let response;
  try{
    response=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json","X-CSRFToken":csrf},body:JSON.stringify(payload)});
  }catch(e){throw new Error("ارتباط با سرور برقرار نشد. مطمئن شو سرور روشن است و اینترنت وصل است، بعد دوباره تلاش کن.");}
  let data;
  try{data=await response.json();}
  catch(e){throw new Error(response.ok?"پاسخ سرور قابل خواندن نبود. یک بار دیگر امتحان کن.":`سرور با خطا پاسخ داد (کد ${response.status}).`);}
  if(!response.ok)throw new Error(data.error||`خطای سرور (کد ${response.status}).`);
  return data;
}
// Turn any raw error into a short, clear Persian message a student can act on.
function humanizeError(err){
  const raw=((err&&err.message)||String(err||"")).trim();
  if(!raw)return "یک خطای ناشناخته رخ داد. دوباره تلاش کن.";
  if(/[؀-ۿ]/.test(raw))return raw; // already Persian — show as-is
  const map=[
    [/failed to fetch|networkerror|load failed|ارتباط/i,"ارتباط با سرور برقرار نشد. مطمئن شو سرور روشن است و دوباره تلاش کن."],
    [/csrf/i,"نشست تو منقضی شده. صفحه را تازه کن (F5) و دوباره امتحان کن."],
    [/preset.*strategy|strategy.*preset/i,"اول باید یک ربات بسازی یا یک نمونه انتخاب کنی."],
    [/timeout|timed out/i,"سرور دیر جواب داد. یک بار دیگر امتحان کن."],
    [/json/i,"پاسخ سرور قابل خواندن نبود. دوباره تلاش کن."],
  ];
  for(const [re,msg] of map)if(re.test(raw))return msg;
  return "مشکلی پیش آمد: "+raw;
}
function setArenaMsg(text,kind=""){const el=$("arenaMsg");if(!el)return;if(!text){el.style.display="none";el.textContent="";return}el.style.display="block";el.textContent=text;el.className="feedback "+kind;}

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
    setFeedback("❌ "+humanizeError(err),"err");
  }finally{
    $("compileWithAI").disabled=false;
    $("compileWithAI").textContent="✨ تبدیل استراتژی";
  }
}

async function buildBot(){
  if(!simpleRules.length){setFeedback("حداقل یک تصمیم بساز.","err");return}
  for(let i=0;i<simpleRules.length;i++){
    const r=simpleRules[i];
    if(!r.conds.length){setFeedback(`❌ تصمیم ${i+1} هیچ شرطی ندارد. حداقل یک «اگر» لازم است.`,"err");return}
    for(const ci of r.conds){
      const def=simpleConditions[ci.key];
      if(def&&def.param&&!Number.isFinite(Number(ci.value))){
        setFeedback(`❌ در تصمیم ${i+1} برای «${def.label.replace("…","___")}» یک عدد معتبر وارد کن.`,"err");return;
      }
    }
  }
  const strategy={label:"My Bot",rules:simpleRules.map((r,i)=>({priority:i+1,conditions:ruleConditionsJSON(r),action:r.action})),default_action:"IDLE"};
  try{
    await postJSON("api/validate/",{strategy});myStrategy=strategy;$("jsonView").textContent=JSON.stringify(strategy,null,2);$("humanBrain").classList.remove("empty");
    $("humanBrain").innerHTML=simpleRules.map((r,i)=>`<div class="brain-rule"><b>${i+1}.</b> اگر ${r.conds.map(condInstanceLabel).join(" <b>و</b> ")}<br>→ <b>${simpleActions[r.action]}</b></div>`).join("")+`<div class="brain-rule"><b>در غیر این صورت:</b> صبر کن</div>`;
    $("testBot").disabled=false;setFeedback("✅ مغز ربات ساخته شد.","ok");refreshOpponentMenus();
  }catch(err){setFeedback("❌ "+humanizeError(err),"err")}
}
function setFeedback(text,kind=""){$("feedback").textContent=text;$("feedback").className="feedback "+kind}
function strategyPayload(selection){if(selection==="mybot"){if(!myStrategy)throw new Error("اول My Bot را بساز.");return{strategy:myStrategy}}return{preset:selection}}
async function runMatch(){
  if(playbackHandle){cancelAnimationFrame(playbackHandle);playbackHandle=null}
  setArenaMsg("");
  try{
    $("playMatch").disabled=true;const blue=$("blueSelect").value,red=$("redSelect").value;
    const result=await postJSON("api/simulate/",{blue:strategyPayload(blue),red:strategyPayload(red),seed:Number($("seedInput").value)||1});
    $("blueName").textContent=labelFor(blue);$("redName").textContent=labelFor(red);playFrames(result.frames,result.record_fps);
  }catch(err){setArenaMsg("❌ "+humanizeError(err),"err")}finally{$("playMatch").disabled=false}
}
function isFiniteNumber(value){return typeof value==="number"&&Number.isFinite(value)}
function isValidReplayFrame(frame){
  if(!frame||typeof frame!=="object"||!isFiniteNumber(frame.time))return false;
  if(!Array.isArray(frame.score)||frame.score.length<2||!frame.score.slice(0,2).every(isFiniteNumber))return false;
  if(!Array.isArray(frame.players)||frame.players.length<2)return false;
  if(!frame.players.slice(0,2).every(player=>player&&isFiniteNumber(player.x)&&isFiniteNumber(player.y)&&isFiniteNumber(player.face)))return false;
  return Boolean(frame.ball&&isFiniteNumber(frame.ball.x)&&isFiniteNumber(frame.ball.y));
}
function validateReplay(frames,fps){
  if(!Array.isArray(frames)||frames.length===0)throw new Error("سرور هیچ فریمی برای پخش مسابقه برنگرداند.");
  if(!isFiniteNumber(fps)||fps<=0)throw new Error("سرعت پخش Replay از سرور معتبر نیست.");
  const invalidIndex=frames.findIndex(frame=>!isValidReplayFrame(frame));
  if(invalidIndex!==-1){
    console.error(`Invalid replay frame at index ${invalidIndex}`,frames[invalidIndex]);
    throw new Error(`فریم شماره ${invalidIndex} از سرور معتبر نیست.`);
  }
}
const PLAYBACK_MAX_STEP_MS=100; // ignore gaps bigger than this (tab switch / hitch)
function playFrames(frames,fps){
  validateReplay(frames,fps);
  const frameMs=1000/fps;
  let elapsed=0,last=null;
  drawFrame(frames[0]);
  if(frames.length===1){playbackHandle=null;return}
  function tick(now){
    // Advance by real time, but clamp each step. When the tab is hidden rAF
    // pauses; on return the first delta is huge, and without this clamp the
    // replay would jump straight to the final frame (players/ball "vanish").
    if(last!==null)elapsed+=Math.min(now-last,PLAYBACK_MAX_STEP_MS);
    last=now;
    const idx=Math.min(frames.length-1,Math.floor(elapsed/frameMs));
    drawFrame(frames[idx]);
    if(idx<frames.length-1)playbackHandle=requestAnimationFrame(tick);else playbackHandle=null;
  }
  playbackHandle=requestAnimationFrame(tick);
}
function drawFrame(frame){
  const canvas=$("game"),ctx=canvas.getContext("2d"),W=canvas.width,H=canvas.height,G=610,GW=105,GH=135;
  const grad=ctx.createLinearGradient(0,0,0,H);grad.addColorStop(0,"#74c9ff");grad.addColorStop(1,"#e5f6ff");ctx.fillStyle=grad;ctx.fillRect(0,0,W,H);
  ctx.fillStyle="#4dca69";ctx.fillRect(0,G,W,H-G);ctx.fillStyle="#38a957";ctx.fillRect(0,G+22,W,H-G-22);ctx.strokeStyle="rgba(255,255,255,.75)";ctx.lineWidth=4;ctx.beginPath();ctx.moveTo(W/2,G);ctx.lineTo(W/2,H);ctx.stroke();
  drawGoal(ctx,false,W,G,GW,GH);drawGoal(ctx,true,W,G,GW,GH);drawPlayer(ctx,frame.players[0],"#2f9bff",58,72,G);drawPlayer(ctx,frame.players[1],"#ff5262",58,72,G);
  ctx.fillStyle="#fff";ctx.beginPath();ctx.arc(frame.ball.x,frame.ball.y,22,0,Math.PI*2);ctx.fill();ctx.strokeStyle="#18263a";ctx.lineWidth=3;ctx.stroke();ctx.fillStyle="#18263a";ctx.beginPath();ctx.arc(frame.ball.x,frame.ball.y,7,0,Math.PI*2);ctx.fill();
  $("score").textContent=`${frame.score[0]} : ${frame.score[1]}`;$("time").textContent=`${frame.time.toFixed(1)}s`;const d0=frame.debug?.[0]||{},d1=frame.debug?.[1]||{};$("blueRule").textContent=d0.rule??"-";$("blueAction").textContent=d0.action??"IDLE";$("redRule").textContent=d1.rule??"-";$("redAction").textContent=d1.action??"IDLE";
}
function drawGoal(ctx,right,W,G,GW,GH){ctx.strokeStyle="#eff8ff";ctx.lineWidth=9;ctx.beginPath();if(!right){ctx.moveTo(0,G);ctx.lineTo(0,G-GH);ctx.lineTo(GW,G-GH)}else{ctx.moveTo(W,G);ctx.lineTo(W,G-GH);ctx.lineTo(W-GW,G-GH)}ctx.stroke()}
function roundedRectPath(ctx,x,y,w,h,r){
  const radius=Math.max(0,Math.min(r,w/2,h/2));
  if(typeof ctx.roundRect==="function"){ctx.roundRect(x,y,w,h,radius);return}
  ctx.moveTo(x+radius,y);ctx.lineTo(x+w-radius,y);ctx.quadraticCurveTo(x+w,y,x+w,y+radius);
  ctx.lineTo(x+w,y+h-radius);ctx.quadraticCurveTo(x+w,y+h,x+w-radius,y+h);
  ctx.lineTo(x+radius,y+h);ctx.quadraticCurveTo(x,y+h,x,y+h-radius);
  ctx.lineTo(x,y+radius);ctx.quadraticCurveTo(x,y,x+radius,y);ctx.closePath();
}
function drawHeadSpike(ctx,x,y,angle,length,width,color){
  ctx.save();
  ctx.translate(x,y);
  ctx.rotate(angle);
  ctx.fillStyle=color;
  ctx.beginPath();
  ctx.moveTo(0,-width/2);
  ctx.quadraticCurveTo(length*.36,-width*.58,length,0);
  ctx.quadraticCurveTo(length*.36,width*.58,0,width/2);
  ctx.quadraticCurveTo(length*.10,width*.22,0,0);
  ctx.quadraticCurveTo(length*.10,-width*.22,0,-width/2);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}
function drawSmile(ctx,x,y,width,height,color){
  ctx.strokeStyle=color;
  ctx.lineWidth=3;
  ctx.lineCap="round";
  ctx.beginPath();
  ctx.moveTo(x-width/2,y);
  ctx.quadraticCurveTo(x,y+height,x+width/2,y);
  ctx.stroke();
}
function drawLimb(ctx,x1,y1,x2,y2,thickness,color){
  ctx.strokeStyle=color;
  ctx.lineWidth=thickness;
  ctx.lineCap="round";
  ctx.beginPath();
  ctx.moveTo(x1,y1);
  ctx.lineTo(x2,y2);
  ctx.stroke();
}
function drawPlayer(ctx,p,color,w,h,G){
  const isRed=color.toLowerCase()==="#ff5262";
  const palette=isRed
    ?{head:"#ff5353",headDark:"#df2f35",jersey:"#d91f2a",boots:"#d52b34",skin:"#ff5353"}
    :{head:"#55a8ff",headDark:"#2d82df",jersey:"#126bd8",boots:"#2475d6",skin:"#55a8ff"};

  const cx=p.x+w/2;
  const facing=p.face>=0?1:-1;
  const headCx=cx+2;
  const headCy=p.y+15;
  const headRx=35;
  const headRy=31;
  const bodyTop=p.y+39;

  // Shadow stays in world coordinates.
  ctx.fillStyle="rgba(0,0,0,.16)";
  ctx.beginPath();
  ctx.ellipse(cx,G+6,34,8,0,0,Math.PI*2);
  ctx.fill();

  // Draw one right-facing mascot and mirror the whole character when face < 0.
  // The pose is intentionally asymmetric, so direction is obvious at a glance.
  ctx.save();
  ctx.translate(cx,0);
  ctx.scale(facing,1);
  ctx.translate(-cx,0);

  // Head spikes: the front/right spike is longer than the rear/left spike.
  drawHeadSpike(ctx,headCx,headCy-27,-Math.PI/2,20,18,palette.headDark);
  drawHeadSpike(ctx,headCx-23,headCy-18,-2.28,15,16,palette.headDark);
  drawHeadSpike(ctx,headCx+24,headCy-18,-.86,18,17,palette.headDark);
  drawHeadSpike(ctx,headCx-33,headCy+3,Math.PI,14,16,palette.headDark);
  drawHeadSpike(ctx,headCx+35,headCy+1,0,22,18,palette.headDark);

  ctx.fillStyle=palette.head;
  ctx.beginPath();
  ctx.ellipse(headCx,headCy,headRx,headRy,0,0,Math.PI*2);
  ctx.fill();

  ctx.fillStyle="rgba(255,255,255,.14)";
  ctx.beginPath();
  ctx.ellipse(headCx-9,headCy-9,15,9,-.35,0,Math.PI*2);
  ctx.fill();

  // Face looks slightly toward the movement direction.
  ctx.fillStyle="#20232a";
  ctx.beginPath();
  ctx.ellipse(headCx-7,headCy,4.3,9.3,0,0,Math.PI*2);
  ctx.ellipse(headCx+12,headCy,4.8,9.8,0,0,Math.PI*2);
  ctx.fill();
  drawSmile(ctx,headCx+3,headCy+13,20,7,"#20232a");

  ctx.fillStyle=palette.skin;
  ctx.beginPath();
  roundedRectPath(ctx,cx-5,bodyTop-4,12,9,4);
  ctx.fill();

  // Body leans a little forward.
  ctx.fillStyle=palette.jersey;
  ctx.beginPath();
  roundedRectPath(ctx,cx-15,bodyTop,34,20,8);
  ctx.fill();

  ctx.strokeStyle="#fff";
  ctx.lineWidth=2;
  ctx.beginPath();
  ctx.moveTo(cx-5,bodyTop+2);
  ctx.lineTo(cx+2,bodyTop+8);
  ctx.lineTo(cx+9,bodyTop+2);
  ctx.stroke();

  // Rear arm is lower; front arm reaches forward.
  drawLimb(ctx,cx-14,bodyTop+8,cx-24,bodyTop+17,5.5,palette.skin);
  drawLimb(ctx,cx+18,bodyTop+7,cx+31,bodyTop+10,5.5,palette.skin);
  ctx.fillStyle=palette.skin;
  ctx.beginPath();
  ctx.arc(cx-26,bodyTop+18,4,0,Math.PI*2);
  ctx.arc(cx+33,bodyTop+10,4,0,Math.PI*2);
  ctx.fill();

  ctx.fillStyle="#fff";
  ctx.beginPath();
  roundedRectPath(ctx,cx-13,p.y+57,30,8,4);
  ctx.fill();

  // Running stance: front leg reaches forward, rear leg trails back.
  drawLimb(ctx,cx-5,p.y+63,cx-11,p.y+68,5.5,palette.skin);
  drawLimb(ctx,cx+9,p.y+63,cx+15,p.y+67,5.5,palette.skin);

  ctx.fillStyle=palette.boots;
  ctx.beginPath();
  roundedRectPath(ctx,cx-19,p.y+66,15,6,3);
  roundedRectPath(ctx,cx+9,p.y+65,17,6,3);
  ctx.fill();

  ctx.restore();

  // Draw the shirt number after restoring so text never appears mirrored.
  ctx.fillStyle="#fff";
  ctx.font="bold 10px Arial";
  ctx.textAlign="center";
  ctx.textBaseline="middle";
  ctx.fillText(isRed?"7":"10",cx+2,bodyTop+13);
}
async function runBatch(){
  try{$("runBatch").disabled=true;const blue=$("blueSelect").value,red=$("redSelect").value;const result=await postJSON("api/batch/",{blue:strategyPayload(blue),red:strategyPayload(red),matches:Number($("batchCount").value),seed:Number($("seedInput").value)||1});$("batchResult").innerHTML=`<b>${labelFor(blue)}</b>: ${result.blue_wins} برد — ${result.blue_goals} گل<br><b>${labelFor(red)}</b>: ${result.red_wins} برد — ${result.red_goals} گل<br>مساوی: ${result.draws}<br>میانگین گل: ${result.blue_goals_per_match} / ${result.red_goals_per_match}`}
  catch(err){$("batchResult").textContent="❌ "+humanizeError(err)}finally{$("runBatch").disabled=false}
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
