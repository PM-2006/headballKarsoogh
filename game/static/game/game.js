const $ = (id) => document.getElementById(id);
const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
let vocabulary = null;
let myStrategy = null;
let playbackHandle = null;
let savedStrategies = [];
let publicStrategies = [];
let editingStrategyId = null;

let gameConfig = {
  width: 1500,
  height: 860,
  ground_y: 730,
  goal_depth: 122,
  goal_height: 205,
  ball_radius: 23,
  player_width: 66,
  player_height: 84,
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
    if (gameConfig.width && gameConfig.height) {
      // Keep the on-screen box matching the world so nothing is stretched,
      // even after an admin changes width/height in the panel.
      canvas.style.aspectRatio = (gameConfig.width / gameConfig.height).toFixed(4);
    }
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

const VIEW_NAMES=["builder","arena","panel"];
function switchView(which){
  VIEW_NAMES.forEach(v=>{
    const view=$(v+"View"),tab=$(v+"Tab");
    if(view)view.classList.toggle("active",v===which);
    if(tab)tab.classList.toggle("active",v===which);
  });
  if(which==="panel")ensurePanelLoaded();
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
async function postJSON(url,payload,method="POST"){
  let response;
  try{
    const opts={method,headers:{"Content-Type":"application/json","X-CSRFToken":csrf}};
    if(method!=="GET"&&method!=="HEAD") opts.body=JSON.stringify(payload||{});
    response=await fetch(url,opts);
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
  if($("saveBotBtn")) $("saveBotBtn").disabled=false;
  const badge=$("botBadge");if(badge){badge.className="bot-badge on";badge.textContent="آماده ✓";}
}
function deleteBot(){
  if(!myStrategy){showToast("رباتی برای حذف وجود ندارد.","err");return;}
  myStrategy=null;
  $("jsonView").textContent="";
  const hb=$("humanBrain");hb.className="brain empty";
  hb.innerHTML='هنوز رباتی ساخته نشده.<br><span class="muted">از سمت راست یک استراتژی بساز تا مغز ربات اینجا نمایش داده شود.</span>';
  $("deleteBot").disabled=true;
  if($("saveBotBtn")) $("saveBotBtn").disabled=true;
  if($("botNameInput")) $("botNameInput").value="";
  cancelEdit();
  const badge=$("botBadge");if(badge){badge.className="bot-badge off";badge.textContent="ساخته نشده";}
  refreshOpponentMenus();
  showToast("صفحه ربات پاکسازی شد.","ok");
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
function pitchHorizon(H){ return Math.round(H*0.36); }   // top edge of the pitch bowl
function drawStadium(ctx,W,H,G){
  const hz=pitchHorizon(H), dome=26;
  // Bright daytime sky above the bowl.
  const sky=ctx.createLinearGradient(0,0,0,hz);
  sky.addColorStop(0,"#3fb0ff");sky.addColorStop(1,"#c4ecff");
  ctx.fillStyle=sky;ctx.fillRect(0,0,W,hz);
  ctx.fillStyle="rgba(255,255,255,.8)";
  drawCloud(ctx,W*0.17,52,50);drawCloud(ctx,W*0.83,38,60);
  // Curved stadium tiers (shallow dome gives the bowl depth).
  const bands=[[0,0.44,"#28324c"],[0.44,0.72,"#313f5e"],[0.72,1,"#3a4d72"]];
  for(const b of bands){
    const ya=hz*b[0], yb=hz*b[1];
    ctx.fillStyle=b[2];
    ctx.beginPath();
    ctx.moveTo(0,ya);ctx.quadraticCurveTo(W/2,ya+dome,W,ya);
    ctx.lineTo(W,yb);ctx.quadraticCurveTo(W/2,yb+dome,0,yb);
    ctx.closePath();ctx.fill();
  }
  // Roof lip.
  ctx.fillStyle="#1c2438";ctx.beginPath();
  ctx.moveTo(0,0);ctx.quadraticCurveTo(W/2,dome,W,0);
  ctx.lineTo(W,10);ctx.quadraticCurveTo(W/2,10+dome,0,10);ctx.closePath();ctx.fill();
  // Crowd speckles bowing with the dome.
  const cols=["#ffd24d","#7fe0ff","#ff90a4","#9dffc4","#ffffff","#c9a8ff","#ffb066","#8fb4ff"];
  ctx.globalAlpha=.9;
  for(let x=6;x<W;x+=9){
    const bow=dome*Math.sin(Math.PI*x/W);
    for(let y=16;y<hz-24;y+=9){ctx.fillStyle=cols[((x*5+y*3)>>1)%cols.length];ctx.fillRect(x,y+bow,3.4,3.4);}
  }
  ctx.globalAlpha=1;
  drawFloodlight(ctx,W*0.20,hz);drawFloodlight(ctx,W*0.80,hz);
  // Barrier + colourful advert boards at the pitch edge (follow the dome).
  ctx.fillStyle="#10203a";ctx.beginPath();
  ctx.moveTo(0,hz-20);ctx.quadraticCurveTo(W/2,hz-20+34,W,hz-20);
  ctx.lineTo(W,hz);ctx.quadraticCurveTo(W/2,hz+34,0,hz);ctx.closePath();ctx.fill();
  const ad=["#12e0c0","#ffd23d","#ff5c8a","#4db4ff","#a06bff"];
  for(let i=0,x=0;x<W;x+=96,i++){
    const bow=34*Math.sin(Math.PI*(x+48)/W);
    ctx.fillStyle=ad[i%ad.length];ctx.fillRect(x,hz-16+bow,92,11);
  }
}
function drawCloud(ctx,x,y,r){
  ctx.beginPath();
  ctx.arc(x,y,r*0.5,0,Math.PI*2);ctx.arc(x+r*0.5,y+4,r*0.38,0,Math.PI*2);
  ctx.arc(x-r*0.5,y+6,r*0.34,0,Math.PI*2);ctx.arc(x+r*0.14,y-r*0.2,r*0.4,0,Math.PI*2);
  ctx.fill();
}
function drawFloodlight(ctx,x,hz){
  ctx.strokeStyle="#4a5a78";ctx.lineWidth=5;ctx.lineCap="round";
  ctx.beginPath();ctx.moveTo(x,hz*0.52);ctx.lineTo(x,26);ctx.stroke();
  ctx.fillStyle="#39496a";ctx.beginPath();roundedRectPath(ctx,x-34,10,68,20,6);ctx.fill();
  const g=ctx.createRadialGradient(x,20,2,x,20,70);
  g.addColorStop(0,"rgba(255,252,220,.5)");g.addColorStop(1,"rgba(255,252,220,0)");
  ctx.fillStyle=g;ctx.beginPath();ctx.arc(x,20,70,0,Math.PI*2);ctx.fill();
  ctx.fillStyle="#fffbe0";for(let i=0;i<4;i++){ctx.beginPath();ctx.arc(x-23+i*15,19,4,0,Math.PI*2);ctx.fill();}
}
function drawPitch(ctx,W,H,G){
  const hz=pitchHorizon(H), dome=34;
  ctx.save();
  // Clip to the domed pitch shape so the far edge curves (2.5D).
  ctx.beginPath();
  ctx.moveTo(0,hz);ctx.quadraticCurveTo(W/2,hz+dome,W,hz);
  ctx.lineTo(W,H);ctx.lineTo(0,H);ctx.closePath();ctx.clip();
  // Bright cartoon green, sunlit near the horizon.
  const gr=ctx.createLinearGradient(0,hz,0,H);
  gr.addColorStop(0,"#54c877");gr.addColorStop(.55,"#41b365");gr.addColorStop(1,"#2c9350");
  ctx.fillStyle=gr;ctx.fillRect(0,hz-6,W,H-hz+6);
  // Vertical mowing stripes.
  const stripes=14, sw=W/stripes;
  for(let i=1;i<stripes;i+=2){ctx.fillStyle="rgba(255,255,255,.055)";ctx.fillRect(i*sw,hz-6,sw+1,H-hz+6);}
  // Sunlight pool.
  const pool=ctx.createRadialGradient(W/2,hz+30,40,W/2,hz+30,W*0.62);
  pool.addColorStop(0,"rgba(255,255,255,.16)");pool.addColorStop(1,"rgba(0,0,0,0)");
  ctx.fillStyle=pool;ctx.fillRect(0,hz-6,W,H-hz+6);
  ctx.fillStyle="rgba(0,0,0,.12)";ctx.fillRect(0,H-16,W,16);   // foreground apron
  ctx.restore();
  // Markings anchored to the ground play-plane.
  ctx.strokeStyle="rgba(255,255,255,.9)";ctx.lineCap="round";
  ctx.lineWidth=4;
  ctx.beginPath();ctx.moveTo(6,hz+3);ctx.quadraticCurveTo(W/2,hz+dome+3,W-6,hz+3);ctx.stroke(); // far touchline
  ctx.lineWidth=3;
  ctx.beginPath();ctx.moveTo(W/2,hz+dome);ctx.lineTo(W/2,H);ctx.stroke();                        // halfway line
  ctx.beginPath();ctx.ellipse(W/2,G-24,116,42,0,0,Math.PI*2);ctx.stroke();                       // centre circle
  ctx.fillStyle="rgba(255,255,255,.92)";ctx.beginPath();ctx.ellipse(W/2,G-24,5,2.4,0,0,Math.PI*2);ctx.fill();
  ctx.beginPath();ctx.ellipse(0,G-20,150,66,0,-Math.PI*0.42,Math.PI*0.42);ctx.stroke();          // penalty arcs
  ctx.beginPath();ctx.ellipse(W,G-20,150,66,0,Math.PI*0.58,Math.PI*1.42);ctx.stroke();
}
function drawHexNet(ctx,x,y,w,h,r){
  ctx.strokeStyle="rgba(255,255,255,.26)";ctx.lineWidth=1;
  const dx=r*1.5, dy=r*Math.sqrt(3);
  for(let col=0,cx=x-r; cx<=x+w+r; col++,cx+=dx){
    const off=(col%2)?dy/2:0;
    for(let cy=y+off-r; cy<=y+h+r; cy+=dy){
      ctx.beginPath();
      for(let k=0;k<6;k++){const a=Math.PI/180*(60*k+30);const px=cx+r*Math.cos(a),py=cy+r*Math.sin(a);k?ctx.lineTo(px,py):ctx.moveTo(px,py);}
      ctx.closePath();ctx.stroke();
    }
  }
}
function goalTube(ctx,x1,y1,x2,y2,w,vertical){
  const g=vertical
    ? ctx.createLinearGradient(x1-w/2,0,x1+w/2,0)
    : ctx.createLinearGradient(0,y1-w/2,0,y1+w/2);
  g.addColorStop(0,"#b3cae2");g.addColorStop(vertical?.44:.0,"#ffffff");g.addColorStop(1,"#9db6d1");
  ctx.save();
  ctx.strokeStyle=g;ctx.lineWidth=w;ctx.lineCap="round";
  ctx.shadowColor="rgba(0,0,0,.28)";ctx.shadowBlur=7;ctx.shadowOffsetY=3;
  ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();
  ctx.restore();
}
function drawGoal(ctx,right,W,G,GW,GH){
  const x0=right?W:0,dir=right?-1:1,inner=x0+dir*GW,topY=G-GH;
  const lo=Math.min(x0,inner);
  const pw=Math.max(9,GW*0.09);
  // Ground shadow at the mouth.
  ctx.fillStyle="rgba(0,0,0,.15)";
  ctx.beginPath();ctx.ellipse(inner+dir*GW*0.25,G+5,GW*0.6,8,0,0,Math.PI*2);ctx.fill();
  // Net recess — hexagonal mesh, darkening toward the back wall for depth (2.5D).
  ctx.save();ctx.beginPath();ctx.rect(lo,topY,GW,GH);ctx.clip();
  const depth=ctx.createLinearGradient(inner,0,x0,0);
  depth.addColorStop(0,"rgba(205,228,250,.16)");depth.addColorStop(1,"rgba(58,84,120,.46)");
  ctx.fillStyle=depth;ctx.fillRect(lo,topY,GW,GH);
  drawHexNet(ctx,lo,topY,GW,GH,Math.max(8,GH*0.05));
  // shade the very back edge
  const back=ctx.createLinearGradient(inner,0,x0,0);
  back.addColorStop(0,"rgba(0,0,0,0)");back.addColorStop(1,"rgba(0,0,0,.28)");
  ctx.fillStyle=back;ctx.fillRect(lo,topY,GW,GH);
  ctx.restore();
  // Frame: back post (thin) -> crossbar into the wall -> prominent front post.
  goalTube(ctx,x0,topY,x0,G,pw*0.62,true);      // back post at the wall
  goalTube(ctx,inner,topY,x0,topY,pw*0.9,false); // crossbar receding to the wall
  goalTube(ctx,inner,topY,inner,G,pw,true);      // front post (nearest the field)
  // Rounded joint cap where front post meets the crossbar.
  ctx.fillStyle="#ffffff";ctx.beginPath();ctx.arc(inner,topY,pw*0.56,0,Math.PI*2);ctx.fill();
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
  // Scale the sprite around the player's own top-left (cx,p.y) so enlarging
  // players keeps the drawing aligned with the physics hitbox (head at
  // p.y+head_center_y, feet at p.y+player_height). Scaling from the canvas
  // origin instead would sink the sprite ~sy*p.y pixels below its hitbox.
  ctx.translate(cx,p.y);
  ctx.scale(facing*sx,sy);
  ctx.translate(-cx,-p.y);

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
  ctx.fillText(isRed?"7":"10",cx+2*sx,p.y+(39+11)*sy);
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
function escapeHtml(str){
  if(!str) return "";
  return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");
}

function labelFor(key){
  if(key==="mybot") return myStrategy?.label || "My Bot";
  if(key.startsWith("saved_")){
    const id=Number(key.replace("saved_",""));
    const b=savedStrategies.find(s=>s.id===id);
    return b ? b.name : "My Bot";
  }
  if(key.startsWith("pub_")){
    const id=Number(key.replace("pub_",""));
    const b=publicStrategies.find(s=>s.id===id);
    return b ? `🏆 ${b.name}` : key;
  }
  return vocabulary?.presets?.[key]||key;
}

function strategyPayload(selection){
  if(selection==="mybot"){
    if(!myStrategy) throw new Error("اول My Bot را بساز.");
    return {strategy:myStrategy};
  }
  if(selection.startsWith("saved_")){
    return {strategy_id:Number(selection.replace("saved_",""))};
  }
  if(selection.startsWith("pub_")){
    return {strategy_id:Number(selection.replace("pub_",""))};
  }
  return {preset:selection};
}

function refreshOpponentMenus(){
  const currentBlue=$("blueSelect").value||"predictive",currentRed=$("redSelect").value||"adaptive";

  let blueOpts="", redOpts="";

  // 1. My Bots group
  let myGroup="";
  if(myStrategy){
    myGroup+=`<option value="mybot">🤖 My Bot (پیش‌نویس جاری)</option>`;
  }
  savedStrategies.forEach(s=>{
    myGroup+=`<option value="saved_${s.id}">👤 ${escapeHtml(s.name)}</option>`;
  });
  if(myGroup){
    blueOpts+=`<optgroup label="🤖 ربات‌های من">${myGroup}</optgroup>`;
    redOpts+=`<optgroup label="🤖 ربات‌های من">${myGroup}</optgroup>`;
  }

  // 2. Admin & Public bots group
  if(publicStrategies.length){
    let pubGroup="";
    publicStrategies.forEach(s=>{
      pubGroup+=`<option value="pub_${s.id}">🏆 ${escapeHtml(s.name)} (${escapeHtml(s.author||"ادمین")})</option>`;
    });
    blueOpts+=`<optgroup label="🏆 ربات‌های رسمی و مدیران">${pubGroup}</optgroup>`;
    redOpts+=`<optgroup label="🏆 ربات‌های رسمی و مدیران">${pubGroup}</optgroup>`;
  }

  // 3. Presets group
  if(vocabulary?.presets){
    let preGroup="";
    Object.entries(vocabulary.presets).forEach(([k,label])=>{
      preGroup+=`<option value="${k}">⚡ ${label}</option>`;
    });
    blueOpts+=`<optgroup label="⚡ الگوهای پیش‌فرض">${preGroup}</optgroup>`;
    redOpts+=`<optgroup label="⚡ الگوهای پیش‌فرض">${preGroup}</optgroup>`;
  }

  $("blueSelect").innerHTML=blueOpts;
  $("redSelect").innerHTML=redOpts;

  if([...$("blueSelect").options].some(o=>o.value===currentBlue)) $("blueSelect").value=currentBlue;
  else $("blueSelect").value=(myStrategy ? "mybot" : (savedStrategies[0] ? "saved_"+savedStrategies[0].id : "predictive"));

  if([...$("redSelect").options].some(o=>o.value===currentRed)) $("redSelect").value=currentRed;
  else $("redSelect").value=(publicStrategies[0] ? "pub_"+publicStrategies[0].id : "adaptive");
}

async function loadStrategiesFromServer(){
  try{
    const res=await fetch("api/strategies/").then(r=>r.json());
    savedStrategies=res.my_strategies || [];
    publicStrategies=res.public_strategies || [];
    renderBotGalleries();
    refreshOpponentMenus();
  }catch(e){
    console.error("Failed loading saved strategies",e);
  }
}

function renderBotGalleries(){
  const myWrap=$("myBotsList");
  if(myWrap){
    if(!savedStrategies.length){
      myWrap.innerHTML='<div class="empty-list">هنوز رباتی ذخیره نکرده‌ای. از بالای صفحه یک ربات بساز و ذخیره‌اش کن!</div>';
    }else{
      myWrap.innerHTML=savedStrategies.map(b=>`
        <div class="bot-card-item">
          <div class="bot-card-head">
            <div class="bot-card-name">🤖 ${escapeHtml(b.name)}</div>
            <span class="bot-badge on">${(b.strategy?.rules||[]).length} تصمیم</span>
          </div>
          <div class="bot-card-meta">
            <span>📅 آخرین ویرایش: ${b.updated_at}</span>
          </div>
          <div class="bot-card-actions">
            <button class="primary" onclick="loadBotIntoBuilder(${b.id})">📂 ویرایش و بارگذاری</button>
            <button class="success" onclick="challengeBotInArena(${b.id},true)">⚽ مسابقه در آرنا</button>
            <button class="btn-danger" onclick="deleteSavedBot(${b.id},'${escapeHtml(b.name)}')">🗑 حذف</button>
          </div>
        </div>
      `).join("");
    }
  }

  const pubWrap=$("publicBotsList");
  if(pubWrap){
    if(!publicStrategies.length){
      pubWrap.innerHTML='<div class="empty-list">هنوز ربات رسمی‌ای توسط مدیران منتشر نشده است.</div>';
    }else{
      pubWrap.innerHTML=publicStrategies.map(b=>`
        <div class="bot-card-item">
          <div class="bot-card-head">
            <div class="bot-card-name">🏆 ${escapeHtml(b.name)}</div>
            <span class="badge-public">${b.author ? `👤 مدیر: ${escapeHtml(b.author)}` : "عمومی"}</span>
          </div>
          <div class="bot-card-meta">
            <span>⚡ تعداد تصمیم‌ها: ${(b.strategy?.rules||[]).length}</span>
            <span>📅 تاریخ انتشار: ${b.created_at}</span>
          </div>
          <div class="bot-card-actions">
            <button onclick="loadBotIntoBuilder(${b.id})">👁 مشاهده مغز ربات</button>
            <button class="primary" onclick="challengeBotInArena(${b.id},false)">⚔️ مسابقه با این ربات</button>
          </div>
        </div>
      `).join("");
    }
  }
}

async function saveCurrentBot(){
  if(!myStrategy){
    showToast("ابتدا یک استراتژی بسازید تا بتوانید آن را ذخیره کنید.","err");
    return;
  }
  const name=($("botNameInput").value || "").trim() || myStrategy.label || "My Bot";
  const ai_prompt=($("strategyText").value || "").trim();
  const btn=$("saveBotBtn");
  try{
    btn.disabled=true;
    btn.textContent="در حال ذخیره...";
    if(editingStrategyId){
      await postJSON(`api/strategies/${editingStrategyId}/`,{
        name,
        strategy:myStrategy,
        ai_prompt
      },"POST");
      showToast(`ربات «${name}» با موفقیت به‌روزرسانی شد.`,"ok");
    }else{
      const res=await postJSON("api/strategies/",{
        name,
        strategy:myStrategy,
        ai_prompt
      },"POST");
      if(res.strategy&&res.strategy.id){
        editingStrategyId=res.strategy.id;
        $("editingInfo").style.display="flex";
        $("editingBotName").textContent=name;
      }
      showToast(`ربات «${name}» با موفقیت در سرور ذخیره شد.`,"ok");
    }
    await loadStrategiesFromServer();
  }catch(err){
    showToast("❌ "+humanizeError(err),"err");
  }finally{
    btn.disabled=false;
    btn.textContent=editingStrategyId ? "💾 ذخیره تغییرات" : "💾 ذخیره ربات";
  }
}

function cancelEdit(){
  editingStrategyId=null;
  if($("editingInfo")) $("editingInfo").style.display="none";
  if($("saveBotBtn")) $("saveBotBtn").textContent="💾 ذخیره ربات";
}

function loadBotIntoBuilder(id){
  const bot=savedStrategies.find(b=>b.id===id) || publicStrategies.find(b=>b.id===id);
  if(!bot){
    showToast("ربات مورد نظر یافت نشد.","err");
    return;
  }
  if(bot.is_owner){
    editingStrategyId=bot.id;
    if($("editingInfo")){
      $("editingInfo").style.display="flex";
      $("editingBotName").textContent=bot.name;
    }
    if($("saveBotBtn")) $("saveBotBtn").textContent="💾 ذخیره تغییرات";
  }else{
    cancelEdit();
  }
  if($("botNameInput")) $("botNameInput").value=bot.name;
  if(bot.ai_prompt && $("strategyText")){
    $("strategyText").value=bot.ai_prompt;
  }
  renderCompiledStrategy(bot.strategy);
  switchView("builder");
  showToast(`ربات «${bot.name}» در ویرایشگر بارگذاری شد.`,"ok");
}

async function deleteSavedBot(id,name){
  if(!confirm(`آیا از حذف ربات «${name}» اطمینان دارید؟`)) return;
  try{
    await postJSON(`api/strategies/${id}/`,{},"DELETE");
    if(editingStrategyId===id){
      cancelEdit();
    }
    showToast(`ربات «${name}» با موفقیت حذف شد.`,"ok");
    await loadStrategiesFromServer();
  }catch(err){
    showToast("❌ "+humanizeError(err),"err");
  }
}

function challengeBotInArena(id,asBlue=true){
  const bot=savedStrategies.find(b=>b.id===id) || publicStrategies.find(b=>b.id===id);
  if(!bot) return;
  refreshOpponentMenus();
  if(asBlue){
    $("blueSelect").value="saved_"+bot.id;
    $("redSelect").value="adaptive";
  }else{
    $("redSelect").value="pub_"+bot.id;
    $("blueSelect").value=(myStrategy ? "mybot" : (savedStrategies[0] ? "saved_"+savedStrategies[0].id : "smart"));
  }
  switchView("arena");
  runMatch();
}

function drawIdleFrame(){
  const W=gameConfig.width||1280,G=gameConfig.ground_y||610;
  const GW=gameConfig.goal_depth||122,PW=gameConfig.player_width||66,PH=gameConfig.player_height||84;
  const p0=GW+150, p1=Math.max(p0+PW+10, W-GW-150-PW);
  drawFrame({time:gameConfig.match_time||60,score:[0,0],
    players:[{x:p0,y:G-PH,face:1},{x:p1,y:G-PH,face:-1}],
    ball:{x:W/2,y:Math.max(50,G-460)},debug:[{},{}]});
}

// ---------- Admin game-config panel (superuser only) ----------
let panelLoaded=false;
function setPanelStatus(t){const el=$("panelStatus");if(el)el.textContent=t;}
async function ensurePanelLoaded(){
  if(panelLoaded||!$("panelGroups"))return;
  try{
    const data=await fetch("api/game-config/").then(r=>r.json());
    if(data.error){setPanelStatus("❌ "+data.error);return;}
    renderPanel(data.groups);panelLoaded=true;
    setPanelStatus("مقادیر فعلی بارگذاری شد. تغییر بده، «آزمایش» کن، بعد «ذخیره».");
  }catch(e){setPanelStatus("❌ خطا در بارگذاری تنظیمات.");}
}
function renderPanel(groups){
  const host=$("panelGroups");if(!host)return;
  host.innerHTML=groups.map(g=>`
    <details class="panel-group" open>
      <summary>${g.title} <span class="pg-count">${g.fields.length}</span></summary>
      <div class="panel-fields">
        ${g.fields.map(f=>{
          const step=f.step||(f.int?1:0.01);
          return `<div class="pfield" data-key="${f.key}">
            <div class="pf-top">
              <label title="${f.key}">${f.label}</label>
              <input class="pf-num" type="number" min="${f.min}" max="${f.max}" step="${step}" value="${f.value}">
            </div>
            <input class="pf-range" type="range" min="${f.min}" max="${f.max}" step="${step}" value="${f.value}">
            <div class="pf-scale"><span>${f.min}</span><span>${f.max}</span></div>
          </div>`;
        }).join("")}
      </div>
    </details>`).join("");
  host.querySelectorAll(".pfield").forEach(row=>{
    const rng=row.querySelector(".pf-range"),num=row.querySelector(".pf-num");
    rng.oninput=()=>{num.value=rng.value;};
    num.oninput=()=>{rng.value=num.value;};
  });
}
function collectPanelValues(){
  const out={};
  document.querySelectorAll("#panelGroups .pfield").forEach(row=>{
    const v=Number(row.querySelector(".pf-num").value);
    if(Number.isFinite(v))out[row.dataset.key]=v;
  });
  return out;
}
function applyClientConfig(map){
  Object.assign(gameConfig,map);
  updateCanvasDimensions();
  drawIdleFrame();
}
async function panelSave(){
  try{
    setPanelStatus("در حال ذخیره…");
    const res=await postJSON("api/game-config/",{values:collectPanelValues()});
    if(res.config)applyClientConfig(res.config);
    if(res.groups)renderPanel(res.groups);
    showToast("✅ تنظیمات برای همه ذخیره شد.","ok");
    setPanelStatus("ذخیره شد ✓ — از این پس همهٔ مسابقه‌ها با این مقادیر اجرا می‌شوند.");
  }catch(err){showToast("❌ "+humanizeError(err),"err");setPanelStatus("خطا در ذخیره.");}
}
async function panelReset(){
  if(!confirm("همهٔ تنظیمات بازی به مقادیر پیش‌فرض بازگردد؟"))return;
  try{
    const res=await postJSON("api/game-config/reset/",{});
    if(res.config)applyClientConfig(res.config);
    if(res.groups)renderPanel(res.groups);
    showToast("↩ به پیش‌فرض بازگشت.","ok");
    setPanelStatus("به مقادیر پیش‌فرض بازگشت.");
  }catch(err){showToast("❌ "+humanizeError(err),"err");}
}
async function panelTest(){
  const overrides=collectPanelValues();
  applyClientConfig(overrides);
  const presets=(vocabulary&&vocabulary.presets)||{};
  const keys=Object.keys(presets);
  const blue=keys[0]||"smart", red=keys[1]||keys[0]||"adaptive";
  try{
    setPanelStatus("در حال شبیه‌سازی آزمایشی…");
    const seed=Number(($("seedInput")||{}).value)||1;
    const result=await postJSON("api/simulate/",{blue:{preset:blue},red:{preset:red},seed,overrides});
    if($("blueName"))$("blueName").textContent=(presets[blue]||blue)+" (آبی)";
    if($("redName"))$("redName").textContent=(presets[red]||red)+" (قرمز)";
    switchView("arena");
    playFrames(result.frames,result.record_fps);
    setPanelStatus("آزمایش اجرا شد. اگر خوب بود، به تب «تنظیمات» برگرد و «ذخیره» کن.");
  }catch(err){showToast("❌ "+humanizeError(err),"err");setPanelStatus("خطا در آزمایش.");}
}

async function init(){
  readInjectedConfig();
  vocabulary=await fetch("api/vocabulary/").then(r=>r.json());
  if(vocabulary&&vocabulary.config){
    Object.assign(gameConfig,vocabulary.config);
    updateCanvasDimensions();
  }
  await loadStrategiesFromServer();
  quickPreset("smart");
  $("builderTab").onclick=()=>switchView("builder");
  $("arenaTab").onclick=()=>switchView("arena");
  if($("panelTab")) $("panelTab").onclick=()=>switchView("panel");
  if($("panelSave")) $("panelSave").onclick=panelSave;
  if($("panelReset")) $("panelReset").onclick=panelReset;
  if($("panelTest")) $("panelTest").onclick=panelTest;
  $("addRule").onclick=()=>addSimple();
  $("buildBot").onclick=buildBot;
  $("compileWithAI").onclick=compileWithAI;
  $("fillAiSample").onclick=()=>{$("strategyText").value="اگر بتونم شوت کنم شوت زمینی بزن. اگر حریف از من به توپ نزدیک‌تر بود برگرد دفاع. اگر من نزدیک‌تر بودم برو سمت توپ. اگر توپ بالای سرم بود بپر."};
  $("testBot").onclick=()=>{if(!myStrategy){showToast("اول یک ربات بساز، بعد آزمایشش کن.","err");return;}refreshOpponentMenus();$("blueSelect").value="mybot";$("redSelect").value="adaptive";switchView("arena");runMatch()};
  $("deleteBot").onclick=deleteBot;
  if($("saveBotBtn")) $("saveBotBtn").onclick=saveCurrentBot;
  if($("cancelEditBtn")) $("cancelEditBtn").onclick=cancelEdit;
  if($("refreshMyBotsBtn")) $("refreshMyBotsBtn").onclick=loadStrategiesFromServer;
  document.querySelectorAll("[data-quick]").forEach(btn=>btn.onclick=()=>quickPreset(btn.dataset.quick));
  $("playMatch").onclick=runMatch;
  $("runBatch").onclick=runBatch;
  $("winClose").onclick=()=>$("winFx").classList.remove("show");

  drawIdleFrame();
}
init();
