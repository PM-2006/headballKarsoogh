const $ = (id) => document.getElementById(id);
const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
let vocabulary = null;
let myStrategy = null;
let playbackHandle = null;

let gameConfig = {
  width: 1280,
  height: 720,
  ground_y: 610,
  goal_depth: 105,
  goal_height: 135,
  ball_radius: 22,
  player_width: 58,
  player_height: 72,
  match_time: 60,
};

function readInjectedConfig() {
  const el = $("game-config-data");
  if (el && el.textContent) {
    try {
      const cfg = JSON.parse(el.textContent);
      if (cfg && typeof cfg === "object") {
        Object.assign(gameConfig, cfg);
        updateCanvasDimensions();
      }
    } catch (e) {}
  }
}

function updateCanvasDimensions() {
  const canvas = $("game");
  if (canvas) {
    if (gameConfig.width) canvas.width = gameConfig.width;
    if (gameConfig.height) canvas.height = gameConfig.height;
  }
}
readInjectedConfig();

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
// Transient popup notification (auto-dismisses). Errors stay a bit longer.
function showToast(text,kind="err"){
  const wrap=$("toastWrap");if(!wrap)return;
  const clean=String(text||"").replace(/^\s*[❌✅ℹ️⚠️]+\s*/,"").trim();
  if(!clean)return;
  const el=document.createElement("div");
  el.className="toast "+(kind||"");
  const ico=kind==="ok"?"✅":kind==="err"?"❌":"ℹ️";
  el.innerHTML=`<span class="t-ico">${ico}</span><span class="t-text"></span><button class="t-close" aria-label="بستن">✕</button>`;
  el.querySelector(".t-text").textContent=clean;
  const remove=()=>{el.classList.add("hide");setTimeout(()=>el.remove(),260)};
  el.querySelector(".t-close").onclick=remove;
  wrap.appendChild(el);
  setTimeout(remove,kind==="err"?4000:2500);
}
// Errors/success now surface as toast popups instead of staying inline.
function setArenaMsg(text,kind=""){
  if(text&&(kind==="err"||kind==="ok")){showToast(text,kind);return;}
  const el=$("arenaMsg");if(!el)return;
  el.style.display="none";el.textContent="";
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
  markBotReady();
  refreshOpponentMenus();
}
function markBotReady(){
  $("deleteBot").disabled=false;
  const badge=$("botBadge");if(badge){badge.className="bot-badge on";badge.textContent="آماده ✓";}
}
function deleteBot(){
  if(!myStrategy){showToast("رباتی برای حذف وجود ندارد.","err");return;}
  myStrategy=null;
  $("jsonView").textContent="";
  const hb=$("humanBrain");hb.className="brain empty";
  hb.innerHTML='هنوز رباتی ساخته نشده.<br><span class="muted">از سمت راست یک استراتژی بساز تا مغز ربات اینجا نمایش داده شود.</span>';
  $("deleteBot").disabled=true;
  const badge=$("botBadge");if(badge){badge.className="bot-badge off";badge.textContent="ساخته نشده";}
  refreshOpponentMenus();
  showToast("ربات حذف شد.","ok");
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
    markBotReady();setFeedback("✅ مغز ربات ساخته شد.","ok");refreshOpponentMenus();
  }catch(err){setFeedback("❌ "+humanizeError(err),"err")}
}
function setFeedback(text,kind=""){
  if(kind==="err"||kind==="ok"){showToast(text,kind);return;}
  $("feedback").textContent=text;$("feedback").className="feedback "+kind;
}
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
  resetFx();
  const frameMs=1000/fps;
  let elapsed=0,last=null,lastScore=[frames[0].score[0],frames[0].score[1]];
  drawFrame(frames[0]);
  if(frames.length===1){playbackHandle=null;showWinner(frames[0]);return}
  function tick(now){
    // Advance by real time, but clamp each step. When the tab is hidden rAF
    // pauses; on return the first delta is huge, and without this clamp the
    // replay would jump straight to the final frame (players/ball "vanish").
    if(last!==null)elapsed+=Math.min(now-last,PLAYBACK_MAX_STEP_MS);
    last=now;
    const idx=Math.min(frames.length-1,Math.floor(elapsed/frameMs));
    const s=frames[idx].score;
    if(s[0]>lastScore[0])celebrateGoal(0);
    if(s[1]>lastScore[1])celebrateGoal(1);
    lastScore=[s[0],s[1]];
    drawFrame(frames[idx]);
    if(idx<frames.length-1)playbackHandle=requestAnimationFrame(tick);
    else{playbackHandle=null;showWinner(frames[idx]);}
  }
  playbackHandle=requestAnimationFrame(tick);
}
function resetFx(){
  const g=$("goalFx"),w=$("winFx");
  if(g)g.classList.remove("show","flash");
  if(w)w.classList.remove("show");
  document.querySelectorAll(".stage .confetti").forEach(c=>c.remove());
}
function spawnConfetti(container,colors,count){
  if(!container)return;
  for(let i=0;i<count;i++){
    const c=document.createElement("div");c.className="confetti";
    c.style.left=Math.random()*100+"%";
    c.style.background=colors[i%colors.length];
    c.style.animationDuration=(1.1+Math.random()*1.4)+"s";
    c.style.animationDelay=(Math.random()*0.3)+"s";
    c.style.width=(7+Math.random()*7)+"px";
    container.appendChild(c);
    setTimeout(()=>c.remove(),2900);
  }
}
function celebrateGoal(team){
  const fx=$("goalFx");if(!fx)return;
  const word=fx.querySelector(".goal-word");
  word.className="goal-word "+(team===0?"blue":"red");
  word.textContent=team===0?"گل آبی!":"گل قرمز!";
  fx.classList.remove("show","flash");void fx.offsetWidth; // restart the animation
  fx.classList.add("show","flash");
  spawnConfetti(document.querySelector(".stage"),
    team===0?["#39a4ff","#8fd0ff","#ffffff","#2fe0a6"]:["#ff5a78","#ffb3c0","#ffffff","#ffcb4d"],28);
  clearTimeout(celebrateGoal._t);
  celebrateGoal._t=setTimeout(()=>fx.classList.remove("show","flash"),1550);
}
function showWinner(frame){
  const win=$("winFx");if(!win)return;
  const b=frame.score[0],r=frame.score[1],card=win.querySelector(".win-card");
  let title,cls="";
  if(b>r){title="🔵 برنده: تیم آبی";cls="blue";}
  else if(r>b){title="🔴 برنده: تیم قرمز";cls="red";}
  else{title="🤝 مساوی شد!";}
  $("winTitle").textContent=title;
  $("winScore").textContent=`${b} : ${r}`;
  card.className="win-card"+(cls?" "+cls:"");
  win.classList.add("show");
  spawnConfetti(win,["#39a4ff","#ff5a78","#ffcb4d","#2fe0a6","#ffffff"],64);
}
const ACT_FA={
  MOVE_LEFT:{t:"حرکت به چپ",i:"⬅️"},MOVE_RIGHT:{t:"حرکت به راست",i:"➡️"},
  MOVE_TO_BALL:{t:"به سمت توپ",i:"🏃"},MOVE_TO_GOAL:{t:"دفاع از دروازه",i:"🛡️"},
  MOVE_TO_CENTER:{t:"به مرکز زمین",i:"🎯"},JUMP:{t:"پرش",i:"⬆️"},
  KICK_LOW:{t:"شوت زمینی",i:"⚡"},KICK_HIGH:{t:"شوت هوایی",i:"🚀"},
  KICK_CLEAR:{t:"دفع توپ",i:"🥊"},IDLE:{t:"منتظر",i:"⏸️"}
};
function actLabel(code){const a=ACT_FA[code];return a?`${a.i} ${a.t}`:(code||"—")}
function ruleLabel(rule){if(rule==null)return "—";if(rule==="default")return "پیش‌فرض";return "شماره "+rule}

function drawFrame(frame){
  const canvas=$("game"),ctx=canvas.getContext("2d");
  const W=gameConfig.width||canvas.width;
  const H=gameConfig.height||canvas.height;
  const G=gameConfig.ground_y||610;
  const GW=gameConfig.goal_depth||105;
  const GH=gameConfig.goal_height||135;
  const PW=gameConfig.player_width||58;
  const PH=gameConfig.player_height||72;
  const BR=gameConfig.ball_radius||22;

  drawStadium(ctx,W,H,G);
  drawPitch(ctx,W,H,G);
  drawGoal(ctx,false,W,G,GW,GH);drawGoal(ctx,true,W,G,GW,GH);
  drawPlayer(ctx,frame.players[0],"#2f9bff",PW,PH,G);drawPlayer(ctx,frame.players[1],"#ff5262",PW,PH,G);
  // Ball ground shadow shrinks as the ball rises.
  const hi=Math.max(0,Math.min(1,(G-frame.ball.y)/(G-150)));
  ctx.fillStyle=`rgba(0,0,0,${0.20*(1-0.55*hi)})`;
  ctx.beginPath();ctx.ellipse(frame.ball.x,G+4,BR*(1-0.35*hi),Math.max(2,6*(1-0.3*hi)),0,0,Math.PI*2);ctx.fill();
  drawBall(ctx,frame.ball.x,frame.ball.y,BR);
  $("score").textContent=`${frame.score[0]} : ${frame.score[1]}`;$("time").textContent=`${frame.time.toFixed(1)}s`;
  const d0=frame.debug?.[0]||{},d1=frame.debug?.[1]||{};
  $("blueRule").textContent=ruleLabel(d0.rule);$("blueAction").textContent=actLabel(d0.action);
  $("redRule").textContent=ruleLabel(d1.rule);$("redAction").textContent=actLabel(d1.action);
}
function drawStadium(ctx,W,H,G){
  // Sky with a soft overhead light wash.
  const sky=ctx.createLinearGradient(0,0,0,G);
  sky.addColorStop(0,"#7fbdf0");sky.addColorStop(.42,"#a8dcff");sky.addColorStop(1,"#e6f5ff");
  ctx.fillStyle=sky;ctx.fillRect(0,0,W,G);
  const wash=ctx.createRadialGradient(W/2,-50,30,W/2,-50,W*0.72);
  wash.addColorStop(0,"rgba(255,255,255,.42)");wash.addColorStop(1,"rgba(255,255,255,0)");
  ctx.fillStyle=wash;ctx.fillRect(0,0,W,G);
  // Drifting clouds.
  ctx.fillStyle="rgba(255,255,255,.55)";
  drawCloud(ctx,W*0.20,168,64);drawCloud(ctx,W*0.60,120,86);drawCloud(ctx,W*0.86,205,52);
  // Multi-tier stands.
  ctx.fillStyle="#132a4e";ctx.fillRect(0,0,W,46);
  ctx.fillStyle="#1a3868";ctx.fillRect(0,46,W,26);
  ctx.fillStyle="#22497f";ctx.fillRect(0,72,W,26);
  ctx.fillStyle="#0d2145";ctx.fillRect(0,0,W,9);              // roof
  ctx.fillStyle="rgba(9,20,40,.55)";                          // support columns
  for(let x=70;x<W;x+=150)ctx.fillRect(x,9,6,89);
  // Crowd speckles.
  const cols=["#ffd24d","#6bd4ff","#ff8098","#8affc0","#ffffff","#c9a8ff"];
  ctx.globalAlpha=.7;
  for(let i=0;i<W;i+=9){const y=14+((i*7)%78);ctx.fillStyle=cols[(i*11)%cols.length];ctx.fillRect(i,y,3,3);}
  ctx.globalAlpha=1;
  drawFloodlight(ctx,W*0.22);drawFloodlight(ctx,W*0.78);
  // Pitch-side advertising boards along the horizon.
  const ad=["#0e2a4a","#123a63","#0e2a4a","#173f66"];
  for(let x=0,k=0;x<W;x+=90,k++){ctx.fillStyle=ad[k%ad.length];ctx.fillRect(x,G-14,88,12);}
  ctx.fillStyle="rgba(120,200,255,.25)";ctx.fillRect(0,G-14,W,2);
}
function drawCloud(ctx,x,y,r){
  ctx.beginPath();
  ctx.arc(x,y,r*0.5,0,Math.PI*2);ctx.arc(x+r*0.5,y+4,r*0.38,0,Math.PI*2);
  ctx.arc(x-r*0.5,y+6,r*0.34,0,Math.PI*2);ctx.arc(x+r*0.14,y-r*0.2,r*0.4,0,Math.PI*2);
  ctx.fill();
}
function drawFloodlight(ctx,x){
  ctx.strokeStyle="#2a466f";ctx.lineWidth=5;ctx.beginPath();ctx.moveTo(x,98);ctx.lineTo(x,30);ctx.stroke();
  ctx.fillStyle="#20395e";ctx.beginPath();roundedRectPath(ctx,x-36,10,72,22,6);ctx.fill();
  const g=ctx.createRadialGradient(x,22,2,x,22,86);g.addColorStop(0,"rgba(255,255,215,.55)");g.addColorStop(1,"rgba(255,255,215,0)");
  ctx.fillStyle=g;ctx.beginPath();ctx.arc(x,22,86,0,Math.PI*2);ctx.fill();
  ctx.fillStyle="#fff8d8";for(let i=0;i<4;i++){ctx.beginPath();ctx.arc(x-25+i*17,21,4.2,0,Math.PI*2);ctx.fill();}
}
function drawPitch(ctx,W,H,G){
  const stripeW=W/14;
  for(let i=0;i<14;i++){ctx.fillStyle=i%2?"#34a657":"#41ba67";ctx.fillRect(i*stripeW,G,stripeW+1,H-G);}
  // Soft light pooled on the pitch + darker apron at the base.
  const pl=ctx.createRadialGradient(W/2,G+6,20,W/2,G+6,W*0.55);
  pl.addColorStop(0,"rgba(255,255,255,.16)");pl.addColorStop(1,"rgba(0,0,0,0)");
  ctx.fillStyle=pl;ctx.fillRect(0,G,W,H-G);
  ctx.fillStyle="rgba(0,0,0,.16)";ctx.fillRect(0,H-13,W,13);
  // Markings.
  ctx.strokeStyle="rgba(255,255,255,.9)";ctx.lineWidth=4;
  ctx.beginPath();ctx.moveTo(0,G+3);ctx.lineTo(W,G+3);ctx.stroke();               // touchline
  ctx.lineWidth=3;
  ctx.beginPath();ctx.moveTo(W/2,G+3);ctx.lineTo(W/2,H);ctx.stroke();             // halfway line
  ctx.fillStyle="rgba(255,255,255,.92)";ctx.beginPath();ctx.arc(W/2,G+(H-G)/2,4,0,Math.PI*2);ctx.fill();
  [150,W-150].forEach(x=>{ctx.beginPath();ctx.moveTo(x,G+4);ctx.lineTo(x,H);ctx.stroke();}); // penalty lines
  // Corner quarter-arcs at the goal lines.
  ctx.beginPath();ctx.arc(4,G+3,16,-Math.PI/2,0);ctx.stroke();
  ctx.beginPath();ctx.arc(W-4,G+3,16,Math.PI,Math.PI*1.5);ctx.stroke();
}
function drawGoal(ctx,right,W,G,GW,GH){
  const x0=right?W:0,dir=right?-1:1,inner=x0+dir*GW,topY=G-GH;
  const lo=Math.min(x0,inner),hi=Math.max(x0,inner);
  // Net
  ctx.save();ctx.beginPath();ctx.rect(lo,topY,GW,GH);ctx.clip();
  ctx.fillStyle="rgba(230,245,255,.10)";ctx.fillRect(lo,topY,GW,GH);
  ctx.strokeStyle="rgba(255,255,255,.30)";ctx.lineWidth=1;
  for(let gx=lo;gx<=hi;gx+=11){ctx.beginPath();ctx.moveTo(gx,topY);ctx.lineTo(gx,G);ctx.stroke();}
  for(let gy=topY;gy<=G;gy+=11){ctx.beginPath();ctx.moveTo(lo,gy);ctx.lineTo(hi,gy);ctx.stroke();}
  ctx.restore();
  // Back post (thin, at the field edge)
  ctx.strokeStyle="#dfeefc";ctx.lineWidth=4;ctx.lineCap="round";
  ctx.beginPath();ctx.moveTo(x0,topY);ctx.lineTo(x0,G);ctx.stroke();
  // Front post + crossbar (thick, with soft shadow)
  ctx.strokeStyle="#f6fbff";ctx.lineWidth=8;
  ctx.shadowColor="rgba(0,0,0,.28)";ctx.shadowBlur=6;ctx.shadowOffsetY=2;
  ctx.beginPath();ctx.moveTo(inner,G);ctx.lineTo(inner,topY);ctx.lineTo(x0,topY);ctx.stroke();
  ctx.shadowColor="transparent";ctx.shadowBlur=0;ctx.shadowOffsetY=0;
}
function drawBall(ctx,x,y,r){
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
function drawPentagon(ctx,cx,cy,rad,rot){
  ctx.beginPath();
  for(let i=0;i<5;i++){const a=rot+i*(2*Math.PI/5),px=cx+Math.cos(a)*rad,py=cy+Math.sin(a)*rad;i?ctx.lineTo(px,py):ctx.moveTo(px,py)}
  ctx.closePath();ctx.fill();
>>>>>>> 360ea4cbbef26ddf9cd4470a2e6ac5e80186572b
}
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
  const sx = w / 58;
  const sy = h / 72;

  // Shadow stays in world coordinates.
  ctx.fillStyle="rgba(0,0,0,.16)";
  ctx.beginPath();
  ctx.ellipse(cx,G+6,Math.max(8,34*sx),Math.max(3,8*sy),0,0,Math.PI*2);
  ctx.fill();

  ctx.save();
  ctx.translate(cx,0);
  ctx.scale(facing*sx,sy);
  ctx.translate(-cx,0);

  // Head spikes: the front/right spike is longer than the rear/left spike.
  drawHeadSpike(ctx,cx+2,p.y+15-27,-Math.PI/2,20,18,palette.headDark);
  drawHeadSpike(ctx,cx+2-23,p.y+15-18,-2.28,15,16,palette.headDark);
  drawHeadSpike(ctx,cx+2+24,p.y+15-18,-.86,18,17,palette.headDark);
  drawHeadSpike(ctx,cx+2-33,p.y+15+3,Math.PI,14,16,palette.headDark);
  drawHeadSpike(ctx,cx+2+35,p.y+15+1,0,22,18,palette.headDark);

  ctx.fillStyle=palette.head;
  ctx.beginPath();
  ctx.ellipse(cx+2,p.y+15,35,31,0,0,Math.PI*2);
  ctx.fill();

  ctx.fillStyle="rgba(255,255,255,.14)";
  ctx.beginPath();
  ctx.ellipse(cx+2-9,p.y+15-9,15,9,-.35,0,Math.PI*2);
  ctx.fill();

  // Face looks slightly toward the movement direction.
  ctx.fillStyle="#20232a";
  ctx.beginPath();
  ctx.ellipse(cx+2-7,p.y+15,4.3,9.3,0,0,Math.PI*2);
  ctx.ellipse(cx+2+12,p.y+15,4.8,9.8,0,0,Math.PI*2);
  ctx.fill();
  drawSmile(ctx,cx+2+3,p.y+15+13,20,7,"#20232a");

  ctx.fillStyle=palette.skin;
  ctx.beginPath();
  roundedRectPath(ctx,cx-5,p.y+39-4,12,9,4);
  ctx.fill();

  // Body leans a little forward.
  ctx.fillStyle=palette.jersey;
  ctx.beginPath();
  roundedRectPath(ctx,cx-15,p.y+39,34,20,8);
  ctx.fill();

  ctx.strokeStyle="#fff";
  ctx.lineWidth=2;
  ctx.beginPath();
  ctx.moveTo(cx-5,p.y+39+2);
  ctx.lineTo(cx+2,p.y+39+8);
  ctx.lineTo(cx+9,p.y+39+2);
  ctx.stroke();

  // Rear arm is lower; front arm reaches forward.
  drawLimb(ctx,cx-14,p.y+39+8,cx-24,p.y+39+17,5.5,palette.skin);
  drawLimb(ctx,cx+18,p.y+39+7,cx+31,p.y+39+10,5.5,palette.skin);
  ctx.fillStyle=palette.skin;
  ctx.beginPath();
  ctx.arc(cx-26,p.y+39+18,4,0,Math.PI*2);
  ctx.arc(cx+33,p.y+39+10,4,0,Math.PI*2);
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
  ctx.font=`bold ${Math.max(8, Math.round(10*Math.min(sx, sy)))}px Arial`;
  ctx.textAlign="center";
  ctx.textBaseline="middle";
  ctx.fillText(isRed?"7":"10",cx+2*sx,p.y+39+13*sy);
}
function batchRow(name,cls,wins,goals,total){
  const pct=total?Math.round(wins/total*100):0;
  return `<div class="bt-row"><span class="bt-name">${name}</span>`+
    `<span class="bt-bar"><span class="bt-fill ${cls}" style="width:${pct}%"></span></span>`+
    `<span class="bt-val">${wins} برد · ${goals} گل</span></div>`;
}
async function runBatch(){
  try{
    $("runBatch").disabled=true;
    const blue=$("blueSelect").value,red=$("redSelect").value;
    const result=await postJSON("api/batch/",{blue:strategyPayload(blue),red:strategyPayload(red),matches:Number($("batchCount").value),seed:Number($("seedInput").value)||1});
    const total=result.matches;
    $("batchResult").innerHTML=
      batchRow(labelFor(blue),"blue",result.blue_wins,result.blue_goals,total)+
      batchRow(labelFor(red),"red",result.red_wins,result.red_goals,total)+
      `<div class="bt-draws">🤝 ${result.draws} مساوی · میانگین گل ${result.blue_goals_per_match} به ${result.red_goals_per_match}</div>`;
  }
  catch(err){showToast(humanizeError(err),"err");$("batchResult").innerHTML=`<span class="batch-empty">هنوز آزمونی اجرا نشده.</span>`}finally{$("runBatch").disabled=false}
}
function labelFor(key){if(key==="mybot")return"My Bot";return vocabulary?.presets?.[key]||key}
function refreshOpponentMenus(){
  const currentBlue=$("blueSelect").value||"predictive",currentRed=$("redSelect").value||"adaptive",options=[];
  if(myStrategy)options.push(`<option value="mybot">My Bot</option>`);Object.entries(vocabulary.presets).forEach(([k,label])=>options.push(`<option value="${k}">${label}</option>`));$("blueSelect").innerHTML=options.join("");$("redSelect").innerHTML=options.join("");
  if([...$("blueSelect").options].some(o=>o.value===currentBlue))$("blueSelect").value=currentBlue;else $("blueSelect").value="predictive";
  if([...$("redSelect").options].some(o=>o.value===currentRed))$("redSelect").value=currentRed;else $("redSelect").value="adaptive";
}
async function init(){
  readInjectedConfig();
  vocabulary=await fetch("api/vocabulary/").then(r=>r.json());
  if(vocabulary&&vocabulary.config){
    Object.assign(gameConfig,vocabulary.config);
    updateCanvasDimensions();
  }
  refreshOpponentMenus();
  quickPreset("smart");
  $("builderTab").onclick=()=>switchView("builder");
  $("arenaTab").onclick=()=>switchView("arena");
  $("addRule").onclick=()=>addSimple();
  $("buildBot").onclick=buildBot;
  $("compileWithAI").onclick=compileWithAI;
  $("fillAiSample").onclick=()=>{$("strategyText").value="اگر بتونم شوت کنم شوت زمینی بزن. اگر حریف از من به توپ نزدیک‌تر بود برگرد دفاع. اگر من نزدیک‌تر بودم برو سمت توپ. اگر توپ بالای سرم بود بپر."};
  $("testBot").onclick=()=>{if(!myStrategy){showToast("اول یک ربات بساز، بعد آزمایشش کن.","err");return;}refreshOpponentMenus();$("blueSelect").value="mybot";$("redSelect").value="adaptive";switchView("arena");runMatch()};
  $("deleteBot").onclick=deleteBot;
  document.querySelectorAll("[data-quick]").forEach(btn=>btn.onclick=()=>quickPreset(btn.dataset.quick));
  $("playMatch").onclick=runMatch;
  $("runBatch").onclick=runBatch;
  $("winClose").onclick=()=>$("winFx").classList.remove("show");

  const W=gameConfig.width||1280;
  const H=gameConfig.height||720;
  const G=gameConfig.ground_y||610;
  const GW=gameConfig.goal_depth||105;
  const PW=gameConfig.player_width||58;
  const PH=gameConfig.player_height||72;
  const initP0x=GW+150;
  const initP1x=Math.max(initP0x+PW+10, W-GW-150-PW);
  const initPy=G-PH;
  const initBallY=Math.max(50, G-460);

  drawFrame({
    time: gameConfig.match_time||60,
    score: [0, 0],
    players: [{x: initP0x, y: initPy, face: 1}, {x: initP1x, y: initPy, face: -1}],
    ball: {x: W/2, y: initBallY},
    debug: [{}, {}]
  });
}
init();
