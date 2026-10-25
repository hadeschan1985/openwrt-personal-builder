const API='https://api.github.com';
export function repositoryName(value) {
  if(!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\/[A-Za-z0-9_.-]+$/.test(value))throw new Error('仓库格式应为 owner/repository。');
  return value;
}
export class GitHub {
  constructor(repo,token,ref='main',fetcher=(...args)=>fetch(...args)) {
    this.repo=repositoryName(repo);this.token=token;this.ref=ref;this.fetcher=fetcher;
    if(!/^[A-Za-z0-9_./-]+$/.test(ref)||ref.includes('..'))throw new Error('分支名无效。');
  }
  async request(path,options={}) {
    const headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28',...(options.body?{'Content-Type':'application/json'}:{})};
    if(this.token)headers.Authorization=`Bearer ${this.token}`;
    let r;
    try{r=await this.fetcher(`${API}/repos/${this.repo}${path}`,{...options,headers,cache:'no-store',signal:options.signal??AbortSignal.timeout(90000)});}
    catch(error){if(['AbortError','TimeoutError'].includes(error.name))throw new Error('GitHub 响应超时。先查看构建记录，确认是否已提交，再决定重试。');throw error;}
    if(!r.ok){const explanations={401:'授权令牌无效或已到期，请重新连接。',403:'权限不足、请求限额或 GitHub 策略限制，请检查授权与 GitHub 提示。',404:'仓库或任务不存在，或当前授权没有访问权限。',410:'构建产物已到期，请重新构建。',422:'配置、分支或工作流输入不符合 GitHub 要求。'};const error=new Error(`GitHub ${r.status}：${explanations[r.status]||'请求失败，请稍后检查 GitHub 状态。'}`);error.status=r.status;throw error;}
    return r.status===204?null:r.json();
  }
  async connect(){const data=await this.request('');this.private=data.private;this.defaultBranch=data.default_branch;return data;}
  async dispatch(config,requestId) {
    if(!this.token)throw new Error('直接启动构建需要仓库 Actions 写入授权。');
    const serialized=JSON.stringify(config);
    if(new TextEncoder().encode(serialized).length>60000)throw new Error('配置超过 60 KB。');
    await this.request('/actions/workflows/build.yml/dispatches',{method:'POST',body:JSON.stringify({ref:this.ref,inputs:{config_json:serialized,request_id:requestId}})});
  }
  runs(){return this.request('/actions/workflows/build.yml/runs?per_page=12');}
  upstreamRuns(){return this.request('/actions/workflows/upstream.yml/runs?per_page=1');}
  async approvedUpstream(){
    let file=await this.request(`/contents/updates/approved.json?ref=${encodeURIComponent(this.ref)}`);
    if(!Number.isInteger(file.size)||file.size<1||file.size>4*1024*1024)throw new Error('上游版本资料大小无效。');
    // Large Contents responses omit base64. Stay on the same GitHub API host;
    // never follow a download_url with the session credential.
    if(file.encoding==='none'&&/^[a-f0-9]{40}$/.test(file.sha))file=await this.request(`/git/blobs/${file.sha}`);
    if(file.encoding!=='base64'||typeof file.content!=='string'||file.content.length>6*1024*1024)throw new Error('上游版本资料格式无效。');
    return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(atob(file.content.replace(/\s/g,'')),c=>c.charCodeAt(0))));
  }
  artifacts(runId){if(!/^\d+$/.test(String(runId)))throw new Error('任务 ID 无效');return this.request(`/actions/runs/${runId}/artifacts`);}
  jobs(runId){if(!/^\d+$/.test(String(runId)))throw new Error('任务 ID 无效');return this.request(`/actions/runs/${runId}/jobs?per_page=100`);}
  async upload(file) {
    if(!this.private)throw new Error('文件包只能上传到已连接的私有构建仓库。');
    if(file.size>12*1024*1024)throw new Error('文件包不能超过 12 MiB。');
    const name=file.name.toLowerCase();
    const extension=name.endsWith('.tar.gz')?'tar.gz':name.split('.').pop();
    if(!['zip','tgz','tar.gz','7z'].includes(extension))throw new Error('目前支持 ZIP/TAR.GZ/TGZ/7Z。');
    const bytes=new Uint8Array(await file.arrayBuffer());
    const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');
    const path=`overlays/${hash.slice(0,24)}.${extension}`;
    let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
    let exists=false;try{const old=await this.request(`/contents/${path}?ref=${encodeURIComponent(this.ref)}`);exists=Boolean(old.sha);}catch(error){if(!error.message.startsWith('GitHub 404'))throw error;}
    if(!exists)await this.request(`/contents/${path}`,{method:'PUT',body:JSON.stringify({message:'Add personal firmware overlay',content:btoa(binary),branch:this.ref})});
    return path;
  }
}
