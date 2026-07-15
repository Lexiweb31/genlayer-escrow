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
