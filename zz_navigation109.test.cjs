const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync('src/navigation.ts', 'utf8');
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const sandboxModule = { exports: {} };

let queue = [];
let target = null;
let reduced = true;
const calls = [];
global.document = { getElementById: (id) => target && target.id === id ? target : null };
global.window = {
  requestAnimationFrame: (callback) => { queue.push(callback); return queue.length; },
  matchMedia: (query) => {
    assert.equal(query, '(prefers-reduced-motion: reduce)');
    return { matches: reduced };
  },
};
vm.runInNewContext(js, {
  module: sandboxModule,
  exports: sandboxModule.exports,
  document: global.document,
  window: global.window,
});
const { scrollToRenderedAnchor } = sandboxModule.exports;
const flush = () => { const callbacks = queue; queue = []; callbacks.forEach((callback) => callback()); };

scrollToRenderedAnchor('oversold-value-directions');
assert.equal(queue.length, 1, '首次定位必须等下一渲染帧');
flush();
assert.equal(calls.length, 0, '目标未挂载时不得滚动');
target = { id: 'oversold-value-directions', getClientRects: () => [], scrollIntoView: (arg) => calls.push(arg) };
flush();
assert.equal(calls.length, 0, '目标存在但不可见时不得滚动');
target.getClientRects = () => [{}];
flush();
assert.equal(calls.length, 1);
assert.equal(calls[0].behavior, 'auto', '可见后滚动且尊重减少动态效果');
assert.equal(calls[0].block, 'start');

calls.length = 0;
reduced = false;
target = { id: 'rsi6-dividend-top20', getClientRects: () => [{}], scrollIntoView: (arg) => calls.push(arg) };
scrollToRenderedAnchor('rsi6-dividend-top20');
flush();
assert.equal(calls.length, 1);
assert.equal(calls[0].behavior, 'smooth', '常规模式保留平滑滚动');
assert.equal(calls[0].block, 'start');
console.log('navigation DOM tests: 6/6 passed');
