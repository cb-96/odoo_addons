// Unit tests for actual frontend helpers using a small DOM/storage stub, not browser qualification.
const fs = require('fs'); const vm = require('vm'); const assert = require('node:assert/strict');
const path = require('path');
const source = fs.readFileSync(path.join(__dirname, '../sports_federation_portal/static/src/js/journey_return_navigation.js'), 'utf8');
const context = vm.createContext({URL, Set, Date, Number, JSON, location: {origin: 'https://local.test', pathname: '/my/action-items', href: 'https://local.test/my/action-items'}, document: {readyState: 'loading', addEventListener() {}}, sessionStorage: {getItem() {return null;}, removeItem() {}, setItem() {}}});
vm.runInContext(source, context);
let tests = 0;
function check(expression, expected) {assert.equal(vm.runInContext(expression, context), expected); tests++;}
check("safeReturn('/my/action-items?scope=club&status=recent&evil=1')", '/my/action-items?scope=club&status=recent');
check("safeReturn('https://evil.test/my/action-items')", null);
check("safeReturn('//evil.test/my/action-items')", null);
check("safeReturn('/my/rosters/1')", null);
check("safeReturn('/my/action-items?scope=unknown')", '/my/action-items');
check("safeReturn('/my/referee-assignments')", '/my/referee-assignments');
check("safeReturn('/my/referee-assignments?filterby=history&page=2')", '/my/referee-assignments?filterby=history');
check("safeReturn('/my/referee-assignments?filterby=invalid')", '/my/referee-assignments');
check("safeReturn('/my/work')", '/my/work');
check("safeReturn('//local.test/my/work')", null);
check("safeReturn('/my/action-items/%2e%2e/work')", null);
check("safeReturn('/my/action-items?status=recent#unsafe')", '/my/action-items?status=recent');
check("safeReturn(null)", null);
context.sessionStorage = {getItem() {throw new Error('disabled');}};
check("storage(s => s.getItem('x'))", null);
console.log(`${tests} frontend helper tests passed (not browser qualification)`);
