const API='https://api.github.com';
export function repositoryName(value) {
  if(!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\/[A-Za-z0-9_.-]+$/.test(value))throw new Error('仓库格式应为 owner/repository。');
  return value;
}
export class GitHub {
  constructor(repo,token,ref='main',fetcher=(...args)=>fetch(...args)) {
    this.repo=repositoryName(repo);this.token=token;this.ref=ref;this.fetcher=fetcher;this.controller=new AbortController();this.closed=false;this.blocked='';this.retryAt=0;this.rateStrikes=0;
    if(!/^[A-Za-z0-9_./-]+$/.test(ref)||ref.includes('..'))throw new Error('分支名无效。');
  }
  async request(path,options={}) {
    if(this.closed)throw new Error('此页授权已断开；已受理的构建不会因此取消。');
    if(!this.canQuery)throw this.pauseError();
    const headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28',...(options.body?{'Content-Type':'application/json'}:{})};
    if(this.token)headers.Authorization=`Bearer ${this.token}`;
    let r;
    try{r=await this.fetcher(`${API}/repos/${this.repo}${path}`,{...options,headers,cache:'no-store',signal:AbortSignal.any([this.controller.signal,options.signal??AbortSignal.timeout(90000)])});}
    catch(error){if(this.closed)throw new Error('此页授权已断开；请求可能已经受理，重连后先查看记录。');if(this.blocked)throw this.pauseError();if(['AbortError','TimeoutError'].includes(error.name))throw new Error('GitHub 响应超时。先查看构建记录，确认是否已提交，再决定重试。');throw error;}
    if(this.closed)throw new Error('此页授权已断开；不会载入旧会话的结果。');
    if(this.blocked)throw this.pauseError();
    const remaining=r.headers?.get('x-ratelimit-remaining'),reset=r.headers?.get('x-ratelimit-reset'),retry=r.headers?.get('retry-after');
    if(remaining!==null&&remaining!==undefined&&remaining!=='')this.rateRemaining=Number(remaining);
    if(!r.ok){
      let body;try{body=await r.json();}catch{}
      const limited=r.status===429||r.status===403&&(remaining==='0'||retry!=null||/rate limit/i.test(body?.message||''));
      if(limited){
        this.rateStrikes++;
        const delay=retry&&/^\d+$/.test(retry)?Date.now()+Number(retry)*1000:retry?Date.parse(retry):NaN;
        const resetAt=remaining==='0'&&Number(reset)>0?Number(reset)*1000:0;
        this.retryAt=Math.max(Date.now()+1000,Number.isFinite(delay)?delay:0,resetAt||(!Number.isFinite(delay)?Date.now()+60000*2**Math.min(this.rateStrikes-1,5):0))+1000;
        if(this.rateStrikes>=4)this.blocked='多次遇到 GitHub 请求限额，已暂停自动读取。请稍后重新连接；构建不会自动重提交。';
        throw this.pauseError(r.status);
      }
      if(r.status===401){this.token='';this.blocked='授权令牌无效或已到期，已停止自动读取，请重新连接。';this.controller.abort();throw this.pauseError(401);}
      if(r.status===403){this.blocked='当前授权权限不足或受 GitHub 策略限制，已停止自动读取。请检查私有构建仓库的授权后重新连接。';this.controller.abort();throw this.pauseError(403);}
      const explanations={404:'仓库或任务不存在，或当前授权没有访问权限。',410:'构建产物已到期，请重新构建。',422:'配置、分支或工作流输入不符合 GitHub 要求。'};const error=new Error(`GitHub ${r.status}：${explanations[r.status]||'请求失败，请稍后检查 GitHub 状态。'}`);error.status=r.status;throw error;
    }
    const expires=r.headers?.get('github-authentication-token-expiration');if(expires)this.tokenExpiresAt=expires;
    if(remaining==='0')this.retryAt=Math.max(Date.now()+60000,Number(reset)*1000||0)+1000;
    let data;try{data=r.status===204?null:await r.json();}catch{throw new Error(this.closed?'此页授权已断开；不会载入旧会话的结果。':'GitHub 返回资料格式无效，请稍后重新连接。');}
    if(this.closed)throw new Error('此页授权已断开；不会载入旧会话的结果。');
    if(this.blocked)throw this.pauseError();
    return data;
  }
  get canQuery(){return !this.closed&&!this.blocked&&Date.now()>=this.retryAt;}
  get pollDelay(){return this.closed||this.blocked?Infinity:Math.max(0,this.retryAt-Date.now());}
  pauseError(status){const error=new Error(this.blocked||`GitHub 请求额度暂时用尽，暂停到 ${new Date(this.retryAt).toLocaleTimeString()} 后再读取；不会自动重提交构建。`);error.status=status|| (this.blocked?403:429);return error;}
  close(){this.closed=true;this.token='';this.controller.abort();}
  async connect(){const data=await this.request('');this.private=data.private;this.defaultBranch=data.default_branch;return data;}
  async dispatch(config,requestId,rebuildRunId=null) {
    if(!this.token)throw new Error('直接启动构建需要仓库 Actions 写入授权。');
    const serialized=JSON.stringify(config);
    if(new TextEncoder().encode(serialized).length>60000)throw new Error('配置超过 60 KB。');
    if(rebuildRunId!==null&&!/^[1-9][0-9]{0,19}$/.test(String(rebuildRunId)))throw new Error('历史重建编号无效。');
    const inputs={config_json:serialized,request_id:requestId};if(rebuildRunId!==null)inputs.rebuild_run_id=String(rebuildRunId);
    await this.request('/actions/workflows/build.yml/dispatches',{method:'POST',body:JSON.stringify({ref:this.ref,inputs})});
  }
  runs(page=1){if(!Number.isInteger(page)||page<1||page>1000)throw new Error('历史页码无效。');return this.request(`/actions/workflows/build.yml/runs?per_page=12&page=${page}`);}
  latestSuccess(){return this.request('/actions/workflows/build.yml/runs?status=success&per_page=10');}
  releases(){return this.request('/releases?per_page=100');}
  buildRecord(runId){if(!/^\d+$/.test(String(runId)))throw new Error('任务 ID 无效');return this.readJSON(`records/${runId}.json`,256*1024);}
  async archive(runId){
    if(!this.private||!this.token)throw new Error('私有收藏需要已授权的私有仓库。');
    if(!/^\d+$/.test(String(runId)))throw new Error('任务 ID 无效');
    await this.request('/actions/workflows/archive.yml/dispatches',{method:'POST',body:JSON.stringify({ref:this.ref,inputs:{run_id:String(runId)}})});
  }
  archiveRuns(){return this.request('/actions/workflows/archive.yml/runs?per_page=3');}
  async readJSON(path,limit=4*1024*1024,expectedSHA=null){
    const standard=/^(updates\/(?:approved|devices-approved|box-approved)|records\/\d+)\.json$/;
    const release=/^updates\/device-catalogs\/kwrt-\d{2}\.\d{2}-\d{8}-[a-f0-9]{8}\.json$/;
    const metadata=/^updates\/device-metadata\/[a-f0-9]{64}\/[a-z0-9_-]+\/[a-z0-9_-]+\.json$/;
    const box=/^updates\/box-catalogs\/box-\d{8}-[a-f0-9]{8}\.json$/;
    if(!standard.test(path)&&!release.test(path)&&!metadata.test(path)&&!box.test(path))throw new Error('资料路径无效。');
    if(expectedSHA!==null&&!/^[a-f0-9]{64}$/.test(expectedSHA))throw new Error('资料校验值无效。');
    let file=await this.request(`/contents/${path}?ref=${encodeURIComponent(this.ref)}`);
    if(!Number.isInteger(file.size)||file.size<1||file.size>limit)throw new Error('上游版本资料大小无效。');
    const size=file.size;
    if(file.encoding==='none'&&/^[a-f0-9]{40}$/.test(file.sha))file=await this.request(`/git/blobs/${file.sha}`);
    if(file.encoding!=='base64'||typeof file.content!=='string'||file.content.length>6*1024*1024)throw new Error('上游版本资料格式无效。');
    const bytes=Uint8Array.from(atob(file.content.replace(/\s/g,'')),c=>c.charCodeAt(0));
    if(expectedSHA!==null){
      const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');
      if(bytes.length!==size||hash!==expectedSHA)throw new Error('设备资料 SHA256 不一致，未加载此更新。');
    }
    if(this.closed)throw new Error('此页授权已断开；不会载入旧会话的结果。');
    if(this.blocked)throw this.pauseError();
    return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
  }
  upstreamRuns(){return this.request('/actions/workflows/upstream.yml/runs?per_page=1');}
  async approvedUpstream(){
    return this.readJSON('updates/approved.json');
  }
  deviceApproved(){return this.readJSON('updates/devices-approved.json');}
  deviceRelease(version){if(!/^kwrt-\d{2}\.\d{2}-\d{8}-[a-f0-9]{8}$/.test(version))throw new Error('设备更新版本无效。');return this.readJSON(`updates/device-catalogs/${version}.json`);}
  deviceUpstreamRuns(){return this.request('/actions/workflows/device-upstream.yml/runs?per_page=1');}
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
