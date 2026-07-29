/* Pyodide host for blog applets.
 *
 * Runs off the main thread so a slow compute never blocks scrolling or the
 * overlay animation. One worker is shared by every applet on the site: the
 * runtime is downloaded and booted at most once per session, and each applet
 * gets its own Python namespace keyed by id.
 *
 * Results come back as raw float64 buffers, which the main thread hands
 * straight to Plotly as typed arrays -- no JSON, no per-point boxing.
 */

const PYODIDE_VERSION = 'v0.27.2';
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/${PYODIDE_VERSION}/full/`;

// Appended to every applet's source. Turns whatever `compute` returns into
// (buffers, metadata) so the JS side never walks a Python list element by element.
const DISPATCH_PREAMBLE = `
import json as _json
import numpy as _np

def _dispatch(_payload):
    _out = compute(**_json.loads(_payload))
    _buffers, _meta = {}, {}
    for _key, _value in _out.items():
        if isinstance(_value, (str, bool, int, float)) or _value is None:
            _meta[_key] = _value
        else:
            _buffers[_key] = _np.ascontiguousarray(_np.asarray(_value, dtype=_np.float64)).tobytes()
    return _buffers, _json.dumps(_meta)
`;

let pyodide = null;
const namespaces = new Map();   // applet id -> { ns, codeKey }

self.importScripts(`${PYODIDE_URL}pyodide.js`);

async function boot() {
    if (pyodide) return pyodide;
    pyodide = await self.loadPyodide({ indexURL: PYODIDE_URL });
    await pyodide.loadPackage('numpy');
    return pyodide;
}

function register(id, code) {
    const existing = namespaces.get(id);
    if (existing && existing.codeKey === code) return;   // already warm

    if (existing) existing.ns.destroy();
    const ns = pyodide.globals.get('dict')();
    pyodide.runPython(code + DISPATCH_PREAMBLE, { globals: ns });
    namespaces.set(id, { ns, codeKey: code });
}

function compute(id, params) {
    const entry = namespaces.get(id);
    if (!entry) throw new Error(`applet "${id}" was never registered`);

    const dispatch = entry.ns.get('_dispatch');
    let result = null;
    try {
        result = dispatch(JSON.stringify(params));
        const [buffers, metaJson] = result.toJs({ dict_converter: Object.fromEntries });

        const arrays = {};
        const transfer = [];
        for (const [key, bytes] of Object.entries(buffers)) {
            // Copy once into an aligned buffer, then hand ownership to the page.
            const floats = new Float64Array(bytes.slice().buffer);
            arrays[key] = floats;
            transfer.push(floats.buffer);
        }
        return { arrays, meta: JSON.parse(metaJson), transfer };
    } finally {
        if (result) result.destroy();
        dispatch.destroy();
    }
}

self.onmessage = async (event) => {
    const { type, id, reqId, code, params } = event.data;

    try {
        if (type === 'boot') {
            await boot();
            self.postMessage({ type: 'booted', reqId });
            return;
        }

        if (type === 'register') {
            await boot();
            register(id, code);
            self.postMessage({ type: 'registered', id, reqId });
            return;
        }

        if (type === 'compute') {
            const { arrays, meta, transfer } = compute(id, params);
            self.postMessage({ type: 'result', id, reqId, arrays, meta }, transfer);
            return;
        }
    } catch (error) {
        self.postMessage({ type: 'error', id, reqId, message: String(error.message || error) });
    }
};
