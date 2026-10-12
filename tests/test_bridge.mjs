import assert from 'node:assert/strict';
import {SelectionTracker} from '../gnome-bridge/selection.js';

const tracker = new SelectionTracker(450);
assert.equal(tracker.feed('initial selection', 0), null); // startup primes existing selection
assert.equal(tracker.feed('initial selection', 1000), null);
assert.equal(tracker.feed('half', 1100, true), null);
assert.equal(tracker.feed('whole sentence', 1200), null);
assert.equal(tracker.feed('whole sentence', 1649), null);
assert.equal(tracker.feed('whole sentence', 1650), 'whole sentence');
assert.equal(tracker.feed('whole sentence', 2000), null);
tracker.suspend();
assert.equal(tracker.feed('selected while paused', 2100), null);
assert.equal(tracker.feed('selected while paused', 3000), null);
assert.equal(tracker.feed('new', 3100), null);
assert.equal(tracker.feed('new', 3550), 'new');
tracker.feed('', 4000);
tracker.feed('new', 4100);
assert.equal(tracker.feed('new', 4550), 'new');
console.log('GNOME selection debounce/pause tests passed');
