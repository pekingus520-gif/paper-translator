import assert from 'node:assert/strict';
import {SelectionTracker} from '../gnome-bridge/selection.js';

const drag = (tracker, baseline, selected, start, end, time) => {
    tracker.feed(baseline, time - 50);
    tracker.feed('', time, true, start);
    tracker.feed('', time + 60, true, end);
    tracker.feed(selected, time + 120, false, end);
};

const tracker = new SelectionTracker();
assert.equal(tracker.feed('old PRIMARY text', 0), null);
assert.equal(tracker.feed('unrelated clipboard update', 1200), null);
assert.equal(tracker.feed('unrelated clipboard update', 2400), null);

// Clicks and unrelated drags must never replay the stale PRIMARY selection.
tracker.feed('', 2500, true, {x: 10, y: 10});
tracker.feed('unrelated clipboard update', 2560, false, {x: 10, y: 10});
assert.equal(tracker.feed('unrelated clipboard update', 3700), null);
drag(tracker, 'unrelated clipboard update', 'unrelated clipboard update',
    {x: 0, y: 0}, {x: 50, y: 5}, 4000);
assert.equal(tracker.feed('unrelated clipboard update', 5200), null);

drag(tracker, 'unrelated clipboard update', 'new sentence',
    {x: 0, y: 0}, {x: 40, y: 10}, 6000);
assert.equal(tracker.feed('new sentence', 7119), null);
assert.equal(tracker.feed('new sentence', 7120), 'new sentence');
assert.equal(tracker.feed('new sentence', 8200), null);

// Copying within the one-second grace period cancels translation.
drag(tracker, 'new sentence', 'copied sentence',
    {x: 0, y: 0}, {x: 30, y: 0}, 9000);
tracker.cancelText('copied sentence');
assert.equal(tracker.feed('copied sentence', 10200), null);
drag(tracker, 'copied sentence', 'copied sentence',
    {x: 0, y: 0}, {x: 30, y: 0}, 11000);
assert.equal(tracker.feed('copied sentence', 12200), null);

// The clipboard owner can change even when copying identical text.
tracker.feed('', 12300, true, {x: 0, y: 0});
tracker.feed('', 12360, true, {x: 30, y: 0});
tracker.cancelCurrent();
tracker.feed('same clipboard contents', 12420, false, {x: 30, y: 0});
assert.equal(tracker.feed('same clipboard contents', 13500), null);

// A delayed PRIMARY update after mouse release can still be accepted.
tracker.feed('', 14000, true, {x: 0, y: 0});
tracker.feed('', 14060, true, {x: 30, y: 0});
tracker.feed('same clipboard contents', 14120, false, {x: 30, y: 0});
tracker.feed('another sentence', 14200);
assert.equal(tracker.feed('another sentence', 15200), 'another sentence');

tracker.suspend();
assert.equal(tracker.feed('existing selection after resume', 16000), null);
assert.equal(tracker.feed('existing selection after resume', 17000), null);
console.log('GNOME gesture and copy distinction tests passed');
