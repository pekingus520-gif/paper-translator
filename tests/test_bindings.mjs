import assert from 'node:assert/strict';
import {HotkeyBindings} from '../gnome-bridge/bindings.js';

const active = new Map();
const calls = [];
let blocked = null;
const bindings = new HotkeyBindings(
    (key, accelerator) => {
        calls.push(['register', key, accelerator]);
        if (accelerator === blocked)
            return false;
        active.set(key, accelerator);
        return true;
    },
    key => {
        calls.push(['remove', key]);
        active.delete(key);
    },
);
const desired = (screenshot, toggle) => [
    ['screenshot', screenshot], ['toggle', toggle],
];
assert.deepEqual(bindings.sync(desired('<Alt>b', '<Control><Alt>z')), []);
assert.deepEqual([...active.values()], ['<Alt>b', '<Control><Alt>z']);
const firstCount = calls.length;
bindings.sync(desired('<Alt>b', '<Control><Alt>z'));
assert.equal(calls.length, firstCount);
assert.deepEqual(bindings.sync(desired('<Control><Shift>s', '<Control><Alt>z')), []);
assert.equal(active.get('screenshot'), '<Control><Shift>s');
assert.equal(active.get('toggle'), '<Control><Alt>z');
blocked = '<Super>F8';
assert.deepEqual(bindings.sync(desired('<Super>F8', '<Control><Alt>z')), ['<Super>F8']);
assert.equal(active.has('screenshot'), false);
assert.equal(active.get('toggle'), '<Control><Alt>z');
blocked = null;
assert.deepEqual(bindings.sync(desired('<Super>F8', '<Control><Alt>z')), []);
assert.equal(active.get('screenshot'), '<Super>F8');
bindings.clear();
assert.equal(active.size, 0);
console.log('GNOME hotkey rebinding tests passed');
