// Hide distribution promotion links only. Preserve text, licenses and source links.
export function promotionLink(value, base) {
  try {
    const url=new URL(value,base);
    return url.protocol==='https:'||url.protocol==='http:' ?
      ['openwrt.ai','dl.openwrt.ai','op.supes.top'].includes(url.hostname.toLowerCase()) : false;
  } catch { return false; }
}
if(typeof document!=='undefined') {
  const hide=()=>{
    for(const anchor of document.querySelectorAll('a[href]')) {
      if(!promotionLink(anchor.getAttribute('href'),document.baseURI))continue;
      const text=document.createElement('span');
      while(anchor.firstChild)text.appendChild(anchor.firstChild);
      anchor.replaceWith(text);
    }
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',hide,{once:true});
  else hide();
  new MutationObserver(hide).observe(document.documentElement,{childList:true,subtree:true});
}
