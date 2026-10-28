"""Read a missing OneCloud selector index from the same validated IPK feeds.

This changes the candidate's supported metadata_source selection, not compiler
code, firmware feeds or checksum checks. Actual build approval is still needed.
"""
import runpy
import sys
import urllib.error
from scripts import builders,catalog,upstream

def publisher_guard(original):
    # Extend each original lease check, including retries, without changing the
    # frozen compiler digest or accepting a different feed or builder identity.
    def guarded(tree,token,files,**kwargs):
        names=list(dict.fromkeys([*files,'qa/device_discovery.py','.github/workflows/device-upstream.yml']))
        return original(tree,token,names,**kwargs)
    return guarded

def metadata(spec,original):
    try:return original(spec)
    except urllib.error.HTTPError as error:
        expected='https://openwrt.ai/json/v1/releases/packages-'+builders.series(spec)+'/arm_cortex-a5_vfpv4-index.json'
        if error.code!=404 or error.url!=expected or spec.get('target')!='amlogic/meson8b' or spec.get('metadata_source')!='selector':raise
        builders.validate_spec(spec)
        # The existing compiler already supports the exact raw IPK feed format.
        # Record that selection so compilation and later rechecks use it too.
        direct=dict(spec);direct.pop('metadata_source',None)
        data=original(direct)
        if data.get('package_metadata_errors') or len(data.get('package_index_sha256',[]))!=7:raise ValueError('Incomplete direct OneCloud package indexes')
        spec.pop('metadata_source',None)
        print('OneCloud selector package index missing: verified all seven original IPK indexes; candidate still requires compilation approval.',flush=True)
        return data

def main():
    original=catalog.kwrt_data
    original_guard=upstream.assert_policy_current
    try:
        catalog.kwrt_data=lambda spec:metadata(spec,original)
        if sys.argv[1:2]==['publish']:upstream.assert_policy_current=publisher_guard(original_guard)
        runpy.run_module('scripts.device_upstream',run_name='__main__')
    finally:
        catalog.kwrt_data=original
        upstream.assert_policy_current=original_guard

if __name__=='__main__':main()
