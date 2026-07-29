/* Interactive applets for blog posts.
 *
 * A post declares an applet with a fenced ```applet block. Two runtimes:
 *
 *   runtime: precomputed  -- Python ran at build time, the browser only picks a
 *                            frame out of a JSON table. Instant, no dependency.
 *   runtime: pyodide      -- real CPython + numpy in a worker, booted on demand.
 *
 * Everything heavy (Plotly, Pyodide) is fetched lazily and only once per
 * session, so a post without applets costs nothing.
 */

window.Applets = (function () {
    'use strict';

    const PLOTLY_SRC = 'https://cdn.plot.ly/plotly-basic-3.0.1.min.js';
    const PLOT_CONFIG = { displayModeBar: false, responsive: true };
    const BASE_LAYOUT = {
        margin: { l: 52, r: 16, t: 8, b: 44 },
        font: { family: "'Space Grotesk', sans-serif", size: 12, color: '#1a1a1a' },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        showlegend: false,
        hovermode: 'closest',
        xaxis: { zeroline: false, gridcolor: '#f0f0f0', linecolor: '#e5e5e5' },
        yaxis: { zeroline: false, gridcolor: '#f0f0f0', linecolor: '#e5e5e5' }
    };
    const PALETTE = ['#1a1a1a', '#c0392b', '#999999'];

    // Resolved against this script, so the worker is found wherever blog.html lives.
    const SCRIPT_URL = document.currentScript ? document.currentScript.src : window.location.href;

    const live = [];             // applets currently mounted, for teardown
    let plotlyPromise = null;
    let worker = null;
    let workerBooted = null;

    // ---------------------------------------------------------------- loading

    function loadPlotly() {
        if (!plotlyPromise) {
            plotlyPromise = new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.src = PLOTLY_SRC;
                script.onload = () => resolve(window.Plotly);
                script.onerror = () => reject(new Error('could not load plotly'));
                document.head.appendChild(script);
            });
        }
        return plotlyPromise;
    }

    const pending = new Map();
    let reqCounter = 0;

    function getWorker() {
        if (!worker) {
            worker = new Worker(new URL('pyodide-worker.js', SCRIPT_URL));
            worker.onmessage = (event) => {
                const settle = pending.get(event.data.reqId);
                if (settle) settle(event.data);
            };
            // Without this, a worker that never starts leaves every caller hanging.
            worker.onerror = (event) => {
                const message = event.message || 'python worker failed to start';
                pending.forEach(settle => settle({ type: 'error', message: message }));
                pending.clear();
            };
        }
        return worker;
    }

    // Promise wrapper over the worker's message protocol. Every reply echoes reqId.
    function ask(message) {
        const target = getWorker();
        const reqId = ++reqCounter;
        return new Promise((resolve, reject) => {
            pending.set(reqId, (data) => {
                pending.delete(reqId);
                if (data.type === 'error') reject(new Error(data.message));
                else resolve(data);
            });
            target.postMessage(Object.assign({ reqId: reqId }, message));
        });
    }

    function bootWorker() {
        if (!workerBooted) workerBooted = ask({ type: 'boot' });
        return workerBooted;
    }

    // ----------------------------------------------------------------- parser

    // Header is `key: value` lines; everything after a lone `---` is Python.
    function parseSpec(source) {
        const lines = source.split('\n');
        const spec = { controls: [], traces: [] };
        let i = 0;

        for (; i < lines.length; i++) {
            const line = lines[i].trim();
            if (line === '---') { i++; break; }
            if (!line) continue;

            const split = line.indexOf(':');
            if (split === -1) continue;
            const key = line.slice(0, split).trim();
            const value = line.slice(split + 1).trim();

            if (key === 'control') {
                const [name, label, min, max, step, initial] = value.split('|').map(s => s.trim());
                spec.controls.push({
                    name: name,
                    label: label,
                    min: parseFloat(min),
                    max: parseFloat(max),
                    step: parseFloat(step),
                    value: parseFloat(initial)
                });
            } else if (key === 'trace') {
                const [name, x, y, mode] = value.split('|').map(s => s.trim());
                spec.traces.push({ name: name, x: x, y: y, mode: mode || 'lines' });
            } else {
                spec[key] = value;
            }
        }

        spec.code = lines.slice(i).join('\n').trim();
        return spec;
    }

    function numberList(value) {
        return String(value || '').split(',').map(v => parseFloat(v.trim())).filter(v => !isNaN(v));
    }

    // -------------------------------------------------------------------- UI

    function buildShell(spec) {
        const root = document.createElement('figure');
        root.className = 'applet';
        root.innerHTML = `
            <figcaption class="applet-head">
                <span class="applet-title"></span>
                <span class="applet-badge"></span>
            </figcaption>
            <div class="applet-plot" style="height:${parseInt(spec.height, 10) || 360}px"></div>
            <div class="applet-controls"></div>
            <div class="applet-status" role="status"></div>`;

        root.querySelector('.applet-title').textContent = spec.title || 'applet';
        root.querySelector('.applet-badge').textContent =
            spec.runtime === 'pyodide' ? 'python · live' : 'python · precomputed';
        return root;
    }

    function buildSlider(control, onInput) {
        const row = document.createElement('label');
        row.className = 'applet-control';
        row.innerHTML = `
            <span class="applet-control-label"></span>
            <input type="range" class="applet-slider">
            <output class="applet-control-value"></output>`;

        const slider = row.querySelector('.applet-slider');
        const output = row.querySelector('.applet-control-value');
        slider.min = control.min;
        slider.max = control.max;
        slider.step = control.step;
        slider.value = control.value;
        row.querySelector('.applet-control-label').textContent = control.label || control.name;

        const decimals = (String(control.step).split('.')[1] || '').length;
        const paint = () => { output.textContent = parseFloat(slider.value).toFixed(decimals); };
        paint();

        slider.addEventListener('input', () => { paint(); onInput(parseFloat(slider.value)); });
        return { row: row, slider: slider, setDisabled: (on) => { slider.disabled = on; } };
    }

    // --------------------------------------------------- tier 1: precomputed

    async function mountPrecomputed(root, spec) {
        const status = root.querySelector('.applet-status');
        const plot = root.querySelector('.applet-plot');
        status.textContent = 'loading data…';

        const [Plotly, data] = await Promise.all([
            loadPlotly(),
            fetch(spec.data).then(res => {
                if (!res.ok) throw new Error(`${spec.data} → HTTP ${res.status}`);
                return res.json();
            })
        ]);

        const control = data.control;
        const layout = Object.assign({}, BASE_LAYOUT, {
            xaxis: Object.assign({}, BASE_LAYOUT.xaxis, { title: { text: data.xaxis || '' } }),
            yaxis: Object.assign({}, BASE_LAYOUT.yaxis, {
                title: { text: data.yaxis || '' },
                range: data.yrange
            })
        });

        // One trace, drawn once. Slider moves only pick a different y vector.
        let index = Math.floor(control.values.length / 2);
        await Plotly.newPlot(plot, [{
            x: Float64Array.from(data.x),
            y: Float64Array.from(data.frames[index]),
            mode: 'lines',
            line: { color: PALETTE[0], width: 2 },
            name: data.trace || ''
        }], layout, PLOT_CONFIG);

        const describe = () => {
            status.textContent = `${control.label} = ${control.values[index].toFixed(2)}` +
                ` · frame ${index + 1}/${control.values.length} · no python at runtime`;
        };

        const slider = buildSlider({
            name: control.name,
            label: control.label,
            min: 0,
            max: control.values.length - 1,
            step: 1,
            value: index
        }, (raw) => {
            index = raw;
            // restyle mutates the existing trace in place: no relayout, no rebuild.
            Plotly.restyle(plot, { y: [Float64Array.from(data.frames[index])] }, [0]);
            describe();
        });

        // The slider shows the frame index; the readout below carries the real value.
        slider.row.querySelector('.applet-control-value').style.display = 'none';
        root.querySelector('.applet-controls').appendChild(slider.row);
        describe();

        live.push({ root: root, plot: plot });
    }

    // -------------------------------------------------------- tier 2: pyodide

    async function mountPyodide(root, spec) {
        const status = root.querySelector('.applet-status');
        const plot = root.querySelector('.applet-plot');
        const controlsHost = root.querySelector('.applet-controls');

        const params = {};
        spec.controls.forEach(c => { params[c.name] = c.value; });

        const instance = { root: root, plot: plot, cancelled: false };
        live.push(instance);

        const sliders = spec.controls.map(control => buildSlider(control, (value) => {
            params[control.name] = value;
            schedule();
        }));
        sliders.forEach(s => { s.setDisabled(true); controlsHost.appendChild(s.row); });

        const start = document.createElement('button');
        start.type = 'button';
        start.className = 'applet-start';
        start.textContent = 'start python runtime';
        controlsHost.appendChild(start);

        status.textContent = 'cpython + numpy, ~10 MB, fetched only if you ask for it';

        // Latest-wins: a drag never queues up work it is about to invalidate.
        let queued = null;
        let running = false;

        function schedule() {
            queued = Object.assign({}, params);
            if (!running) drain();
        }

        async function drain() {
            running = true;
            while (queued && !instance.cancelled) {
                const request = queued;
                queued = null;
                try {
                    const started = performance.now();
                    const response = await ask({ type: 'compute', id: spec.id, params: request });
                    if (instance.cancelled) break;
                    draw(response.arrays, response.meta, performance.now() - started);
                } catch (error) {
                    status.textContent = `error: ${error.message}`;
                    status.classList.add('applet-status-error');
                    break;
                }
            }
            running = false;
        }

        function draw(arrays, meta, elapsed) {
            const traces = spec.traces.map((trace, i) => ({
                x: arrays[trace.x],
                y: arrays[trace.y],
                mode: trace.mode,
                name: trace.name,
                line: { color: PALETTE[i % PALETTE.length], width: i === 0 ? 3 : 1.5 },
                marker: { color: PALETTE[i % PALETTE.length], size: 7 }
            }));

            // react() diffs against what is on screen instead of tearing it down.
            window.Plotly.react(plot, traces, instance.layout, PLOT_CONFIG);
            status.textContent = (meta.status ? meta.status + ' · ' : '') +
                `computed in ${elapsed.toFixed(1)} ms`;
        }

        async function begin() {
            start.disabled = true;
            start.textContent = 'booting…';
            if (!workerBooted) status.textContent = 'downloading cpython + numpy…';

            try {
                const Plotly = await loadPlotly();
                await bootWorker();
                if (instance.cancelled) return;
                await ask({ type: 'register', id: spec.id, code: spec.code });

                instance.layout = Object.assign({}, BASE_LAYOUT, {
                    xaxis: Object.assign({}, BASE_LAYOUT.xaxis, {
                        title: { text: spec.xaxis || '' },
                        range: numberList(spec.xrange).length === 2 ? numberList(spec.xrange) : undefined
                    }),
                    yaxis: Object.assign({}, BASE_LAYOUT.yaxis, {
                        title: { text: spec.yaxis || '' },
                        range: numberList(spec.yrange).length === 2 ? numberList(spec.yrange) : undefined,
                        // Equal aspect: shrink the drawing area rather than fight the range.
                        scaleanchor: spec.equal === 'true' ? 'x' : undefined,
                        constrain: spec.equal === 'true' ? 'domain' : undefined
                    })
                });

                await Plotly.newPlot(plot, [], instance.layout, PLOT_CONFIG);
                start.remove();
                sliders.forEach(s => s.setDisabled(false));
                schedule();
            } catch (error) {
                start.disabled = false;
                start.textContent = 'retry';
                status.textContent = `error: ${error.message}`;
                status.classList.add('applet-status-error');
            }
        }

        start.addEventListener('click', begin);

        // Runtime already warm from an earlier post: skip the gate entirely.
        if (workerBooted) begin();
    }

    // ------------------------------------------------------------- public API

    function mount(container) {
        const blocks = container.querySelectorAll('pre code.language-applet');

        blocks.forEach(block => {
            const spec = parseSpec(block.textContent);
            const root = buildShell(spec);
            block.parentNode.replaceWith(root);

            const runtime = spec.runtime === 'pyodide' ? mountPyodide : mountPrecomputed;
            runtime(root, spec).catch(error => {
                const status = root.querySelector('.applet-status');
                status.textContent = `error: ${error.message}`;
                status.classList.add('applet-status-error');
            });
        });
    }

    // Called when the post closes. Plots are torn down, but the Python worker
    // stays warm so reopening a post is instant.
    function unmountAll() {
        live.forEach(instance => {
            instance.cancelled = true;
            if (window.Plotly && instance.plot) window.Plotly.purge(instance.plot);
        });
        live.length = 0;
    }

    return { mount: mount, unmountAll: unmountAll };
})();
