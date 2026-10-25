import test from 'node:test';
import assert from 'node:assert/strict';
import {promotionLink} from '../firmware-assets/personal-footer.js';
test('promotion removal preserves official licenses, source and local navigation',()=>{
  const base='http://192.168.1.1/';
  assert.equal(promotionLink('https://openwrt.ai/',base),true);
  for(const url of ['https://github.com/kiddin9/Kwrt','https://openwrt.org','/cgi-bin/luci/','https://not-openwrt.ai','mailto:author@example.com'])assert.equal(promotionLink(url,base),false);
});
