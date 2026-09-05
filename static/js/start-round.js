/**
 * Shared Alpine mixin for the "start a round" buttons on the home and
 * challenge screens.
 */
function roundStarter() {
    return {
        loading: false,
        error: '',

        async start(size, mode = 'normal') {
            if (this.loading) return;
            this.loading = true;
            this.error = '';

            try {
                const res = await fetch('/api/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ round_size: size, mode }),
                });
                if (!res.ok) throw new Error('Could not start the round');

                const data = await res.json();
                window.location.href = `/game/${data.round_id}`;
            } catch (err) {
                this.error = 'Something went wrong. Please try again.';
                this.loading = false;
            }
        },
    };
}
