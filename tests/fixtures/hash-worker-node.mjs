// Run the exact browser worker module in a real Node worker for protocol tests.
import {parentPort} from 'node:worker_threads';
globalThis.self={postMessage:data=>parentPort.postMessage(data)};
await import('../../site/lib/hash-worker.js');
parentPort.on('message',data=>self.onmessage({data}));
