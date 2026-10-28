"""Exercise real public metadata discovery without compiling or approving it."""
import os
from scripts import catalog,device_upstream as d
from scripts.build import require
from qa.device_discovery import metadata

original=catalog.kwrt_data
try:
    catalog.kwrt_data=lambda spec:metadata(spec,original)
    candidate=d.discover();entry=candidate['targets']['amlogic/meson8b']
    require(entry['spec'].get('metadata_source') is None,'OneCloud did not select the original raw IPK feeds')
    require(entry['spec'].get('source_cache')=='onecloud-author-20261012','Original verified author builder binding changed')
    require(len(entry['metadata']['package_index_sha256'])==7,'Missing original package indexes')
    repeated=original(entry['spec'])
    require(d.digest(repeated)==d.digest(entry['metadata']),'Direct metadata recheck changed; retain existing approved release')
    report={'schema_version':1,'status':'passed','scope':'real-public-metadata-discovery-only','run_id':os.environ['GITHUB_RUN_ID'],'source_commit':os.environ['GITHUB_SHA'],'policy_sha256':candidate['policy_sha256'],'platforms':len(candidate['targets']),'non_x86_profiles':sum(len(e['metadata']['profiles']['profiles']) for e in candidate['targets'].values()),'onecloud':{'builder_sha256':entry['spec']['sha256'],'source_cache':entry['spec']['source_cache'],'packages':len(entry['metadata']['packages']),'package_indexes':len(entry['metadata']['package_index_sha256']),'metadata_sha256':d.digest(entry['metadata']),'target_fingerprint':d.target_fingerprint(entry),'repeat_read_identical':True},'firmware_compiled':False,'approved':False,'hardware_tested':False}
    d.write('work/device-discovery-report.json',report)
    print('DEVICE_DISCOVERY_RESULT='+d.canonical(report),flush=True)
finally:catalog.kwrt_data=original
