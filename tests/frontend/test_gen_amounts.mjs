import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const docsUrl = new URL('../../docs/index.html', import.meta.url);
const publicUrl = new URL('../../public/index.html', import.meta.url);
const docs = readFileSync(docsUrl, 'utf8');
const publicHtml = readFileSync(publicUrl, 'utf8');
const start = docs.indexOf('const WEI_PER_GEN');
const end = docs.indexOf('const jobCode', start);
const helpers = docs.slice(start, end);
const amounts = vm.runInNewContext(
  `${helpers};({genToWeiExact,toGEN,toGENNum,weiBigInt,MIN_DEMO_AMOUNT_WEI})`,
);
const cardStart = docs.indexOf('function jobCardHTML');
const cardEnd = docs.indexOf('function jobCategory', cardStart);
const jobCardHTML = vm.runInNewContext(`
  const JC_ACCENT={SUBMITTED:'green',SETTLEMENT_PENDING:'gold'};
  const TERM=new Set(['ACCEPTED','PARTIAL','REFUNDED']);
  const savedJobs=new Set();
  const esc=value=>String(value??'');
  const jobCode=()=> 'JOB-TEST';
  const jobCategory=()=> 'Digital deliverable';
  const relativeTime=()=> 'now';
  const scoreRing=score=>String(score);
  const settlementRecipientRole=transfer=>({WORKER_PAYOUT:'Worker recipient',CLIENT_REFUND:'Client recipient',PLATFORM_FEE:'Platform recipient'})[transfer.settlement_type];
  ${helpers}
  ${docs.slice(cardStart, cardEnd)}
  jobCardHTML;
`);

test('frontend copies remain identical', () => {
  assert.equal(docs, publicHtml);
});

test('decimal GEN converts to wei without Number precision loss', () => {
  assert.equal(amounts.genToWeiExact('0.001'), '1000000000000000');
  assert.equal(
    amounts.genToWeiExact('1.000000000000000001'),
    '1000000000000000001',
  );
  assert.equal(amounts.weiBigInt('0.001'), 0n);
  assert.equal(amounts.MIN_DEMO_AMOUNT_WEI, 1000000000000000n);
});

test('tiny legacy values never display as zero GEN', () => {
  assert.equal(amounts.toGEN('1'), '0.000000000000000001 GEN');
  assert.equal(amounts.toGEN('999'), '999 wei (less than 0.0001 GEN)');
  assert.equal(amounts.toGENNum('1'), '0.000000000000000001');
});

test('invalid decimal inputs are rejected', () => {
  assert.throws(() => amounts.genToWeiExact('1e-3'));
  assert.throws(() => amounts.genToWeiExact('0.0000000000000000001'));
});

test('submitted job cards do not claim validator completion', () => {
  const html = jobCardHTML({
    address: '0x1234567890123456789012345678901234567890',
    status: 'SUBMITTED',
    amount: '1',
    score: null,
    title: 'Submitted work',
    spec: 'Waiting for evaluation',
  });
  assert.match(html, /Not evaluated yet/);
  assert.doesNotMatch(html, /5-validator result confirmed/);
  assert.match(html, /0\.000000000000000001 GEN/);
});

test('pending job cards expose precise outbound settlement proof', () => {
  const parent = '0xf800344a5fc364be9d6ae9ff40fd48c73689cfaf36140eb100208c75d9885c11';
  const html = jobCardHTML({
    address: '0x1234567890123456789012345678901234567890',
    status: 'SETTLEMENT_PENDING',
    amount: '0',
    score: 100,
    title: 'Pending settlement',
    spec: 'Transfer proof',
    settlement: {
      parent_transaction: parent,
      transfers: [{
        recipient: '0xf55dAc48f46b1708b4F818CA923b825F3f73aD7c',
        amount: '980000000000000',
        settlement_type: 'WORKER_PAYOUT',
      }],
    },
  });
  assert.match(html, /Settlement transfer pending finalization/);
  assert.match(html, /Worker recipient/);
  assert.match(html, /0\.00098 GEN/);
  assert.match(html, new RegExp(parent));
  assert.match(html, /Explorer ↗/);
});
