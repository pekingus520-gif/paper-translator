import assert from 'node:assert/strict';
import {shouldPresentResult} from '../gnome-bridge/result-presentation.js';

const first = {generation: 'a', result_revision: 2};
assert.equal(shouldPresentResult(null, first), true);
assert.equal(shouldPresentResult(first, {...first}), false);
assert.equal(shouldPresentResult(first, {...first, result_revision: 3}), true);
assert.equal(shouldPresentResult(first, {generation: 'b', result_revision: 2}), true);
assert.equal(shouldPresentResult(null, {generation: 'a', result_revision: 0}), false);
console.log('Result presentation revision tests passed');
