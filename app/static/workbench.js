"use strict";
const el = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const attr = esc;
const compact = (n,places=1) => n==null || !Number.isFinite(Number(n))?"—":Number(n).toLocaleString("zh-CN",{maximumFractionDigits:places});
const shortTime = x => String(x||"—").replace("T"," ").replace(/\.\d+([+Z].*)?$/,"").slice(0,19);
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
<div class="toggles"><label class="check"><input id="correction" type="checkbox">滚动实测校正</label><label class="check"><input id="ensemble" type="checkbox">集合预报（event2）</label></div>
<label class="field">校正观测截止时间（可选）<input type="datetime-local" id="cutoff"></label>
${schedule?'<label class="field">起报间隔（秒）<input id="interval" type="number" value="3600" min="1" step="1" required></label>':""}
<button class="primary" type="submit"${!store.events.length||!store.schemes.length?" disabled":""}>${schedule?"创建定时任务":"运行预报"}</button></form>`;}
function runPayload(){const evt=el("event-choice").value;store.eventId=evt;store.planId=el("plan-choice").value;const p={event_id:evt,scheme_id:Number(store.planId),correction:el("correction").checked,ensemble:el("ensemble").checked,actor:"workbench"};if(el("cutoff").value)p.cutoff=el("cutoff").value.replace("T"," ");return p;}
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
    let grid="",ticks="";for(let j=0;j<=4;j++){const v=j*step;grid+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="#d5dfdb"/><text x="${L-9}" y="${y(v)+4}" text-anchor="end">${compact(v)}</text>`;}
    for(const i of new Set([0,Math.round((n-1)/3),Math.round(2*(n-1)/3),n-1]))ticks+=`<text x="${x(i)}" y="${H-16}" text-anchor="${i===0?"start":i===n-1?"end":"middle"}">${esc(String(result.times[i]).replace("T"," ").slice(5,16))}</text>`;
    let band="";if(store.band&&result.p05?.length===n&&result.p95?.length===n&&[...result.p05,...result.p95].every(useful)){
        band=`<polygon fill="url(#hatch)" stroke="#707c72" stroke-width="0.8" points="${[...result.p95.map(point),...result.p05.map(point).reverse()].join(" ")}"/>`;}
    const raw=store.raw&&result.raw?.some((v,i)=>v!==result.forecast[i])?line(result.raw,"#9b571f",true):"";
    const dots=store.obs?(result.observed||[]).map((v,i)=>useful(v)?`<circle cx="${x(i)}" cy="${y(v)}" r="2.7" stroke="#141414" fill="white"><title>${esc(result.times[i])} 实测 ${compact(v)} m³/s</title></circle>`:"").join(""):"";
    return `<figure class="figure"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="流量过程对比图，横轴为时间，纵轴为流量，单位立方米每秒"><defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse"><rect width="6" height="6" fill="#e2ebe4"/><path d="M0,6 L6,0" stroke="#8b9d93" stroke-width="1"/></pattern></defs><g font-size="12" fill="#395058"><text x="3" y="13">m³/s</text>${grid}${ticks}</g>${band}${raw}${line(result.forecast,"#075e75",false)}${dots}</svg></figure>`;}
function chartPanel(){
    const r=store.run;if(!r)return `<section class="panel chart-panel"><div class="bar"><h2>出口流量过程</h2></div>${empty("尚无预报过程","选择洪水场次与参数方案后运行预报。")}</section>`;
    const d=r.result||{},q=d.forecast||[],max=q.length?Math.max(...q):null,ix=q.indexOf(max),t=d.times?.[ix];
    return `<section class="panel chart-panel"><div class="bar"><h2>出口流量过程</h2>${tag(runStatus(r.status),r.status!=="issued")}</div>
<p class="small">${esc(r.event_id)} · 预报 ${esc(r.id)} · 方案版本 ID ${esc(r.plan_id)}</p>
<div class="stats">${stat("预报洪峰",compact(max),"m³/s")}${stat("峰现时间",t?String(t).replace("T"," ").slice(5,16):"—")}${stat("计算时段",q.length,"个")}</div>
<div class="legend"><span><i class="key"></i>预报</span>${store.obs?'<span><i class="key obs"></i>实测</span>':""}${store.raw&&d.raw?.some((v,i)=>v!==q[i])?'<span><i class="key raw"></i>校正前</span>':""}${store.band&&d.p05?.length?'<span><i class="key band"></i>情景 P05–P95</span>':""}</div>
${d.times?hydro(d):empty("预报结果为空")}
<div class="toggles">${[["obs","叠加实测"],["raw","显示校正前过程"],["band","显示情景区间"]].map(([key,txt])=>`<label class="check"><input data-chart="${key}" type="checkbox"${store[key]?" checked":""}>${txt}</label>`).join("")}</div>
<div class="actions">${r.status==="issued"?tag("产品已签发"):button("签发产品","issue",r.id,"primary")}${button("验证回放","replay",r.id)}${button("打印过程","print")}</div>
<details><summary>逐时段读数</summary>${table(["时间","实测 m³/s","预报 m³/s","P05","P95"],(d.times||[]).map((t,i)=>[esc(shortTime(t)),compact(d.observed?.[i]),compact(q[i]),compact(d.p05?.[i]),compact(d.p95?.[i])]))}</details></section>`;}
function workView(){return `<div class="grid">${chartPanel()}<section class="panel controls"><div class="bar"><h2>起报设置</h2></div>${runFields()}</section></div><section class="panel history"><div class="bar"><h2>预报记录</h2></div>${table(["预报编号","场次","方案版本 ID","状态","操作"],store.runs.map(r=>[esc(r.id),esc(r.event_id),esc(r.plan_id),tag(runStatus(r.status)),button("查看过程","open-run",r.id)+button("回放","replay",r.id)]))}</section>`;}
function eventsView(){return `<section class="panel"><div class="bar"><h2>已入库场次</h2><div>${button("导入教学数据","demo","", "secondary")} ${button("导入 CSV","import","","primary")}</div></div>${table(["场次","时段数","质量状态","操作"],store.events.map(e=>[esc(e.event_id),esc(e.count),tag(typeof e.quality==="string"?e.quality:String(e.issues?.length||0)+" 条问题",!!e.issues?.length),button("查看质控","qc",e.event_id)]))}</section>`;}
function plansView(){return `<section class="panel"><div class="bar"><h2>参数方案与版本</h2>${button("新建方案","new-plan","","primary")}</div>${table(["方案","版本","状态","操作"],store.schemes.map(p=>[esc(p.name),esc("v"+p.version),tag(p.deleted?"已归档":p.active?"当前":"可用"),button("参数","inspect-plan",p.id)+(p.deleted?"":button("新版本","version",p.id)+(p.active?"":button("切换","activate",p.id))+button("删除","delete-plan",p.id,"danger"))]))}</section>`;}
function scheduleView(){return `<section class="panel"><div class="bar"><h2>创建定时起报</h2></div>${runFields(true)}</section><section class="panel"><div class="bar"><h2>定时任务</h2></div>${table(["编号","场次","间隔","下次触发","操作"],store.schedules.map(s=>[esc(s.id),esc(s.event_id),esc(s.interval_seconds+" s"),esc(shortTime(s.next_run_at||s.next_at||s.next_due)),button("取消","delete-schedule",s.id,"danger")]))}</section>`;}
function alertsView(){return `<section class="panel"><div class="bar"><h2>站内预警消息</h2></div>${table(["消息","预报","等级","时间","状态"],store.alerts.map(a=>[esc(a.message||a.title||a.content),button(String(a.run_id),"open-run",a.run_id),esc(a.level||a.severity||"—"),esc(shortTime(a.created_at||a.time)),(a.read||a.is_read||a.read_at)?tag("已读"):button("标为已读","read-alert",a.id)]))}</section>`;}
function auditView(){return `<section class="panel"><div class="bar"><h2>操作流水</h2></div>${table(["时间","操作人","操作","对象","明细"],store.audit.map((a,i)=>[esc(shortTime(a.created_at||a.ts||a.time)),esc(a.actor),esc(a.action),esc(a.target||a.object_id||a.run_id||"—"),button("查看","audit-detail",i)]))}</section>`;}

