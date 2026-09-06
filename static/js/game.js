/**
 * Game screen controller (Alpine.js component).
 *
 * The server owns the answers and the scoring; this component only tracks
 * which tiles have been placed where, and asks the server to judge a word once
 * every blank is filled.
 */
function game(roundId) {
    return {
        roundId,
        words: [],
        currentWordIndex: 0,
        answerBlocks: [],
        tiles: [],
        totalScore: 0,
        lastScore: 0,
        showSuccess: false,
        shaking: false,
        dropTarget: null,
        draggingIndex: null,
        selectedTile: null,
        roundComplete: false,
        wordStartTime: null,

        // Timings must stay in step with the CSS animations in theme.css.
        SUCCESS_MS: 2200,
        SHAKE_MS: 500,

        get progressPct() {
            if (!this.words.length) return 0;
            if (this.roundComplete) return 100;
            return (this.currentWordIndex / this.words.length) * 100;
        },

        /**
         * The "Word N of M" counter. Clamped so a finished round can never
         * read "Word 6 of 5" while the browser is navigating to the summary.
         */
        get displayWordNumber() {
            if (!this.words.length) return 0;
            return Math.min(this.currentWordIndex + 1, this.words.length);
        },

        get currentWord() {
            return this.words[this.currentWordIndex];
        },

        async init() {
            const res = await fetch(`/api/round/${this.roundId}`);
            if (!res.ok) {
                window.location.href = '/';
                return;
            }
            const data = await res.json();
            this.words = data.words;
            this.totalScore = data.total_score || 0;

            // Resume where the player left off: skip the solved run at the front.
            let startIdx = 0;
            while (startIdx < this.words.length && this.words[startIdx].solved) {
                startIdx++;
            }
            this.currentWordIndex = startIdx;

            if (this.currentWordIndex >= this.words.length) {
                this.roundComplete = true;
                this.goToSummary();
                return;
            }
            this.loadWord();
        },

        loadWord() {
            const word = this.currentWord;

            // The first letter is a freebie, shown already placed.
            this.answerBlocks = Array.from({ length: word.length }, (_, i) => ({
                letter: i === 0 ? word.first_letter : '',
                isHint: false,
                tileIndex: null,
            }));

            // ...so remove one copy of it from the tiles the player drags.
            const scrambled = word.scrambled.toUpperCase().split('');
            const firstIdx = scrambled.indexOf(word.first_letter);
            if (firstIdx > -1) scrambled.splice(firstIdx, 1);

            this.tiles = scrambled.map((letter, i) => ({
                id: `${this.currentWordIndex}-${i}`,
                letter,
                used: false,
            }));

            this.selectedTile = null;
            this.shaking = false;
            this.wordStartTime = Date.now();
        },

        // --- placing letters -------------------------------------------------

        canPlaceIn(blockIndex) {
            return blockIndex !== 0 && !this.answerBlocks[blockIndex].letter;
        },

        placeInBlock(tileIndex, blockIndex) {
            const block = this.answerBlocks[blockIndex];
            block.letter = this.tiles[tileIndex].letter;
            block.tileIndex = tileIndex;
            this.tiles[tileIndex].used = true;
            this.selectedTile = null;
            playSfx('pop');
            this.checkIfComplete();
        },

        clickTile(index) {
            if (this.tiles[index].used) return;

            if (this.selectedTile === index) {
                this.selectedTile = null;
                return;
            }
            this.selectedTile = index;

            const target = this.answerBlocks.findIndex(
                (b, i) => i > 0 && !b.letter && !b.isHint
            );
            if (target > -1) this.placeInBlock(index, target);
        },

        dragStart(index, event) {
            if (this.tiles[index].used) return;
            this.draggingIndex = index;
            event.dataTransfer.effectAllowed = 'move';
            // Firefox ignores a drag that carries no data.
            event.dataTransfer.setData('text/plain', String(index));
        },

        dragEnd() {
            this.draggingIndex = null;
            this.dropTarget = null;
        },

        dropOnBlock(blockIndex) {
            if (this.draggingIndex === null || !this.canPlaceIn(blockIndex)) return;
            const tileIndex = this.draggingIndex;
            this.dropTarget = null;
            this.draggingIndex = null;
            this.placeInBlock(tileIndex, blockIndex);
        },

        removeFromBlock(blockIndex) {
            if (blockIndex === 0) return;              // the given first letter
            const block = this.answerBlocks[blockIndex];
            if (!block.letter || block.isHint) return; // hints are not takebacks

            if (block.tileIndex !== null) {
                this.tiles[block.tileIndex].used = false;
            }
            block.letter = '';
            block.tileIndex = null;
        },

        clearPlacedLetters() {
            this.answerBlocks.forEach((block, i) => {
                if (i === 0 || block.isHint || block.tileIndex === null) return;
                this.tiles[block.tileIndex].used = false;
                block.letter = '';
                block.tileIndex = null;
            });
        },

        // --- talking to the server -------------------------------------------

        async post(url, body) {
            const res = await fetch(url, {
                method: 'POST',
                headers: jsonHeaders(),
                body: JSON.stringify(body),
            });
            return res.ok ? res.json() : null;
        },

        async checkIfComplete() {
            if (!this.answerBlocks.every((b) => b.letter)) return;

            const answer = this.answerBlocks.map((b) => b.letter).join('');
            const elapsed = this.wordStartTime
                ? (Date.now() - this.wordStartTime) / 1000
                : 0;

            const data = await this.post('/api/check', {
                round_word_id: this.currentWord.id,
                answer,
                elapsed_seconds: elapsed,
            });
            if (!data) return;

            if (data.correct) {
                this.celebrate(data.score);
            } else {
                this.rejectAnswer();
            }
        },

        celebrate(score) {
            this.lastScore = score;
            this.totalScore += score;
            this.showSuccess = true;
            spawnSparkles(this.$refs.sparkles);
            playSfx('yay');

            setTimeout(() => {
                this.showSuccess = false;
                this.$refs.sparkles.innerHTML = '';
                this.nextWord();
            }, this.SUCCESS_MS);
        },

        rejectAnswer() {
            this.shaking = true;
            setTimeout(() => {
                this.shaking = false;
                this.clearPlacedLetters();
            }, this.SHAKE_MS);
        },

        async getHint() {
            const filled = this.answerBlocks
                .map((b, position) => ({ position, letter: b.letter }))
                .filter((f) => f.letter);

            const data = await this.post('/api/hint', {
                round_word_id: this.currentWord.id,
                filled_positions: filled,
            });
            if (!data || data.position < 0) return;

            const block = this.answerBlocks[data.position];
            if (block.letter && block.tileIndex !== null) {
                this.tiles[block.tileIndex].used = false;
            }
            block.letter = data.letter;
            block.isHint = true;
            block.tileIndex = null;

            // Consume a matching tile so the counts stay honest.
            const tileIdx = this.tiles.findIndex(
                (t) => !t.used && t.letter === data.letter
            );
            if (tileIdx > -1) this.tiles[tileIdx].used = true;

            this.checkIfComplete();
        },

        async skipWord() {
            await this.post('/api/skip', { round_word_id: this.currentWord.id });
            this.nextWord();
        },

        // --- navigation ------------------------------------------------------

        nextWord() {
            // Check before incrementing: stepping the index past the last word
            // would render "Word 6 of 5" for as long as the summary takes to load.
            if (this.currentWordIndex + 1 >= this.words.length) {
                this.roundComplete = true;
                this.goToSummary();
                return;
            }
            this.currentWordIndex++;
            this.loadWord();
        },

        goToSummary() {
            window.location.href = `/summary/${this.roundId}`;
        },
    };
}
