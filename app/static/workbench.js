"use strict";
const el = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const attr = esc;
const compact = (n,places=1) => n==null || !Number.isFinite(Number(n))?"—":Number(n).toLocaleString("zh-CN",{maximumFractionDigits:places});
const shortTime = x => (typeof x==="number"?new Date(x*1000).toLocaleString("sv-SE"):String(x||"—")).replace("T"," ").replace(/\.\d+([+Z].*)?$/,"").slice(0,19);
const label = {work:"预报工作台",events:"数据与质控",plans:"参数方案",schedule:"定时起报",alerts:"预警通知",audit:"操作记录"};
const store = {view:"work",events:[],schemes:[],runs:[],alerts:[],audit:[],schedules:[],run:null,eventId:"",planId:"",obs:true,band:true,raw:true};
const enc=encodeURIComponent;
function notice(message,bad=false){el("notice").textContent=message;el("notice").hidden=!message;el("notice").className=bad?"error":"";}
async function api(path,method="GET",body){
    const response=await fetch("/api"+path,{method,headers:body?{"Content-Type":"application/json"}:undefined,body:body?JSON.stringify(body):undefined,cache:"no-store"});
    const data=await response.json().catch(()=>null);
    if(!response.ok){let detail=data?.detail??data?.error??response.statusText;throw new Error(typeof detail==="string"?detail:JSON.stringify(detail));}
    return data;
}
const button=(text,act,id="",kind="quiet")=>`<button type="button" class="${kind}" data-act="${attr(act)}" data-id="${attr(id)}">${esc(text)}</button>`;
const empty=(text,sub="")=>`<div class="empty"><strong>${esc(text)}</strong><span class="hint">${esc(sub)}</span></div>`;
function table(headers,rows){
    return rows.length?`<div class="scroll"><table><thead><tr>${headers.map(h=>"<th>"+esc(h)+"</th>").join("")}</tr></thead><tbody>${rows.map(r=>"<tr>"+r.map(c=>"<td>"+c+"</td>").join("")+"</tr>").join("")}</tbody></table></div>`:empty("暂无记录");
}
const opts=(list,fn,sel)=>list.map(x=>{const [v,t]=fn(x);return `<option value="${attr(v)}"${String(v)===String(sel)?" selected":""}>${esc(t)}</option>`;}).join("");
const eopts=()=>opts(store.events,x=>[x.event_id,x.event_id],store.eventId);
const popts=()=>opts(store.schemes.filter(x=>!x.deleted),x=>[x.id,`${x.name} · v${x.version}${x.active?"（当前）":""}`],store.planId);
const tag=(s,w=false)=>`<span class="tag${w?" warn":""}">${esc(s)}</span>`;
const runStatus=x=>x==="issued"?"已签发":"草稿";
const jsonBox=obj=>`<pre class="detail">${esc(JSON.stringify(obj,null,2))}</pre>`;
function modal(title,body){el("dialog-body").innerHTML="<h2>"+esc(title)+"</h2>"+body;if(!el("dialog").open)el("dialog").showModal();}
async function reload(){
    const names=["events","schemes","runs","alerts","schedules","audit"];
    const responses=await Promise.all(names.map(n=>api("/"+n)));
    for(let i=0;i<names.length;i++)store[names[i]]=responses[i];
    if(!store.events.some(x=>x.event_id===store.eventId))store.eventId=(store.events.find(x=>x.event_id==="event4")||store.events[0])?.event_id||"";
    if(!store.schemes.some(x=>String(x.id)===String(store.planId)&&!x.deleted))store.planId=(store.schemes.find(x=>x.active&&!x.deleted)||store.schemes.find(x=>!x.deleted))?.id||"";
    if(!store.run&&!store.runs.length&&store.eventId)store.preview=await api("/events/"+enc(store.eventId));
    if(store.run||store.runs.length)store.run=await api("/runs/"+enc(store.run?.id??store.runs[0].id));
    el("connection").textContent="服务在线";el("alert-count").textContent=store.alerts.filter(a=>!(a.read??a.is_read??a.read_at)).length||"";
    render();
}
function render(){
    el("page-title").textContent=label[store.view];el("content").setAttribute("aria-busy","false");
    document.querySelectorAll("button[data-view]").forEach(b=>{b.classList.toggle("current",b.dataset.view===store.view);b.setAttribute("aria-current",b.dataset.view===store.view?"page":"false");});
    el("content").innerHTML=({work:workView,events:eventsView,plans:plansView,schedule:scheduleView,alerts:alertsView,audit:auditView})[store.view]();
    if(store.view==="work"||store.view==="schedule")updateScenarioControl();
}
function updateScenarioControl(){const cb=el("ensemble"),s=el("event-choice");if(!cb||!s)return;cb.disabled=s.value!=="event2";if(cb.disabled)cb.checked=false;}
function runFields(schedule=false){return `<form class="stack" id="${schedule?"schedule-form":"run-form"}">
<label class="field">洪水场次<select id="event-choice" required>${eopts()}</select></label>
<label class="field">参数方案<select id="plan-choice" required>${popts()}</select></label>
<div class="toggles"><label class="check"><input id="correction" type="checkbox"${store.useCorrection?" checked":""}>滚动实测校正</label><label class="check"><input id="ensemble" type="checkbox"${store.useEnsemble?" checked":""}>集合预报（event2）</label></div>
<label class="field">校正观测截止时间（可选）<input type="datetime-local" id="cutoff" value="${attr(store.cutoffValue||"")}"></label>
${schedule?'<label class="field">起报间隔（秒）<input id="interval" type="number" value="3600" min="1" step="1" required></label>':""}
<button class="primary" type="submit"${!store.events.length||!store.schemes.length?" disabled":""}>${schedule?"创建定时任务":"运行预报"}</button></form>`;}
function runPayload(){const evt=el("event-choice").value;store.useCorrection=el("correction").checked;store.useEnsemble=el("ensemble").checked;store.cutoffValue=el("cutoff").value;store.eventId=evt;store.planId=el("plan-choice").value;const p={event_id:evt,scheme_id:Number(store.planId),correction:el("correction").checked,ensemble:el("ensemble").checked,actor:"workbench"};if(el("cutoff").value)p.cutoff=el("cutoff").value.replace("T"," ");return p;}
const stat=(title,value,unit="")=>`<div class="stat"><span>${esc(title)}</span><strong>${esc(value)} <small>${esc(unit)}</small></strong></div>`;
function hydro(result){
    const W=840,H=288,L=61,T=22,R=20,B=43,n=result.times.length;
    if(!n)return empty("无过程数据");
    const useful=v=>v!==null&&v!==undefined&&Number.isFinite(Number(v));
    const groups=[result.forecast,...(store.obs?[result.observed]:[]),...(store.band?[result.p95]:[]),...(store.raw?[result.raw]:[])];
    const vmax=Math.max(1,...groups.filter(Array.isArray).flat().filter(useful)),mag=10**Math.floor(Math.log10(vmax/4)),step=[1,2,2.5,5,10].map(x=>x*mag).find(x=>4*x>=vmax)||10*mag;
    const x=i=>L+i*(W-L-R)/Math.max(1,n-1),y=v=>T+(1-v/(4*step))*(H-T-B);
    const point=(v,i)=>x(i).toFixed(2)+","+y(v).toFixed(2);
    function line(arr,color,dash){if(!Array.isArray(arr))return "";let d="",move=true;arr.forEach((v,i)=>{if(!useful(v)){move=true;return;}d+=(move?"M":"L")+point(v,i);move=false;});return `<path d="${d}" fill="none" stroke="${color}" stroke-width="2.4"${dash?' stroke-dasharray="7 4"':""}/>`;}
    let grid="",ticks="";for(let j=0;j<=4;j++){const v=j*step;grid+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="#d4deec"/><text x="${L-9}" y="${y(v)+4}" text-anchor="end">${compact(v)}</text>`;}
    for(const i of new Set([0,Math.round((n-1)/3),Math.round(2*(n-1)/3),n-1]))ticks+=`<text x="${x(i)}" y="${H-16}" text-anchor="${i===0?"start":i===n-1?"end":"middle"}">${esc(String(result.times[i]).replace("T"," ").slice(5,16))}</text>`;
    let band="";if(store.band&&result.p05?.length===n&&result.p95?.length===n&&[...result.p05,...result.p95].every(useful)){
        band=`<polygon fill="url(#hatch)" stroke="#7d90ae" stroke-width="0.8" points="${[...result.p95.map(point),...result.p05.map(point).reverse()].join(" ")}"/>`;}
    const raw=store.raw&&result.raw?.some((v,i)=>v!==result.forecast[i])?line(result.raw,"#a55916",true):"";
    const dots=store.obs?(result.observed||[]).map((v,i)=>useful(v)?`<circle cx="${x(i)}" cy="${y(v)}" r="2.7" stroke="#141414" fill="white"><title>${esc(result.times[i])} 实测 ${compact(v)} m³/s</title></circle>`:"").join(""):"";
    return `<figure class="figure"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="流量过程对比图，横轴为时间，纵轴为流量，单位立方米每秒"><defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse"><rect width="6" height="6" fill="#e1e9f5"/><path d="M0,6 L6,0" stroke="#7186a6" stroke-width="1"/></pattern></defs><g font-size="12" fill="#435671"><text x="3" y="13">m³/s</text>${grid}${ticks}</g>${band}${raw}${line(result.forecast,"#193d78",false)}${dots}</svg></figure>`;}
function chartPanel(){
    const r=store.run;if(!r){
        const e=store.preview;
        if(!e)return `<section class="panel chart-panel"><h2>出口流量过程</h2>${empty("暂无观测数据","请在数据与质控页面导入场次。")}</section>`;
        const obs=e.observed.filter(v=>v!==null);
        return `<section class="panel chart-panel"><div class="bar"><h2>起报前观测过程</h2>${tag(e.event_id)}</div>
        <div class="stats">${stat("实测洪峰",compact(obs.length?Math.max(...obs):null),"m³/s")}${stat("累计面雨量",compact(e.rain.reduce((a,b)=>a+(b||0),0)),"mm")}${stat("观测时段",e.count,"个")}</div>
        <div class="legend"><span><i class="key obs"></i>实测流量</span></div>${hydro({...e,forecast:[],raw:[],p05:[],p95:[]})}</section>`;
    }
    const d=r.result||{},q=d.forecast||[],max=q.length?Math.max(...q):null,ix=q.indexOf(max),t=d.times?.[ix];
    return `<section class="panel chart-panel"><div class="bar"><h2>出口流量过程</h2>${tag(runStatus(r.status),r.status!=="issued")}</div>
<p class="small">${esc(r.event_id)} · 预报 ${esc(r.id)} · ${esc(r.snapshot?.plan_name||"参数方案")} v${esc(r.snapshot?.plan_version??r.plan_id)}　${tag(d.warning||"正常",d.warning!=="正常")} ${d.members?.length?tag(d.members.length+" 个情景"):""}</p>
<div class="stats">${stat("预报洪峰",compact(max),"m³/s")}${stat("峰现时间",t?String(t).replace("T"," ").slice(5,16):"—")}${stat("计算时段",q.length,"个")}</div>
<div class="legend"><span><i class="key"></i>预报</span>${store.obs?'<span><i class="key obs"></i>实测</span>':""}${store.raw&&d.raw?.some((v,i)=>v!==q[i])?'<span><i class="key raw"></i>校正前</span>':""}${store.band&&d.p05?.length?'<span><i class="key band"></i>情景 P05–P95</span>':""}</div>
${d.times?hydro(d):empty("预报结果为空")}
<div class="toggles">${[["obs","叠加实测"],["raw","显示校正前过程"],["band","显示情景区间"]].map(([key,txt])=>`<label class="check"><input data-chart="${key}" type="checkbox"${store[key]?" checked":""}>${txt}</label>`).join("")}</div>
<div class="actions">${r.status==="issued"?`<a class="secondary" href="/api/runs/${enc(r.id)}/bulletin" download>下载签发公报</a>`:button("签发产品","issue",r.id,"primary")}${button("验证回放","replay",r.id)}${button("打印过程","print")}</div>
<details><summary>产品与回放依据</summary>${table(["项目","记录"],[["输入快照 SHA-256",esc(r.snapshot_hash)],["模型 SHA-256",esc(r.snapshot?.engine_hash)],["结果 SHA-256",esc(r.result_hash)],["起报 / 签发",esc(shortTime(r.created))+" / "+esc(shortTime(r.issued_at))],["观测校正",r.snapshot?.correction?"开启":"关闭"],["RMSE / DC",compact(d.metrics?.rmse,3)+" m³/s / "+compact(d.metrics?.dc,6)]])}</details>
<details><summary>逐时段读数</summary>${table(["时间","实测 m³/s","预报 m³/s","P05","P95"],(d.times||[]).map((t,i)=>[esc(shortTime(t)),compact(d.observed?.[i]),compact(q[i]),compact(d.p05?.[i]),compact(d.p95?.[i])]))}</details></section>`;}
function workView(){return `<div class="grid">${chartPanel()}<section class="panel controls"><div class="bar"><h2>起报设置</h2></div>${runFields()}</section></div><section class="panel history"><div class="bar"><h2>预报记录</h2></div>${table(["预报编号","场次","方案版本 ID","状态","操作"],store.runs.map(r=>[esc(r.id),esc(r.event_id),esc(r.plan_id),tag(runStatus(r.status)),button("查看过程","open-run",r.id)+button("回放","replay",r.id)]))}</section>`;}
function eventsView(){return `<section class="panel"><div class="bar"><h2>已入库场次</h2><div>${button("导入教学数据","demo","", "secondary")} ${button("导入 CSV","import","","primary")}</div></div>${table(["场次","时段数","质量状态","操作"],store.events.map(e=>[esc(e.event_id),esc(e.count),tag(qualityName(e.quality),!!e.issues?.length),button("查看质控","qc",e.event_id)]))}</section>`;}
function plansView(){return `<section class="panel"><div class="bar"><h2>参数方案与版本</h2>${button("新建方案","new-plan","","primary")}</div>${table(["方案","版本","状态","操作"],store.schemes.map(p=>[esc(p.name),esc("v"+p.version),tag(p.deleted?"已归档":p.active?"当前":"可用"),button("参数","inspect-plan",p.id)+(p.deleted?"":button("新版本","version",p.id)+(p.active?"":button("切换","activate",p.id))+button("删除","delete-plan",p.id,"danger"))]))}</section>`;}
function scheduleView(){return `<section class="panel"><div class="bar"><h2>创建定时起报</h2></div>${runFields(true)}</section><section class="panel"><div class="bar"><h2>定时任务</h2></div>${table(["编号","场次","间隔","下次触发","最近结果","操作"],store.schedules.map(s=>[esc(s.id),esc(s.event_id),esc(s.interval_seconds+" s"),s.active?esc(shortTime(s.next_run_at)):"—",s.last_error?esc(s.last_error):s.last_run_id?button("预报 "+s.last_run_id,"open-run",s.last_run_id):"—",s.active?button("停用","delete-schedule",s.id,"danger"):tag("已停用")]))}</section>`;}
function alertsView(){return `<section class="panel"><div class="bar"><h2>站内预警消息</h2></div>${table(["消息","预报","等级","时间","状态"],store.alerts.map(a=>[esc(a.message||a.title||a.content),button(String(a.run_id),"open-run",a.run_id),esc(a.level||a.severity||"—"),esc(shortTime(a.created||a.created_at||a.time)),(a.read||a.is_read||a.read_at)?tag("已读"):button("标为已读","read-alert",a.id)]))}</section>`;}
function auditView(){return `<section class="panel"><div class="bar"><h2>操作流水</h2></div>${table(["时间","操作人","操作","对象","明细"],store.audit.map((a,i)=>[esc(shortTime(a.at||a.created_at||a.ts||a.time)),esc(a.actor),esc(a.action),esc(a.subject||a.target||a.object_id||a.run_id||"—"),button("查看","audit-detail",i)]))}</section>`;}

const stateKeys=["WU","WL","WD","S","QS","QI","QG"];
function qcPanel(e){
    const issues=e.issues||[];
    return `<p class="hint">${esc(e.event_id)} · ${esc(e.count)} 个时段 · ${esc(qualityName(e.quality))}</p>
    ${issues.length?table(["行","列","问题","级别"],issues.map(x=>[esc(x.row),esc(x.column),esc(x.reason),tag(x.severity==="error"?"阻断":"提示",true)])):'<p>该场次通过质控。</p>'}
    <details><summary>观测与输入序列</summary>${table(["时间","雨量 mm","蒸发 mm","实测 m³/s"],(e.times||[]).map((t,i)=>[esc(shortTime(t)),compact(e.rain?.[i],3),compact(e.em?.[i],3),compact(e.observed?.[i])]))}</details>`;
}
function importForm(){return `<form id="import-form" class="stack"><label class="field">场次编号<input id="import-event" required maxlength="80" placeholder="例如 demo-01"></label>
<label class="field">观测 CSV（UTF-8，列名同教学数据包）<input type="file" id="csv-file" accept=".csv,text/csv" required></label>
<p class="hint">新场次须填写全部初始状态。WU、WL、WD、S 的单位为 mm，QS、QI、QG 的单位为 m³/s。覆盖已有场次后，历史预报仍可按原快照回放。</p>
<div class="field-row">${stateKeys.map(k=>`<label class="field">${k}<input type="number" min="0" step="any" id="state-${k}"></label>`).join("")}</div><button class="primary">提交质控入库</button></form>`;}
function planEditor(plan,versioned){
    if(!plan||!plan.parameters)throw new Error("暂无可用参数模板，请先导入教学数据。");
    return `<form id="plan-form" class="stack" data-version="${versioned?attr(plan.id):""}">${versioned?`<p>${esc(plan.name)} · 以 v${esc(plan.version)} 为基础</p>`:'<label class="field">方案名称<input id="plan-name" maxlength="80" required></label>'}
    <div class="field-row">${Object.entries(plan.parameters).map(([k,v])=>`<label class="field">${esc(k)}<input data-param="${attr(k)}" type="number" step="any" required value="${attr(v)}"></label>`).join("")}</div><button class="primary">保存参数版本</button></form>`;
}
function qualityName(q){return ({ok:"通过",warning:"带标记",blocked:"阻断"})[q]||q||"—";}
async function action(act,id){
    const body={actor:"workbench"};
    switch(act){
    case "demo":await api("/events/demo","POST");await reload();notice("教学数据已就绪。");break;
    case "qc":modal("场次质控",qcPanel(await api("/events/"+enc(id))));break;
    case "import":modal("导入观测数据",importForm());break;
    case "open-run":store.run=await api("/runs/"+enc(id));store.view="work";render();window.scrollTo({top:0});break;
    case "issue":{
        if(!window.confirm("签发预报 "+id+"？签发操作将写入产品和操作记录。"))return;
        const out=await api("/runs/"+enc(id)+"/issue","POST",body);store.run=out;await reload();notice("预报 "+id+" 已签发。");break;}
    case "replay":{
        const result=await api("/runs/"+enc(id)+"/replay","POST",body);await reload();
        modal("历史预报回放",`<p>${tag(result.match?"快照重算结果一致":"结果不一致",!result.match)}</p>${jsonBox(result)}`);break;}
    case "print":window.print();break;
    case "inspect-plan":{const p=await api("/schemes/"+enc(id));modal(p.name+" · v"+p.version,table(["参数","值"],Object.entries(p.parameters).map(([k,v])=>[esc(k),esc(v)])));break;}
    case "new-plan":modal("新建参数方案",planEditor(store.schemes.find(s=>s.active)||store.schemes[0],false));break;
    case "version":modal("保存为新版本",planEditor(await api("/schemes/"+enc(id)),true));break;
    case "activate":await api("/schemes/"+enc(id)+"/activate","POST",body);store.planId=id;await reload();notice("已切换当前参数版本。");break;
    case "delete-plan":if(window.confirm("归档该方案版本？")){await api("/schemes/"+enc(id)+"?actor=workbench","DELETE");await reload();notice("方案版本已归档。");}break;
    case "delete-schedule":if(window.confirm("停用该定时任务？")){await api("/schedules/"+enc(id),"DELETE");await reload();notice("定时任务已停用。");}break;
    case "read-alert":await api("/alerts/"+enc(id)+"/read","POST",body);await reload();notice("消息已标为已读。");break;
    case "audit-detail":modal("操作明细",jsonBox(store.audit[Number(id)]));break;
    }
}
let busy=false;
async function task(fn){
    if(busy)return;busy=true;notice("");try{await fn();}catch(e){
        const msg=e?.message||String(e);
        if(el("dialog").open){let error=el("dialog-body").querySelector(".modal-error");if(!error){error=document.createElement("p");error.className="modal-error";error.setAttribute("role","alert");el("dialog-body").prepend(error);}error.textContent=msg;}
        else notice(msg,true);
    }finally{busy=false;}
}
document.addEventListener("click",e=>{
    const b=e.target.closest("button");if(!b||busy)return;
    if(b.dataset.view){store.view=b.dataset.view;notice("");render();}
    else if(b.id==="refresh")task(reload);
    else if(b.dataset.act)task(()=>action(b.dataset.act,b.dataset.id));
});
document.addEventListener("change",async e=>{
    if(e.target.id==="event-choice"){store.eventId=e.target.value;updateScenarioControl();
        if(!store.run&&store.view==="work"){
            const id=store.eventId;
            try{const preview=await api("/events/"+enc(id));if(store.eventId===id&&!store.run&&store.view==="work"){
                store.preview=preview;document.querySelector(".chart-panel").outerHTML=chartPanel();
            }}catch(err){notice(err.message,true);}
        }}
    if(e.target.id==="plan-choice")store.planId=e.target.value;
    if(e.target.dataset.chart){store[e.target.dataset.chart]=e.target.checked;const panel=document.querySelector(".chart-panel");if(panel)panel.outerHTML=chartPanel();}
});
document.addEventListener("submit",e=>{
    const id=e.target.id;if(!["run-form","schedule-form","import-form","plan-form"].includes(id))return;
    e.preventDefault();task(async()=>{
        if(id==="run-form"){store.run=await api("/runs","POST",runPayload());await reload();notice("预报草稿已生成。");}
        if(id==="schedule-form"){await api("/schedules","POST",{...runPayload(),interval_seconds:Number(el("interval").value)});await reload();notice("定时起报已创建。");}
        if(id==="import-form"){
            const eventId=el("import-event").value.trim(),file=el("csv-file").files[0];if(!file||!eventId)throw new Error("请选取 CSV 并填写场次编号。");
            if(file.size>4_000_000)throw new Error("CSV 需小于 4 MB。");
            const body={actor:"workbench",csv_text:(await file.text()).replace(/^\uFEFF/,"")},state={};
            for(const k of stateKeys){const v=el("state-"+k).value;if(v!=="")state[k]=Number(v);}
            if(Object.keys(state).length){if(Object.keys(state).length!==7)throw new Error("请填写全部七个初始状态。");body.state=state;}
            await api("/events/"+enc(eventId)+"/import","POST",body);el("dialog").close();await reload();modal("入库质控结果",qcPanel(await api("/events/"+enc(eventId))));
        }
        if(id==="plan-form"){
            const version=e.target.dataset.version,body={parameters:{},actor:"workbench"};
            for(const input of e.target.querySelectorAll("[data-param]"))body.parameters[input.dataset.param]=Number(input.value);
            if(!version)body.name=el("plan-name").value.trim();
            await api(version?"/schemes/"+enc(version)+"/versions":"/schemes","POST",body);el("dialog").close();await reload();notice("方案已保存。");
        }
    });
});
store.alertsReady=false;
reload().then(()=>{store.alertsReady=true;}).catch(e=>{el("connection").textContent="连接异常";el("content").setAttribute("aria-busy","false");el("content").innerHTML=empty("服务暂不可用","检查服务运行状态后点击刷新。");notice(e.message,true);});


// Deliver newly persisted messages while keeping text input and chart settings intact.
let polling=false;
setInterval(async()=>{
    if(polling||busy||document.hidden)return;
    polling=true;
    try {
        const incoming=await api("/alerts");
        const seen=new Set(store.alerts.map(x=>x.id));
        const fresh=incoming.filter(x=>!seen.has(x.id));
        store.alerts=incoming;
        el("alert-count").textContent=incoming.filter(x=>!x.read_at).length||"";
        if(store.alertsReady&&fresh.length)notice("收到预警："+(fresh[0].message||fresh[0].level));
        store.alertsReady=true;
        if(store.view==="alerts"&&!el("dialog").open)el("content").innerHTML=alertsView();
        if(store.view==="schedule"){
            const timers=await api("/schedules");
            if(store.view==="schedule"&&JSON.stringify(timers)!==JSON.stringify(store.schedules)){
                store.schedules=timers;
                const fragment=document.createElement("template");fragment.innerHTML=scheduleView();
                const old=el("content").querySelector(".panel:last-child");
                if(old)old.replaceWith(fragment.content.lastElementChild);
            }
        }
    }catch(e){/* Manual refresh reports transport errors. */}finally{polling=false;}
},5000);
