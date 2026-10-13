import assert from 'node:assert/strict';
import {attachScreenshotSignals} from '../gnome-bridge/screenshot-session.js';

function fakeUi() {
    const listeners = new Map();
    let nextId = 1;
    return {
        listeners,
        disconnected: [],
        connect(signal, callback) {
            const id = nextId++;
            listeners.set(id, {signal, callback});
            return id;
        },
        disconnect(id) {
            this.disconnected.push(id);
            listeners.delete(id);
        },
        emit(signal, ...args) {
            for (const listener of [...listeners.values()]) {
                if (listener.signal === signal)
                    listener.callback(this, ...args);
            }
        },
    };
}

const ui = fakeUi();
const messages = [];
const deferred = [];
attachScreenshotSignals(ui, 'shot-1', message => messages.push(message),
    callback => deferred.push(callback));
assert.deepEqual([...ui.listeners.values()].map(value => value.signal),
    ['screenshot-taken', 'closed']);
ui.emit('screenshot-taken', {get_path: () => '/tmp/selected.png'});
assert.deepEqual(messages, [{command: 'screenshot_file', capture_id: 'shot-1',
    path: '/tmp/selected.png'}]);
ui.emit('closed');
assert.equal(ui.disconnected.length, 0, 'signal handlers stay connected until emission ends');
deferred.shift()();
assert.equal(ui.disconnected.length, 2);
assert.equal(messages.length, 1, 'a completed capture is never cancelled');

const cancelledUi = fakeUi();
const cancelled = [];
const cleanup = [];
attachScreenshotSignals(cancelledUi, 'shot-2', message => cancelled.push(message),
    callback => cleanup.push(callback));
cancelledUi.emit('closed');
cleanup.shift()();
assert.deepEqual(cancelled, [{command: 'screenshot_cancel', capture_id: 'shot-2'}]);
console.log('Screenshot signal lifecycle tests passed');
