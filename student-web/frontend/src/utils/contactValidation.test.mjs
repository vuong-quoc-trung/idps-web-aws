import test from 'node:test';
import assert from 'node:assert/strict';
import { validPhone, normalizePhone, validEmail, phoneError } from './contactValidation.ts';

test('Vietnamese mobile/landline and international phone formats', () => {
  for (const value of [undefined, '', '0912345678', '0912 345 678', '+84 912-345-678', '02412345678', '+1 (415) 555-2671']) assert.equal(validPhone(value), true, value);
  for (const value of ['123', '0123456789', '+840912345678', '091234567a', '++84912345678', '+012345678', '+1234567890123456']) assert.equal(validPhone(value), false, value);
  assert.equal(normalizePhone(' +84 912-345-678 '), '+84912345678');
});
test('Email syntax accepts multiple providers and rejects malformed addresses', () => {
  for (const value of [undefined, '', ' test+tag@gmail.com ', 'student@university.edu.vn', 'a.b@outlook.com']) assert.equal(validEmail(value), true, value);
  for (const value of ['a@gmail', 'a..b@gmail.com', '.a@gmail.com', 'a @gmail.com', 'a@@gmail.com', 'a@-gmail.com', 'a@gmail..com', 'a'.repeat(65)+'@gmail.com']) assert.equal(validEmail(value), false, value);
});

test('Vietnamese phone errors explain missing digits and international prefix', () => {
  assert.match(phoneError('077415608'), /thiếu 1 chữ số/);
  assert.match(phoneError('+8477415608'), /thiếu 1 chữ số/);
  assert.match(phoneError('+840912345678'), /bỏ số 0 đầu/);
  assert.equal(phoneError('0771234567'), '');
  assert.equal(phoneError('+84771234567'), '');
});
