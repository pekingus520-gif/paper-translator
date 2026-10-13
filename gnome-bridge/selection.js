// Only a real drag that changes PRIMARY can start automatic translation.
export class SelectionTracker {
    constructor(delay = 1000, minimumDrag = 8) {
        this.delay = delay;
        this.minimumDragSquared = minimumDrag * minimumDrag;
        this.suspend();
    }

    suspend() {
        this.priming = true;
        this.current = '';
        this.drag = null;
        this.awaitingUntil = 0;
        this.pending = '';
        this.pendingSince = 0;
        this.copied = '';
        this.copyBlocked = false;
    }

    cancelCurrent() {
        this.cancelText(this.pending || this.current);
    }

    cancelText(text) {
        this.copyBlocked = true;
        this.copied = (text ?? '').trim() || this.pending || this.current;
        this.pending = '';
        this.awaitingUntil = 0;
    }

    feed(text, now, dragging = false, point = null) {
        text = (text ?? '').trim();
        if (this.priming && !dragging) {
            this.current = text;
            this.priming = false;
            return null;
        }
        if (dragging) {
            if (!this.drag) {
                this.drag = {baseline: this.current, start: point, moved: false};
                this.copyBlocked = false;
                this.pending = '';
                this.awaitingUntil = 0;
            } else if (point && this.drag.start) {
                const dx = point.x - this.drag.start.x;
                const dy = point.y - this.drag.start.y;
                if (dx * dx + dy * dy >= this.minimumDragSquared)
                    this.drag.moved = true;
            }
            return null;
        }
        if (this.drag) {
            const gesture = this.drag;
            this.drag = null;
            this.awaitingUntil = gesture.moved && !this.copyBlocked ? now + 500 : 0;
            this.pending = '';
            if (text && text !== gesture.baseline && text !== this.copied &&
                gesture.moved && !this.copyBlocked) {
                this.pending = text;
                this.pendingSince = now;
                this.awaitingUntil = 0;
                this.copied = '';
            }
            this.current = text;
            return null;
        }
        if (text !== this.current) {
            if (this.awaitingUntil && now <= this.awaitingUntil && text &&
                text !== this.copied && !this.copyBlocked) {
                this.pending = text;
                this.pendingSince = now;
                this.copied = '';
            } else {
                this.pending = '';
            }
            this.current = text;
            this.awaitingUntil = 0;
            return null;
        }
        if (this.awaitingUntil && now > this.awaitingUntil)
            this.awaitingUntil = 0;
        if (this.pending && text === this.pending && now - this.pendingSince >= this.delay) {
            const selected = this.pending;
            this.pending = '';
            return selected;
        }
        return null;
    }
}
