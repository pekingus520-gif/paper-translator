import assert from 'node:assert/strict';
import {SelectionTracker} from '../gnome-bridge/selection.js';

const tracker = new SelectionTracker();
assert.equal(tracker.feed('initial selection', 0), null); // startup primes existing selection
assert.equal(tracker.feed('initial selection', 1000), null);
assert.equal(tracker.feed('half', 1100, true), null);
assert.equal(tracker.feed('whole sentence', 1200), null);
assert.equal(tracker.feed('whole sentence', 2199), null);
assert.equal(tracker.feed('whole sentence', 2200), 'whole sentence');
assert.equal(tracker.feed('whole sentence', 2300), null);
tracker.suspend();
assert.equal(tracker.feed('selected while paused', 2400), null);
assert.equal(tracker.feed('selected while paused', 3400), null);
assert.equal(tracker.feed('new', 3500), null);
assert.equal(tracker.feed('new', 4500), 'new');
tracker.feed('', 4600);
tracker.feed('new', 4700);
assert.equal(tracker.feed('new', 5700), 'new');
tracker.feed('copy candidate', 5800);
tracker.cancelCurrent();
assert.equal(tracker.feed('copy candidate', 7000), null);
tracker.feed('fresh selection', 7100);
assert.equal(tracker.feed('fresh selection', 8100), 'fresh selection');
tracker.feed('', 8200, true);
tracker.feed('fresh selection', 8300);
assert.equal(tracker.feed('fresh selection', 9300), 'fresh selection');
console.log('GNOME selection debounce/pause tests passed');
