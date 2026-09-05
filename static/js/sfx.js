/**
 * Sound effects.
 *
 * Uses the Web Audio API so repeated effects fire without the scheduling lag
 * an <audio> element has, and falls back to HTMLAudioElement until the buffers
 * have finished decoding (or if Web Audio is unavailable).
 */
(function () {
    const elements = {};
    const buffers = {};
    let ctx = null;

    try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx) ctx = new AudioCtx();
    } catch (err) {
        ctx = null;
    }

    /** @param {Record<string, string>} files name -> URL */
    function loadSounds(files) {
        Object.entries(files).forEach(([name, url]) => {
            const el = new Audio(url);
            el.preload = 'auto';
            el.load();
            elements[name] = el;

            if (!ctx) return;
            fetch(url)
                .then((r) => r.arrayBuffer())
                .then((data) => ctx.decodeAudioData(data))
                .then((decoded) => { buffers[name] = decoded; })
                .catch(() => { /* fall back to the <audio> element */ });
        });
    }

    function playSfx(name) {
        if (ctx && ctx.state === 'suspended') ctx.resume();

        const buffer = ctx && buffers[name];
        if (buffer) {
            const source = ctx.createBufferSource();
            source.buffer = buffer;
            source.connect(ctx.destination);
            source.start(0);
            return;
        }

        const el = elements[name];
        if (el) {
            el.currentTime = 0;
            el.play().catch(() => { /* autoplay blocked until first gesture */ });
        }
    }

    window.loadSounds = loadSounds;
    window.playSfx = playSfx;
})();
