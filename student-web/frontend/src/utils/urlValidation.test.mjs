import test from 'node:test';
import assert from 'node:assert/strict';
import { validHttpUrl } from './urlValidation.ts';
test('optional HTTP(S) URLs and signed image links', () => {
  for (const value of [null, '', '  ', 'https://example.com/a?x=1&y=2', ' http://example.com/a ', 'https://example.com/a%20b']) assert.equal(validHttpUrl(value), true, value);
});
test('rejects executable schemes, credentials and malformed URLs', () => {
  for (const value of ['javascript:alert(1)', 'data:text/html,test', '//example.com/a', 'https:///a', 'https://user:pass@example.com/a', 'https://example.com:99999/a', 'https://example.com/\nfoo', 'https://example.com/%xx', 'https://example.com/a b']) assert.equal(validHttpUrl(value), false, value);
});
