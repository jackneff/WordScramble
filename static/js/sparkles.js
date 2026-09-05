/**
 * Celebration particles, shared by the game and summary screens.
 */
(function () {
    const COLORS = [
        '#ff6b6b', '#ffa94d', '#ffe066', '#69db7c', '#66d9e8',
        '#74c0fc', '#f783ac', '#da77f2', '#ffd700', '#ffffff',
    ];

    const BURST_COUNT = 40;
    const STAR_COUNT = 15;

    function randomColor() {
        return COLORS[Math.floor(Math.random() * COLORS.length)];
    }

    function burst(container, originX, originY) {
        for (let i = 0; i < BURST_COUNT; i++) {
            const el = document.createElement('div');
            el.className = 'sparkle-particle';

            const size = 6 + Math.random() * 14;
            const angle = (Math.PI * 2 * i) / BURST_COUNT + (Math.random() - 0.5) * 0.5;
            const distance = 150 + Math.random() * 300;
            const color = randomColor();

            el.style.cssText = `
                width: ${size}px; height: ${size}px;
                left: ${originX}px; top: ${originY}px;
                background: ${color};
                box-shadow: 0 0 ${size}px ${color};
                --dx: ${Math.cos(angle) * distance}px;
                --dy: ${Math.sin(angle) * distance - 100}px;
                animation-duration: ${0.8 + Math.random() * 0.8}s;
                animation-delay: ${Math.random() * 0.2}s;
            `;
            container.appendChild(el);
        }
    }

    function stars(container, spread) {
        for (let i = 0; i < STAR_COUNT; i++) {
            const el = document.createElement('div');
            el.className = 'sparkle-star';

            const size = 16 + Math.random() * 24;
            const color = randomColor();

            el.style.cssText = `
                width: ${size}px; height: ${size}px;
                left: ${Math.random() * window.innerWidth}px;
                top: ${Math.random() * window.innerHeight * spread}px;
                color: ${color};
                filter: drop-shadow(0 0 ${size / 2}px ${color});
                animation-duration: ${0.6 + Math.random() * 0.8}s;
                animation-delay: ${0.1 + Math.random() * 0.4}s;
            `;
            container.appendChild(el);
        }
    }

    /**
     * @param {HTMLElement} container
     * @param {{originY?: number, spread?: number, clearAfter?: number}} options
     */
    function spawnSparkles(container, options) {
        if (!container) return;
        const opts = options || {};
        const originY = window.innerHeight * (opts.originY || 0.5);

        burst(container, window.innerWidth / 2, originY);
        stars(container, opts.spread || 0.7);

        if (opts.clearAfter) {
            setTimeout(() => { container.innerHTML = ''; }, opts.clearAfter);
        }
    }

    window.spawnSparkles = spawnSparkles;
})();
