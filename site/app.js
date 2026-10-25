import {COMMON,CORE,NFT_ONLY,PROXIES,THEMES,defaultConfig,tokenize,validate,privateContent,safePreset} from './lib/model.js?v=20261026-5';
import {GitHub,repositoryName} from './lib/github.js?v=20261026-5';
import {internalRun,firmwareArtifact,deliveryLabel,buildRecord,privateArchives} from './lib/delivery.js?v=20261026-5';
import {SOFTWARE_PROFILES,applySoftwareProfile,softwareAdvice} from './lib/software.js?v=20261026-3';
import {runStatus,stepStatus,active,requestRun,stageName,failureHelp,artifactInfo,verifyDownload} from './lib/progress.js?v=20261026-5';
import {mergeApproved} from './lib/upstream.js?v=20261026-3';

const $=id=>document.getElementById(id);
const state={catalog:null,device:null,target:null,available:new Set(),config:defaultConfig(),git:null,file:null,loadId:0,loading:false,metadataReady:false,busy:false,pending:null,runs:[],latestRuns:[],success:null,historyPage:1,totalRuns:0,archives:[],archiving:new Set(),expanded:null,details:new Map(),refreshing:false,resultsLoaded:false,result:null,runError:''};
const targetCache=new Map();
const verifiedFiles=new Map();
let toastTimer,pollTimer;
let upstreamBusy=false,upstreamAt=0,approvedFingerprint='';
let deferredConfig=null;
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500);}
function notice(message,kind=''){const n=$('notice');n.textContent=message;n.className='notice '+kind;}
async function json(url){const r=await fetch(url);if(!r.ok)throw new Error(`资料读取失败（${r.status}）`);return r.json();}
function node(tag,text,className){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;}
const val=id=>$(id).value;
const checked=id=>$(id).checked;
function clearSelectedFile(){state.file=null;$('overlay-file').value='';$('upload-label').textContent='选择文件包';}
const bindings={
  system:{hostname:'hostname',ip:'ip',webserver:'webserver',signature:'signature',default_theme:'default-theme',theme_mode:'theme-mode'},
  network:{mode:'network-mode',gateway:'gateway',wan_port:'wan-port',lan_ports:'lan-ports',wifi_ssid:'wifi-ssid'},
  output:{filesystem:'filesystem'}
};
const checks={system:{https:'https',ipv6:'ipv6',password_secret:'password-secret'},network:{dhcp:'dhcp',pppoe_secret:'pppoe-secret',wifi_password_secret:'wifi-secret'},output:{efi:'efi',legacy:'legacy',vmdk:'vmdk',rootfs:'rootfs'}};
function readForm(){
  const c=structuredClone(state.config);
  for(const [group,fields] of Object.entries(bindings))for(const [key,id]of Object.entries(fields))c[group][key]=val(id);
  for(const [group,fields] of Object.entries(checks))for(const [key,id]of Object.entries(fields))c[group][key]=checked(id);
  c.build_mode=val('build-mode');c.output.rootfs_size_mb=Number(val('rootfs-size'));
  c.packages=tokenize(val('custom-packages'));c.firewall=val('firewall');c.defaults=val('defaults');c.overlay=val('overlay-path').trim();
  for(const key of ['docker','usb_net','usb_wireless','wwan','istoreos','routerdog','remove_links'])c.features[key]=checked(`feature-${key}`);
  return c;
}
function applyForm(c){
  $('build-mode').value=c.build_mode||'experiment';
  for(const [group,fields]of Object.entries(bindings))for(const [key,id]of Object.entries(fields))$(id).value=c[group][key];
  for(const [group,fields]of Object.entries(checks))for(const [key,id]of Object.entries(fields))$(id).checked=c[group][key];
  $('rootfs-size').value=c.output.rootfs_size_mb;$('custom-packages').value=c.packages.join(' ');$('firewall').value=c.firewall;$('defaults').value=c.defaults;$('overlay-path').value=c.overlay;
  for(const key of ['docker','usb_net','usb_wireless','wwan','istoreos','routerdog','remove_links'])$(`feature-${key}`).checked=c.features[key]||false;
  conditionalFields();
}
function browserSnapshot(c){const result=safePreset(c);result.defaults='';result.overlay='';return result;}
function persist(){
  // A private approved version may not be available until reconnecting. Do not
  // replace its saved settings with the public baseline during initial load.
  if(deferredConfig)return;
  try{localStorage.setItem('pb-autofill',String(checked('autofill')));if(checked('autofill'))localStorage.setItem('pb-current',JSON.stringify(browserSnapshot(state.config)));else localStorage.removeItem('pb-current');}catch{toast('浏览器储存不可用，仍可导出配置。');}
}
function update(){
  if(!state.device)return;
  state.config=readForm();
  const c=state.config,errors=validate(c,state.available,state.catalog?.versions);
  $('delivery-help').textContent=c.build_mode==='release'?'正式模式：要求私有仓库、至少 12 位后台密码 Secret、HTTPS；本次 x86/64 磁盘映像均须启动和登录验收通过。仍需你验证实体硬件。':'实验模式：可以不设置密码，不执行本次映像启动验收。请勿直接接入实际网络。';
  $('summary-device').textContent=state.device.name;$('summary-version').textContent=c.version;
  $('summary-packages').textContent=`${new Set([...c.packages,...c.themes,...c.proxies]).size} 个`;
  $('summary-removed').textContent=`${c.remove_packages.length} 个`;
  $('summary-output').textContent=[c.output.efi?'EFI':'',c.output.legacy?'Legacy':'',c.output.vmdk?'VMDK':'',c.output.rootfs?'ROOTFS':''].filter(Boolean).join(' / ')||c.output.filesystem;
  const panel=$('validation');panel.replaceChildren();panel.classList.toggle('invalid',errors.length>0);
  if(errors.length){const list=node('ul');errors.forEach(e=>list.append(node('li',e)));panel.append(list);}else panel.textContent=privateContent(c)||state.file?'配置已通过基础检查。含私人内容，须在私有仓库构建。':'配置已通过基础检查。构建时会再次检查依赖和映像支持。';
  if(!errors.length&&!c.system.password_secret)panel.textContent+=' 尚未设置后台密码：仅建议用于实验，实际使用前请启用密码设置。';
  $('software-advice').replaceChildren(...softwareAdvice(c).map(note=>node('p',note,'help')));
  for(const e of document.querySelectorAll('[data-package]')){
    const group=e.dataset.group,pkg=e.dataset.package;
    e.classList.toggle('selected',c[group]?.includes(pkg));
    if(group==='remove_packages')e.classList.toggle('removed',c[group].includes(pkg));
    e.setAttribute('aria-pressed',String(c[group]?.includes(pkg)));
  }
  persist();
}
function renderSoftwareProfiles(){
  $('software-profiles').replaceChildren();
  for(const profile of SOFTWARE_PROFILES){
    const card=node('div',undefined,'software-profile');card.append(node('h3',profile.name),node('p',profile.note,'help'));
    const button=node('button','加入此组合','button secondary');button.type='button';
    button.disabled=profile.source!==state.config.builder;
    if(button.disabled)button.textContent=`需${profile.source==='kwrt'?' Kwrt':'官方'}版本`;
    button.addEventListener('click',()=>{try{state.config=applySoftwareProfile(readForm(),profile.id,state.available);applyForm(state.config);update();toast('软件组合已加入；原有网络、密码引用与文件设置保持不变。');}catch(error){toast(error.message);}});
    card.append(button);$('software-profiles').append(card);
  }
}
function conditionalFields(){
  const side=val('network-mode')==='side',x86=state.config.target.startsWith('x86/');
  $('gateway-field').hidden=!side;$('gateway').required=side;
  $('theme-mode').disabled=state.config.builder!=='kwrt';
  if(val('wan-port')==='eth0'&&!val('lan-ports').trim())$('lan-ports').value='eth1';
  for(const option of $('webserver').options)option.disabled=option.value==='lighttpd'&&state.config.builder!=='kwrt';
  $('pppoe-secret').disabled=side;if(side)$('pppoe-secret').checked=false;
  $('dhcp-help').textContent=side?'旁路由开启 DHCP 时，须关闭主路由 DHCP；关闭时需要终端正确指定网关和 DNS。':'主路由模式下通常开启 DHCP。';
  for(const id of ['wan-port','lan-ports','rootfs-size','efi','legacy','vmdk'])$(id).disabled=!x86;
  if(!x86){$('wan-port').value='';$('lan-ports').value='';$('rootfs-size').value=256;$('vmdk').checked=false;}
  for(const b of document.querySelectorAll('#proxy-packages button')){
    const nft=NFT_ONLY.has(b.dataset.package);
    const blocked=nft&&val('firewall')==='iptables';
    b.disabled=!state.available.has(b.dataset.package)||(blocked&&!state.config.proxies.includes(b.dataset.package));
  }
}
function chip(pkg,name,group,{disabled=false,help=''}={}){
  const button=node('button',name,'chip');button.type='button';button.dataset.package=pkg;button.dataset.group=group;button.disabled=disabled;button.title=help||pkg;button.setAttribute('aria-pressed','false');
  if(disabled)button.append(node('small',group==='remove_packages'?'必要包':'源中无此包'));
  button.addEventListener('click',()=>{
    deferredConfig=null;state.config=readForm();const items=new Set(state.config[group]);items.has(pkg)?items.delete(pkg):items.add(pkg);state.config[group]=[...items];
    if(group==='packages')$('custom-packages').value=state.config.packages.join(' ');
    if(group==='themes')renderDefaultThemes();update();conditionalFields();
  });return button;
}
function renderDefaultThemes(){
  const old=state.config.system.default_theme;const select=$('default-theme');select.replaceChildren();
  for(const pkg of state.config.themes){const theme=pkg.replace('luci-theme-','');select.add(new Option(theme,theme));if(['argon','bootstrap'].includes(theme)){select.add(new Option(`${theme} · 浅色`,`${theme}-light`));select.add(new Option(`${theme} · 深色`,`${theme}-dark`));}}
  select.value=old;if(!select.value&&select.options.length){select.selectedIndex=0;state.config.system.default_theme=select.value;}
}
function renderPackages(){
  const meta=state.target.profiles,profile=meta.profiles[state.device.id];
  const factory=[...new Set([...(meta.default_packages||[]),...(profile.device_packages||[])])].sort();
  $('factory-count').textContent=`${factory.length} 个`;$('factory-packages').replaceChildren(...factory.map(pkg=>chip(pkg,pkg,'remove_packages',{disabled:CORE.has(pkg)||(state.config.builder==='kwrt'&&pkg==='my-default-settings')})));
  $('package-count').textContent=`${state.available.size.toLocaleString()} 个可用包`;
  const groups=new Map();for(const item of COMMON){if(!groups.has(item.group))groups.set(item.group,[]);groups.get(item.group).push(item);}
  $('common-packages').replaceChildren();
  for(const [title,items]of groups){const wrap=node('div',undefined,'package-group');wrap.append(node('p',title));const chips=node('div',undefined,'chips');for(const item of items)chips.append(chip(item.pkg,item.name,'packages',{disabled:!state.available.has(item.pkg)}));wrap.append(chips);$('common-packages').append(wrap);}
  $('proxy-packages').replaceChildren(...PROXIES.map(item=>chip(item.pkg,item.name,'proxies',{disabled:!state.available.has(item.pkg)})));
  $('theme-packages').replaceChildren(...THEMES.map(theme=>chip(`luci-theme-${theme}`,theme,'themes',{disabled:!state.available.has(`luci-theme-${theme}`)})));
  renderDefaultThemes();
  const optional={docker:['luci-app-dockerman'],usb_net:['kmod-usb-net-rtl8152','kmod-usb-net-asix','kmod-usb-net-cdc-ether','kmod-usb-net-cdc-ncm'],usb_wireless:['kmod-mt76-usb','kmod-rt2800-usb','iw','wpad-mbedtls'],wwan:['luci-proto-modemmanager','modemmanager','kmod-usb-net-qmi-wwan','kmod-usb-serial-option'],istoreos:['luci-app-istorex'],routerdog:['luci-app-routerdog']};
  if(state.config.builder==='kwrt')optional.wwan=['luci-app-wwand','luci-proto-wwand','wwand-esim','wwand-mbim','wwand-mhi','wwand-ncm'];
  for(const [feature,pkgs]of Object.entries(optional)){
    const field=$(`feature-${feature}`);field.disabled=pkgs.some(p=>!state.available.has(p));
    field.parentElement.title=field.disabled?'当前软件源缺少一个或多个依赖包':pkgs.join(' ');
  }
}
async function targetData(device){
  const key=`${device.version}/${device.target}`;
  if(targetCache.has(key))return targetCache.get(key);
  let data;
  try{data=await json(`data/${device.metadata}`);}catch{
    if(device.builder==='kwrt')throw new Error('Kwrt 固定版本资料不可用，请稍后重试；不会混用官方软件源');
    const profiles=await json(`https://downloads.openwrt.org/releases/${device.version}/targets/${device.target}/profiles.json`);
    const branch=device.version.split('.').slice(0,2).join('.');
    const indexes=await Promise.allSettled([json(`https://sysupgrade.openwrt.org/json/v1/releases/${device.version}/targets/${device.target}/index.json`),json(`https://sysupgrade.openwrt.org/json/v1/releases/packages-${branch}/${profiles.arch_packages}-index.json`)]);
    const packages=new Set();indexes.forEach((r,i)=>{if(r.status==='fulfilled')Object.keys(i===0?r.value.packages:r.value).forEach(p=>packages.add(p));});
    data={profiles,packages:[...packages],package_metadata_errors:indexes.filter(r=>r.status==='rejected').map(()=> '部分软件包索引读取失败')};
  }
  targetCache.set(key,data);return data;
}
async function selectDevice(device,config=null){
  const requestId=++state.loadId;notice('正在读取设备详情和可用软件包…');$('device-results').hidden=true;$('device-search').setAttribute('aria-expanded','false');
  state.loading=true;state.metadataReady=false;$('build-button').disabled=true;$('preview-button').disabled=true;
  try{
    const data=await targetData(device);if(requestId!==state.loadId)return;
    state.device=device;state.target=data;state.available=new Set(data.packages);state.config=config||defaultConfig(device.version,device.target,device.id);
    clearSelectedFile();
    $('device-search').value=device.name;$('version').value=device.version;
    $('device-count').textContent=`${state.catalog.devices.filter(d=>d.version===device.version).length.toLocaleString()} 个设备档案`;
    $('device-name').textContent=device.name;$('device-platform').textContent=`${device.target} · ${device.id}`;
    $('target-label').textContent=device.target;$('arch-label').textContent=data.profiles.arch_packages;
    $('builder-label').textContent=device.builder==='kwrt'?'Kwrt ImageBuilder':'官方 ImageBuilder';
    $('kernel-label').textContent=data.profiles.linux_kernel?.version||'查看构建环境';
    const images=data.profiles.profiles[device.id]?.images||[];
    $('official-images').replaceChildren();
    const imageBase=data.image_base||`https://downloads.openwrt.org/releases/${device.version}/targets/${device.target}`;
    for(const image of images){const row=node('div',undefined,'download-item');const link=node('a',`${image.type} · ${image.filesystem} · ${(image.size/1048576).toFixed(1)} MiB ↗`);link.href=`${imageBase}/${encodeURIComponent(image.name)}`;link.target='_blank';link.rel='noreferrer';row.append(link,node('code',`SHA256 ${image.sha256}`));$('official-images').append(row);}
    renderPackages();renderSoftwareProfiles();applyForm(state.config);update();
    const source=device.builder==='kwrt'?'Kwrt 固定构建包':'OpenWrt 官方';
    notice(data.package_metadata_errors.length?'设备资料已载入，但部分包索引不可用；请刷新后再构建。':`${source}资料已载入。`+(state.git?`已连接构建仓库 ${state.git.repo}。`:'可导出配置，在 GitHub 手动构建；连接仓库授权后也可直接提交。'),data.package_metadata_errors.length?'warning':'');
    state.metadataReady=!data.package_metadata_errors.length;return true;
  }catch(error){if(requestId===state.loadId)notice(`设备资料载入失败：${error.message}。可重新选择或刷新。`,'error');return false;
  }finally{if(requestId===state.loadId){state.loading=false;buildAvailability();$('preview-button').disabled=!state.metadataReady;}}
}
function showDevices(){
  const value=val('device-search').toLowerCase().trim(),version=val('version');
  const devices=state.catalog.devices.filter(d=>d.version===version&&[d.name,d.target,d.id,...d.aliases].some(s=>s.toLowerCase().includes(value))).sort((a,b)=>Number(b.target==='x86/64')-Number(a.target==='x86/64')).slice(0,40);
  $('device-results').replaceChildren();
  for(const d of devices){const b=node('button',d.name);b.type='button';b.setAttribute('role','option');b.append(node('small',`${d.target} · ${d.id}`));b.addEventListener('click',()=>selectDevice(d));$('device-results').append(b);}
  if(!devices.length)$('device-results').append(node('p','未找到匹配设备。','help'));
  $('device-results').hidden=false;$('device-search').setAttribute('aria-expanded','true');
}
function renderFeatures(){
  for(const [id,label]of [['docker','Docker 管理'],['usb_net','USB 有线网卡'],['usb_wireless','USB 无线网卡'],['wwan','WWAN / 蜂窝网络'],['istoreos','iStoreOS 风格界面'],['routerdog','路由狗 / NAS 模式'],['remove_links','去除作者外链']]){
    const labelNode=node('label',undefined,'check');const input=node('input');input.type='checkbox';input.id=`feature-${id}`;labelNode.append(input,document.createTextNode(label));if(id==='remove_links')labelNode.title='仅隐藏发行方推广链接，保留文字、开源许可和源码入口';$('feature-options').append(labelNode);
  }
}
function presetOptions(){
  $('preset-list').replaceChildren(new Option('选择已保存模板…',''));
  try{const presets=JSON.parse(localStorage.getItem('pb-presets')||'{}');for(const name of Object.keys(presets))$('preset-list').add(new Option(name,name));}catch{}
}
function configText(){return JSON.stringify(readForm(),null,2);}
function showConfig(){
  $('config-json').value=configText();
  try{$('manual-run').href=`https://github.com/${repositoryName(val('repository'))}/actions/workflows/build.yml`;$('manual-run').hidden=false;}catch{$('manual-run').hidden=true;}
  $('config-dialog').showModal();
}
function externalLink(label,url){const a=node('a',label);a.href=url;a.target='_blank';a.rel='noreferrer';return a;}
function savePending(){try{if(state.pending)sessionStorage.setItem('pb-pending',JSON.stringify(state.pending));else sessionStorage.removeItem('pb-pending');}catch{}}
function buildAvailability(){$('build-button').disabled=state.busy||state.loading||!state.metadataReady||Boolean(state.pending&&state.git?.repo===state.pending.repo);}
function pendingPanel(){
  const p=state.pending,box=$('pending-build');box.hidden=!p||p.repo!==state.git?.repo;
  if(box.hidden)return;
  const run=requestRun(state.latestRuns,p.id);
  $('pending-status').textContent=run?`本次请求：${runStatus(run)}（#${run.run_number}）`:'本次请求已发送，正在等待 GitHub 登记。暂不重复提交。';
  $('pending-id').textContent=`请求编号 ${p.id}`;
  $('release-pending').hidden=Date.now()-p.at<120000||Boolean(run&&active(run));
}
function renderLatestResults(){
  const body=$('latest-results-body'),git=state.git,button=$('refresh-results');body.replaceChildren();
  button.textContent=git?'刷新结果 ↻':'连接查看结果';button.disabled=state.refreshing;
  $('results-privacy').textContent=git?(git.private?'已授权读取私有仓库 · 不公开固件':'当前连接的是公开仓库，请勿放入私人配置'):'固件保持私有，不会发布到公开网页';
  if(!git){body.append(node('p','你的固件保存在私有仓库。连接 GitHub 后，这里会显示最近成功的编译结果；登录 GitHub 本站不等于已授权此网页。','help'));return;}
  if(state.runError){body.append(node('p',`暂时无法读取编译结果：${state.runError}`,'error'));const reconnect=node('button','重新连接 GitHub','button secondary');reconnect.type='button';reconnect.addEventListener('click',()=>$('connect-dialog').showModal());body.append(reconnect);return;}
  if(!state.resultsLoaded){body.append(node('p','正在读取你的编译结果…','help'));return;}
  const latest=state.latestRuns.filter(r=>!internalRun(r))[0],success=state.success;
  if(latest&&latest.id!==success?.id){const message=node('p',`最新任务 #${latest.run_number}：${runStatus(latest)}。${success?'下方保留最近成功的结果。':'成功后会自动显示下载包。'}`,'notice');message.append(document.createTextNode(' '),externalLink('查看任务 ↗',latest.html_url));body.append(message);}
  if(!success){body.append(node('p',latest?'暂时没有成功的编译结果。':'这个仓库还没有构建记录。可以在下方选择设备并启动构建。','help'));return;}
  const summary=node('div',undefined,'result-summary');
  summary.append(node('strong',`构建 #${success.run_number} · 编译成功`),node('span',`完成时间 ${new Date(success.updated_at||success.created_at).toLocaleString()}`));
  summary.append(externalLink('查看日志与映像清单 ↗',success.html_url));body.append(summary);
  if(state.result?.runId!==success.id){body.append(node('p','正在读取下载包…','help'));return;}
  if(state.result.error){body.append(node('p',`下载包读取失败：${state.result.error} 请点击“刷新结果”重试。`,'error'));return;}
  const artifacts=state.result.artifacts.filter(firmwareArtifact);
  if(!artifacts.length)body.append(node('p','此任务已成功，但下载包已被清理或未保存。请查看任务日志，必要时重新构建。','help'));
  for(const artifact of artifacts)body.append(renderArtifact(success,artifact));
  renderDelivery(success,state.result,body);
  body.append(node('p','这里是最近成功的个人构建，不代表下方尚未提交的配置。旧任务保留原下载方式；新任务按格式分包并显示每个文件的 SHA256。','fine'));
}
function renderDelivery(run,data,container){
  container.append(node('p',deliveryLabel(data.record),'notice '+(data.record?.vm?.status==='passed'?'':'warning')));
  if(data.recordError)container.append(node('p',data.recordError,'error'));
  if(data.record){
    const wrap=node('div',undefined,'file-table'),table=node('table'),head=node('tr');
    for(const title of ['文件 / 格式','大小','SHA256'])head.append(node('th',title));table.append(head);
    for(const file of data.record.files){const row=node('tr'),name=node('td',file.name);name.append(node('small',file.group));row.append(name,node('td',`${(file.bytes/1048576).toFixed(2)} MiB`));const hash=node('td');hash.append(node('code',file.sha256));row.append(hash);table.append(row);}wrap.append(table);container.append(wrap);
    const reuse=node('button','用此配置重新填写','button secondary');reuse.type='button';reuse.addEventListener('click',async()=>{reuse.disabled=true;try{await restore(data.record.config);toast('配置已填写，尚未提交构建；密码仍只引用仓库 Secret。');}catch(error){toast(error.message);}finally{reuse.disabled=false;}});container.append(reuse);
  }else container.append(node('p','旧任务没有逐项记录，或记录尚在保存。请从 GitHub 任务摘要 / ZIP 内清单查看映像 SHA256；不会将旧固件误标为已验收。','help'));
  if(run.conclusion==='success'&&state.git?.private){
    const saved=state.archives.find(a=>a.runId===String(run.id));
    if(saved){container.append(document.createTextNode(' '),externalLink('已私有收藏 ↗',saved.url));return;}
    const button=node('button',state.archiving.has(run.id)?'私有收藏处理中…':'收藏到私有仓库','button secondary');button.type='button';button.disabled=state.archiving.has(run.id)||!data.artifacts.some(a=>firmwareArtifact(a)&&!artifactInfo(a).expired)||state.archives.length>=5;
    button.addEventListener('click',async()=>{const git=state.git;button.disabled=true;try{await git.archive(run.id);if(git!==state.git)return;state.archiving.add(run.id);button.textContent='私有收藏处理中…';toast('已提交私有收藏。不会公开或删除固件，请在下方查看收藏任务。');await refreshArchives();}catch(error){toast(error.message);button.disabled=false;}});container.append(document.createTextNode(' '),button);
  }
}
async function recordFor(git,run){try{return {record:buildRecord(await git.buildRecord(run.id),run)};}catch(error){return error.status===404?{}:{recordError:`逐项清单读取失败：${error.message}`};}}
async function refreshArchives(){
  const git=state.git,body=$('archive-list');if(!git){body.textContent='连接私有仓库后查看收藏。';return;}
  $('refresh-archives').disabled=true;
  try{const [releases,runs]=await Promise.all([git.releases(),git.archiveRuns().catch(error=>error.status===404?{workflow_runs:[]}:Promise.reject(error))]);if(git!==state.git)return;state.archives=privateArchives(releases,git.repo);body.replaceChildren();
    for(const archive of state.archives){state.archiving.delete(Number(archive.runId));const card=node('div',undefined,'artifact');card.append(externalLink(archive.name+' ↗',archive.url),node('p',`私有收藏 · ${new Date(archive.date).toLocaleString()}`,'help'));for(const asset of archive.assets){const row=node('div',undefined,'download-item');row.append(externalLink(`${asset.name} · ${(asset.size/1048576).toFixed(1)} MiB ↗`,asset.url));if(asset.digest)row.append(node('code',asset.digest));card.append(row);}body.append(card);}
    if(!state.archives.length)body.append(node('p','还没有私有收藏。成功构建后可手动收藏；不会自动占用空间。','help'));
    const latest=runs.workflow_runs?.[0];if(latest){body.append(externalLink(`最近收藏任务：${runStatus(latest)} ↗`,latest.html_url));if(latest.conclusion==='failure')body.append(node('p','收藏未完成，原构建产物不受影响。请查看任务原因；不会自动重复提交。','error'));if(!active(latest))state.archiving.clear();}
    renderLatestResults();
  }catch(error){if(git===state.git)body.replaceChildren(node('p',`收藏读取失败：${error.message}`,'error'));}finally{$('refresh-archives').disabled=false;}
}
function renderRunDetails(run,container){
  container.replaceChildren();const data=state.details.get(run.id);
  if(!data){container.append(node('p','正在读取步骤与产物…','help'));return;}
  if(data.error){container.append(node('p',data.error,'error'));return;}
  const steps=data.jobs.flatMap(job=>job.steps||[]),failed=steps.find(step=>step.conclusion==='failure');
  const list=node('ol',undefined,'run-steps');
  for(const step of steps.filter(s=>!s.name.startsWith('Post '))){const li=node('li',`${stageName(step.name)} · ${stepStatus(step)}`);li.className=step.conclusion==='failure'?'error':'';list.append(li);}
  container.append(list);
  if(run.conclusion==='failure'||run.conclusion==='timed_out')container.append(node('p',failureHelp(failed),'notice warning'));
  if(!data.artifacts.length)container.append(node('p',active(run)?'完成后会在这里显示固件、校验值与到期时间。':'没有可下载的产物，或已被 GitHub 清理。','help'));
  for(const artifact of data.artifacts)container.append(renderArtifact(run,artifact));
  renderDelivery(run,data,container);
  container.append(node('p','ZIP 校验不等于固件已通过实机测试。解压后请用包内 SHA256SUMS 校验具体映像；固件含私人设置时勿转发。','fine'));
}
function renderArtifact(run,artifact){
    const info=artifactInfo(artifact),card=node('div',undefined,'artifact');
    card.append(node('strong',`${artifact.name} · ${(artifact.size_in_bytes/1048576).toFixed(1)} MiB`));
    card.append(node('p',info.expired?'已到期，无法下载':`到期：${new Date(artifact.expires_at).toLocaleString()}${info.days!==null?`（约 ${info.days} 天）`:''}`,'help'));
    if(info.digest)card.append(node('code',`ZIP 下载包 SHA256：${info.digest}`));
    if(!info.expired){
      const download=externalLink(firmwareArtifact(artifact)?'下载固件 ZIP ↗':'下载日志 / 附件 ZIP ↗',`https://github.com/${state.git.repo}/actions/runs/${run.id}/artifacts/${artifact.id}`);download.className='button primary';card.append(download);
      if(info.digest&&artifact.size_in_bytes<=256*1024*1024){
        const label=node('label','校验已下载的 ZIP（仅在本机读取，不上传）','verify-label'),input=node('input');input.type='file';input.accept='.zip';
        const remembered=verifiedFiles.get(info.digest),result=node('p',remembered?.text||'',remembered?.className||'help');result.setAttribute('role','status');
        input.addEventListener('change',async()=>{const file=input.files[0];if(!file)return;input.disabled=true;result.textContent='正在本机计算 SHA256…';try{const check=await verifyDownload(file,info.digest);result.textContent=check.ok?'校验通过：ZIP 与 GitHub 保存的下载包一致。':'校验不一致：请勿使用。确认选中了本次任务的原始 ZIP，必要时重新下载。';result.className=check.ok?'help':'error';}catch(error){result.textContent=error.message;result.className='error';}finally{verifiedFiles.set(info.digest,{text:result.textContent,className:result.className});input.disabled=false;}});
        label.append(input);card.append(label,result);
      }
      if(info.digest&&artifact.size_in_bytes>256*1024*1024)card.append(node('p','此 ZIP 超过 256 MiB，为避免浏览器内存不足，请下载后使用系统 SHA256 工具对照上方校验值。ZIP 校验与解压后的映像校验值不同。','help'));
    }
    return card;
}
function renderRuns(){
  $('history-page').textContent=`第 ${state.historyPage} 页 · 共 ${state.totalRuns} 次`;$('history-prev').disabled=state.historyPage<=1;$('history-next').disabled=state.historyPage*12>=state.totalRuns;
  $('run-list').replaceChildren();$('run-list').classList.toggle('empty',!state.runs.length);
  if(!state.runs.length){$('run-list').textContent='这个仓库还没有构建记录。';return;}
  for(const run of state.runs){
    const detail=node('details',undefined,'run-card'),summary=node('summary',undefined,'run');detail.open=state.expanded===run.id;
    const main=node('div',`构建 #${run.run_number}${internalRun(run)?' · 内部验收测试':''}`);main.append(node('small',new Date(run.created_at).toLocaleString()));summary.append(main,node('span',runStatus(run),'pill'));detail.append(summary);
    const body=node('div',undefined,'run-detail');body.append(externalLink('完整日志与 GitHub 结果 ↗',run.html_url));const content=node('div');body.append(content);detail.append(body);
    if(detail.open)renderRunDetails(run,content);
    detail.addEventListener('toggle',()=>{if(detail.open){state.expanded=run.id;renderRunDetails(run,content);if(!state.details.has(run.id)||active(run))loadRunDetails(run,content);}else if(state.expanded===run.id)state.expanded=null;});
    $('run-list').append(detail);
  }
}
async function loadRunDetails(run,container){
  const git=state.git;
  try{const [jobs,artifacts,record]=await Promise.all([git.jobs(run.id),git.artifacts(run.id),recordFor(git,run)]);if(git!==state.git)return;state.details.set(run.id,{jobs:jobs.jobs||[],artifacts:artifacts.artifacts||[],...record});}
  catch(error){if(git!==state.git)return;state.details.set(run.id,{error:error.message});}
  if(container?.isConnected)renderRunDetails(run,container);
}
function schedulePoll(){clearTimeout(pollTimer);if(state.git&&!document.hidden)pollTimer=setTimeout(()=>refreshRuns(false),state.pending||state.runs.some(active)?20000:60000);}
async function refreshRuns(manual=true){
  if(!state.git){if(manual)toast('先连接你的 GitHub 构建仓库。');return;}
  if(state.refreshing)return;state.refreshing=true;const git=state.git;$('refresh-runs').disabled=true;$('refresh-results').disabled=true;
  try{const [history,first,successful]=await Promise.all([git.runs(state.historyPage),state.historyPage>1?git.runs():null,git.latestSuccess()]);if(git!==state.git)return;
    const runs=history.workflow_runs||[];state.runs=runs;state.totalRuns=history.total_count||0;state.latestRuns=(first||history).workflow_runs||[];state.success=(successful.workflow_runs||[]).find(r=>!internalRun(r))||null;state.resultsLoaded=true;state.runError='';const tracked=state.pending?.repo===git.repo?requestRun(state.latestRuns,state.pending.id):null;
    if(tracked){state.expanded=tracked.id;if(!active(tracked)){state.pending=null;savePending();}}
    const success=state.success;
    if(success){try{const [data,record]=await Promise.all([git.artifacts(success.id),recordFor(git,success)]);if(git!==state.git)return;state.result={runId:success.id,artifacts:data.artifacts||[],...record};}catch(error){if(git!==state.git)return;state.result={runId:success.id,error:error.message};}}else state.result=null;
    const opened=runs.find(run=>run.id===state.expanded);if(opened)await loadRunDetails(opened);
    if(git!==state.git)return;renderRuns();pendingPanel();buildAvailability();$('poll-status').textContent=`自动更新中 · 最近更新 ${new Date().toLocaleTimeString()}（切换到后台时暂停）`;
  }catch(error){if(git===state.git){state.runError=error.message;$('poll-status').textContent=`刷新失败：${error.message} 原记录保留；不会自动重提交构建。`;}}
  finally{state.refreshing=false;$('refresh-runs').disabled=false;renderLatestResults();schedulePoll();if(state.archiving.size)refreshArchives();if(Date.now()-upstreamAt>300000)refreshUpstream();renderConnection();}
}
function renderConnection(){const git=state.git;$('connection-info').textContent=git?`授权仅保存在此页内存，刷新后需重新连接。${git.tokenExpiresAt?`令牌到期：${git.tokenExpiresAt}。`:''}${Number.isFinite(git.rateRemaining)&&git.rateRemaining<100?`GitHub 本时段剩余请求 ${git.rateRemaining}，请减少手动刷新。`:''}`:'';}
async function refreshUpstream(){
  const git=state.git;if(!git||upstreamBusy||!state.catalog)return;
  upstreamBusy=true;upstreamAt=Date.now();$('refresh-upstream').disabled=true;
  const body=$('upstream-body');
  try{
    const [data,runs]=await Promise.allSettled([git.approvedUpstream(),git.upstreamRuns()]);
    if(git!==state.git)return;
    const parts=[];
    if(runs.status==='fulfilled'){
      const run=runs.value.workflow_runs?.[0];
      if(run){const status=run.conclusion==='success'?'检查完成':active(run)?'检查 / 测试进行中':runStatus(run);parts.push(node('p',`最近检查：${new Date(run.updated_at).toLocaleString()} · ${status}`));
        if(['failure','timed_out','cancelled'].includes(run.conclusion))parts.push(node('p','本次检查或测试未通过，不会提升新版本；已批准的版本保持不变。','error'));}
    }else if(runs.reason.status!==404)parts.push(node('p',`检查状态读取失败：${runs.reason.message}`,'error'));
    if(data.status==='fulfilled'){
      const approved=data.value,merged=mergeApproved(state.catalog,approved);
      if(approvedFingerprint!==approved.fingerprint){
        // Preserve the entire current form, selected file and current metadata.
        // New package metadata applies only when the user chooses a version.
        const selected=val('version');state.catalog=merged.catalog;
        for(const [key,value]of merged.targets)targetCache.set(key,value);
        $('version').replaceChildren(...state.catalog.versions.map(v=>new Option(state.catalog.version_labels?.[v]||`OpenWrt ${v}`,v)));$('version').value=selected;
        approvedFingerprint=approved.fingerprint;
      }
      parts.push(node('p',`已批准：${new Date(approved.approved_at).toLocaleString()} · ${approved.sources.map(s=>s.version).join(' / ')}`));
      parts.push(node('p','两种来源均已通过 EFI、Legacy、VMDK 启动与 LuCI 登录测试。新版本已加入固件版本列表；当前配置没有改动。','help'));
      if(deferredConfig&&state.catalog.versions.includes(deferredConfig.version)){
        const saved=deferredConfig,button=node('button','恢复上次自动更新版本的配置','button secondary');button.type='button';
        button.addEventListener('click',async()=>{if(deferredConfig!==saved){button.remove();return;}button.disabled=true;try{await restore(saved);button.remove();toast('已恢复上次配置。');}catch(error){toast(error.message);button.disabled=false;}});parts.push(button);
      }
    }else if(data.reason.status===404)parts.push(node('p','自动跟进已接入，尚无通过本流程的版本；首次校验完成后会自动加入版本列表。','help'));
    else parts.push(node('p',`更新资料读取失败：${data.reason.message} 已加载的版本仍保留。`,'error'));
    parts.push(externalLink('查看上游检查与测试记录 ↗',`https://github.com/${git.repo}/actions/workflows/upstream.yml`));
    body.replaceChildren(...parts);
  }catch(error){body.replaceChildren(node('p',error.message,'error'));}
  finally{upstreamBusy=false;$('refresh-upstream').disabled=false;}
}
async function connect(){
  $('connect-error').textContent='';$('confirm-connect').disabled=true;
  try{const git=new GitHub(val('repository').trim(),val('github-token').trim(),val('branch').trim());const data=await git.connect();state.git=git;state.runs=[];state.latestRuns=[];state.success=null;state.historyPage=1;state.archives=[];state.archiving.clear();state.details.clear();state.expanded=null;state.resultsLoaded=false;state.result=null;state.runError='';renderLatestResults();$('github-token').value='';
    // Store only the repository and branch. GitHub credentials remain in RAM.
    localStorage.setItem('pb-repository',git.repo);localStorage.setItem('pb-branch',git.ref);
    $('connection-label').textContent=`${git.repo.split('/')[1]} · ${data.private?'私有':'公开'}`;
    $('connection-dot').classList.add('connected');$('connect-dialog').close();toast('仓库已连接。令牌仅保存在本页内存中。');notice(`已连接${data.private?'私有':'公开'}构建仓库 ${git.repo}。`);await Promise.all([refreshRuns(),refreshUpstream(),refreshArchives()]);
    $('history-link').href=`https://github.com/${git.repo}/actions/workflows/build.yml`;
  }catch(error){$('connect-error').textContent=error.message;}finally{$('confirm-connect').disabled=false;}
}
async function startBuild(){
  if(state.pending&&state.pending.repo===state.git?.repo){toast('上次请求仍在登记或执行，请先查看构建记录。');return;}
  if(state.loading||!state.metadataReady){toast('请等设备资料载入完成后再构建。');return;}
  state.config=readForm();const errors=validate(state.config,state.available,state.catalog?.versions);if(errors.length){update();toast(errors[0]);return;}
  if(!state.git?.token){showConfig();toast('可导出配置并手动运行，或连接仓库授权后直接构建。');return;}
  if((privateContent(state.config)||state.file)&&!state.git.private){toast('初始化脚本、密码引用和文件包须使用私有构建仓库。');return;}
  const config=structuredClone(state.config),file=state.file,git=state.git;
  const button=$('build-button');state.busy=true;button.disabled=true;button.textContent='正在提交…';
  try{if(file){config.overlay=await git.upload(file);if(state.file===file){state.config.overlay=config.overlay;$('overlay-path').value=config.overlay;}}
    const requestId=crypto.randomUUID();state.pending={id:requestId,at:Date.now(),repo:git.repo};savePending();pendingPanel();await git.dispatch(config,requestId);toast('GitHub 已接受构建请求，进度会自动更新。');notice(`构建请求已提交：${config.version} / ${config.profile}。可关闭页面，构建仍会继续；返回时需重新连接授权。`);await refreshRuns(false);
  }catch(error){if(error.status>=400&&error.status<500){state.pending=null;savePending();pendingPanel();}notice(error.message,'error');schedulePoll();}finally{state.busy=false;buildAvailability();button.replaceChildren(document.createTextNode('构建新固件 '),node('span','↗'));}
}
async function restore(config){
  const clean=safePreset(config),errors=validate(clean,null,state.catalog?.versions);if(errors.length)throw new Error(errors[0]);
  const device=state.catalog.devices.find(d=>d.version===clean.version&&d.target===clean.target&&d.id===clean.profile);if(!device)throw new Error('此配置的版本/设备不在当前目录中。');
  if(!await selectDevice(device,clean))throw new Error('此设备资料未载入，配置尚未导入。');
  deferredConfig=null;persist();
}
async function init(){
  renderFeatures();presetOptions();renderLatestResults();
  try{const p=JSON.parse(sessionStorage.getItem('pb-pending')||'null');if(p&&/^[a-f0-9-]{36}$/.test(p.id)&&Number.isFinite(p.at)&&typeof p.repo==='string')state.pending=p;}catch{}
  $('repository').value=localStorage.getItem('pb-repository')||'hadeschan1985/openwrt-personal-builds';$('branch').value=localStorage.getItem('pb-branch')||'main';$('autofill').checked=localStorage.getItem('pb-autofill')!=='false';
  $('builder-form').addEventListener('submit',e=>e.preventDefault());
  $('builder-form').addEventListener('input',()=>{deferredConfig=null;update();});
  $('builder-form').addEventListener('change',e=>{if(e.target.id==='network-mode')$('dhcp').checked=val('network-mode')==='router';conditionalFields();update();});
  $('device-search').addEventListener('input',()=>state.catalog&&showDevices());$('device-search').addEventListener('focus',()=>state.catalog&&showDevices());
  $('device-search').addEventListener('keydown',e=>{if(e.key==='Escape'){$('device-results').hidden=true;$('device-search').setAttribute('aria-expanded','false');}if(e.key==='ArrowDown'){$('device-results').querySelector('button')?.focus();e.preventDefault();}});
  document.addEventListener('click',e=>{if(!e.target.closest('.search-field')){$('device-results').hidden=true;$('device-search').setAttribute('aria-expanded','false');}});
  $('version').addEventListener('change',()=>{const devices=state.catalog.devices.filter(d=>d.version===val('version'));$('device-count').textContent=`${devices.length.toLocaleString()} 个设备档案`;selectDevice(devices.find(d=>d.id===state.device?.id&&d.target===state.device?.target)||devices.find(d=>d.target==='x86/64')||devices[0]);});
  $('package-search').addEventListener('input',()=>{const query=val('package-search').toLowerCase().trim();$('package-results').replaceChildren();if(query)for(const pkg of [...state.available].filter(p=>p.includes(query)).slice(0,12))$('package-results').append(chip(pkg,pkg,'packages'));update();});
  $('preview-button').addEventListener('click',showConfig);$('build-button').addEventListener('click',startBuild);
  $('connect-button').addEventListener('click',()=>$('connect-dialog').showModal());$('confirm-connect').addEventListener('click',connect);
  $('refresh-runs').addEventListener('click',()=>refreshRuns());
  $('history-prev').addEventListener('click',()=>{if(state.historyPage>1&&!state.refreshing){state.historyPage--;state.expanded=null;refreshRuns();}});
  $('history-next').addEventListener('click',()=>{if(state.historyPage*12<state.totalRuns&&!state.refreshing){state.historyPage++;state.expanded=null;refreshRuns();}});
  $('refresh-archives').addEventListener('click',()=>state.git?refreshArchives():$('connect-dialog').showModal());
  $('refresh-upstream').addEventListener('click',()=>state.git?refreshUpstream():$('connect-dialog').showModal());
  $('refresh-results').addEventListener('click',()=>state.git?refreshRuns():$('connect-dialog').showModal());
  document.addEventListener('visibilitychange',()=>{clearTimeout(pollTimer);if(!document.hidden&&state.git)refreshRuns(false);});
  $('release-pending').addEventListener('click',()=>{state.pending=null;savePending();pendingPanel();buildAvailability();toast('已解除本页等待。不会取消 GitHub 任务，重新提交前请确认没有重复任务。');});
  $('copy-config').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('config-json').value);toast('构建配置已复制。下一步打开 GitHub。');}catch{toast('自动复制不可用，请展开配置明细后复制。');}});
  $('download-config').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([$('config-json').value],{type:'application/json'}));const a=node('a');a.href=url;a.download=`openwrt-${state.config.target.replace('/','-')}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  $('autofill').addEventListener('change',persist);
  $('save-preset').addEventListener('click',()=>{const name=val('preset-name').trim();if(!name){toast('先给模板起一个名字。');return;}const presets=JSON.parse(localStorage.getItem('pb-presets')||'{}');presets[name]=browserSnapshot(readForm());localStorage.setItem('pb-presets',JSON.stringify(presets));presetOptions();toast('模板已保存在本机；初始化脚本和文件包路径未自动保存。');});
  $('preset-list').addEventListener('change',async()=>{if(!val('preset-list'))return;try{await restore(JSON.parse(localStorage.getItem('pb-presets'))[val('preset-list')]);toast('模板已载入。');}catch(error){toast(error.message);}});
  $('import-config').addEventListener('change',async e=>{try{const f=e.target.files[0];if(!f)return;if(f.size>60000)throw new Error('配置文件不能超过 60 KB。');await restore(JSON.parse(await f.text()));toast('配置已导入。');}catch(error){toast(error.message);}e.target.value='';});
  $('clear-overlay').addEventListener('click',()=>{clearSelectedFile();$('overlay-path').value='';update();toast('已清除本页选择；不会删除仓库中的文件。');});
  $('overlay-file').addEventListener('change',e=>{const file=e.target.files[0];if(!file)return;if(file.size>12*1024*1024||!/(\.zip|\.tgz|\.tar\.gz|\.7z)$/i.test(file.name)){e.target.value='';toast('请选择不超过 12 MiB 的 ZIP/TAR.GZ/TGZ/7Z。');return;}state.file=file;$('upload-label').textContent=`${file.name} · ${(file.size/1048576).toFixed(2)} MiB`;$('overlay-path').value='';update();});
  try{state.catalog=await json('data/catalog.json');$('version').replaceChildren(...state.catalog.versions.map(v=>new Option(state.catalog.version_labels?.[v]||`OpenWrt ${v}`,v)));$('version').value=state.catalog.default_version;
    $('metadata-date').textContent=`资料更新 ${new Date(state.catalog.updated).toLocaleDateString()}`;
    const devices=state.catalog.devices.filter(d=>d.version===val('version'));$('device-count').textContent=`${devices.length.toLocaleString()} 个设备档案`;
    let saved=null;try{if(checked('autofill'))saved=JSON.parse(localStorage.getItem('pb-current')||'null');}catch{}
    if(saved)try{await restore(saved);return;}catch{if(saved.version&&!state.catalog.versions.includes(saved.version)){deferredConfig=saved;toast('上次配置使用自动更新版本，连接私有仓库后可恢复；原保存内容未覆盖。');}else toast('原保存配置不适用于当前目录，已恢复默认。');}
    await selectDevice(devices.find(d=>d.target==='x86/64'&&d.id==='generic')||devices[0]);
  }catch(error){notice(`设备目录读取失败：${error.message}。请用 HTTP 服务器打开此网页，不要直接双击 HTML。`,'error');}
}
init().catch(error=>notice(`初始化失败：${error.message}`,'error'));
