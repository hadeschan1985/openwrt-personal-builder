const STATUS={queued:'等待构建资源',requested:'等待受理',pending:'排队中',waiting:'等待 GitHub 放行',in_progress:'正在构建',completed:'已结束'};
const RESULT={success:'构建成功',failure:'构建失败',cancelled:'已取消',timed_out:'执行超时',action_required:'需要处理 GitHub 提示',skipped:'已跳过',neutral:'已结束',stale:'任务已失效',startup_failure:'启动失败'};
export function runStatus(run){return RESULT[run.conclusion]||STATUS[run.status]||'正在确认状态';}
export function stepStatus(step){return step.conclusion==='success'?'已完成':step.conclusion==='failure'?'未通过':runStatus(step);}
export function active(run){return run.status!=='completed'&&!run.conclusion;}
export function latestBuildResults(runs){
  const sorted=[...runs].sort((a,b)=>Number(b.run_number||b.id)-Number(a.run_number||a.id));
  return {latest:sorted[0]||null,success:sorted.find(run=>run.status==='completed'&&run.conclusion==='success')||null};
}
export function requestRun(runs,id){return runs.find(run=>typeof run.display_title==='string'&&run.display_title.endsWith(` · ${id}`));}
export function stageName(name){
  const rebuild={'Restore original input snapshot in a separate transfer process':'读取原版本的归档软件','Inventory public input cache for reproducible rebuild support':'核对本次使用的软件','Capture exact builders packages and fixed sources without generated private files':'整理历史重建所需的软件','Transfer private rebuild inputs to a fresh publication job':'传送私有重建资料','Verify and retain private input snapshots without executing archived sources':'核验并归档构建输入'};
  if(rebuild[name])return rebuild[name];
  if(name==='Upload EFI VMDK disk')return '保存 EFI VMDK 单独下载';
  if(name==='Upload Legacy VMDK disk')return '保存 Legacy VMDK 单独下载';
  if(name==='Verify device firmware containers and file integrity')return '校验本次设备固件文件';
  if(name==='Upload each device image separately')return '逐个保存设备固件下载';
  const delivery={'Verify actual images and selected local services':'验收本次映像启动与本地服务','Prepare delivery manifest':'生成逐文件交付清单','Upload EFI disk':'保存 EFI 映像','Upload Legacy disk':'保存 Legacy 映像','Upload VMDK disks':'保存 VMDK 映像','Upload ROOTFS':'保存 ROOTFS','Upload logs and manifests':'保存日志与校验报告','Upload private record for trusted recorder':'准备私有构建记录','Save private build record without executing upstream code':'保存私有配置与映像记录'};
  if(delivery[name])return delivery[name];
  const translations={'Checkout':'读取构建代码','Python':'准备运行环境','Validate configuration':'检查配置与隐私限制','Install ImageBuilder dependencies':'准备构建工具','Restore verified ImageBuilder download cache':'恢复并校验构建缓存','Build firmware':'检查依赖并生成固件','Upload firmware, manifests and checksums':'保存固件和校验值','Upload failure log':'保存失败日志','Run summary':'生成结果摘要','Set up job':'准备 GitHub 构建环境','Complete job':'收尾'};
  return translations[name]||name.replace(/^Post /,'清理：');
}
export function failureHelp(step,jobs=[]){
  if(!step&&jobs.length&&jobs.every(job=>Array.isArray(job.steps)&&job.steps.length===0)&&jobs.some(job=>job.conclusion==='failure'))return 'GitHub 尚未启动构建步骤。请打开任务页查看账户额度、权限或平台提示；无需修改固件软件包。';
  if(!step)return '请打开 GitHub 日志查看具体原因；失败不会生成可用固件。';
  if(/Restore original input snapshot/.test(step.name))return '原版本归档读取或校验失败。请查看原构建记录、仓库权限及此步骤日志。';
  if(/Capture exact builders|Transfer private rebuild|Verify and retain private input/.test(step.name))return '保存重建资料失败。请查看私有存储容量、传输及此步骤日志，原有归档保留。';
  if(/Validate/.test(step.name))return '配置或私有仓库检查未通过。检查软件包、输出格式和仓库 Secrets 设置。';
  if(/Verify actual images/.test(step.name))return '本次映像启动、后台认证或本地服务验收未通过，不会交付为正式固件。请查看失败检查项；不要直接刷机。';
  if(/dependencies|Python|Checkout|cache/i.test(step.name))return '构建环境或下载准备失败，可能是上游或 GitHub 暂时不可用。请先查看日志，再决定重试。';
  if(/Build firmware/.test(step.name))return '依赖预检、上游下载或映像生成未通过。日志中“依赖预检”后的信息会指出缺包、冲突或下载问题；请勿直接反复提交。';
  if(/Upload/.test(step.name))return '保存产物失败。检查 GitHub 存储配额与日志；不要把此任务当作交付成功。';
  return '请打开 GitHub 日志查看此步骤的具体错误，再决定重试。';
}
export function profileFailureHelp(entry){
  const diagnostic=String(entry?.diagnostic||'').slice(-3000);
  if(/上游构建器或软件包已变化|Upstream changed/.test(diagnostic))return '测试期间上游资源已变更，本轮检查已停止；等待新资源重新同步和编译验收。旧版本的通过记录不会作为新资源的通过结论。';
  if(/IncompleteRead|Connection reset by peer|RemoteDisconnected|Temporary failure in name resolution|(?:connection|read|operation) timed out|HTTP Error (?:408|429|50[0234])/i.test(diagnostic))return '此型号最近检查因上游下载中断或暂时不可用而未完成；尚无本轮编译通过结论。后续检查会重试，无需修改设备或软件配置。';
  const missing=[...new Set([...diagnostic.matchAll(/(?:Cannot install package|cannot find dependency) ([A-Za-z0-9][A-Za-z0-9+_.-]{0,120})/g)].map(match=>match[1].replace(/\.$/,'')))].slice(0,8);
  return missing.length?'此型号默认软件组合编译未通过。当前上游缺少依赖：'+missing.join('、')+'。':'此型号最近一轮默认软件组合编译未通过；请查看具体原因后再提交。';
}
export function artifactInfo(artifact,now=Date.now()){
  const expires=Date.parse(artifact.expires_at),expired=artifact.expired||Number.isFinite(expires)&&expires<=now;
  return {expired,days:Number.isFinite(expires)?Math.max(0,Math.ceil((expires-now)/86400000)):null,
    digest:/^sha256:[a-f0-9]{64}$/i.test(artifact.digest||'')?artifact.digest.slice(7).toLowerCase():null};
}
export {verifyDownload} from './verification.js?v=20261026-8';
