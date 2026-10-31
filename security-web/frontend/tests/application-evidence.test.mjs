import test from 'node:test';
import assert from 'node:assert/strict';
import { applicationEvidence } from '../src/applicationEvidence.ts';
test('legacy, invalid and arbitrary evidence do not become APP aggregates', () => {
  for (const text of ['not JSON','null','{}','{"rule_code":"OTHER"}']) assert.equal(applicationEvidence(text),null);
});
test('APP evidence preserves explicit recommendation and bounded display fields', () => {
  const value=applicationEvidence(JSON.stringify({rule_code:'APP-1001',event_count:20,uri_path:'/api/auth/me',recommended_action:'BLOCK',reason:'20 failures'}));
  assert.equal(value.count,20);assert.equal(value.recommendation,'BLOCK');assert.equal(value.endpoint,'/api/auth/me');
  assert.equal(applicationEvidence('{"rule_code":"APP-1004","recommended_action":"EXECUTE"}').recommendation,'ALERT_ONLY');
});
