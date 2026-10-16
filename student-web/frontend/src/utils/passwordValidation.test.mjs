import test from 'node:test';
import assert from 'node:assert/strict';
import { passwordError } from './passwordValidation.ts';
test('password policy matches backend byte limit and preserves whitespace', () => {
  assert.equal(passwordError('a'.repeat(12), 'a'.repeat(12)), '');
  assert.equal(passwordError('a'.repeat(72), 'a'.repeat(72)), '');
  assert.ok(passwordError('short', 'short'));
  assert.ok(passwordError(' '.repeat(12), ' '.repeat(12)));
  assert.ok(passwordError('短'.repeat(25), '短'.repeat(25)));
  assert.ok(passwordError('valid-password', 'valid-password '));
});
