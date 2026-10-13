// Pure selection state: imports no GNOME APIs so it can be tested outside Shell.
export class SelectionTracker {
    constructor(delay = 1000) {
        this.delay = delay;
        this.suspend();
    }

    suspend() {
        this.priming = true;
        this.current = '';
        this.emitted = '';
        this.changedAt = 0;
    }

    cancelCurrent() {
        this.emitted = this.current;
    }

    feed(text, now, dragging = false) {
        text = (text ?? '').trim();
        if (this.priming) {
            this.current = this.emitted = text;
            this.changedAt = now;
            this.priming = false;
            return null;
        }
        if (dragging) {
            this.emitted = '';
            this.current = '';
            this.changedAt = now;
            return null;
        }
        if (text !== this.current) {
            this.current = text;
            this.changedAt = now;
            if (!text)
                this.emitted = '';
            return null;
        }
        if (text && text !== this.emitted && now - this.changedAt >= this.delay) {
            this.emitted = text;
            return text;
        }
        return null;
    }
}
