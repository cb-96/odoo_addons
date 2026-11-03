// Staging browser/adversarial runner. Uses real prepared fixtures; no missing case is treated as passed.
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
const base=process.env.SF_BASE_URL;
const config=JSON.parse(process.env.SF_FAMILY_FIXTURES || '{}');
for(const key of ['guardian_login','guardian_password','reviewer_login','reviewer_password','person_a','person_b','membership_a','membership_b','next_season','document_a','relationship_a','evidence_path']) {
    if(!config[key])throw Error(`Missing SF_FAMILY_FIXTURES.${key}`);
}
if(!base)throw Error('Set SF_BASE_URL');
const browser=await chromium.launch();
try {
    const login=async(user,password)=>{
        const context=await browser.newContext(); const page=await context.newPage();
        await page.goto(`${base}/web/login`); await page.locator('[name="login"]').fill(user);
        await page.locator('[name="password"]').fill(password); await page.locator('button[type="submit"]').click();
        await page.waitForURL(url=>!url.pathname.includes('/web/login'));
        return {context,page};
    };
    const guardian=await login(config.guardian_login,config.guardian_password);
    const reviewer=await login(config.reviewer_login,config.reviewer_password);
    const rpc=async(page,model,method,args)=>page.evaluate(async({model,method,args})=>{
        const response=await fetch(`/web/dataset/call_kw/${model}/${method}`,{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({jsonrpc:'2.0',method:'call',params:{model,method,args,kwargs:{}},id:1})});
        const body=await response.json();if(body.error)throw Error(body.error.data?.message || body.error.message);return body.result;
    },{model,method,args});
    const page=guardian.page;
    await page.goto(`${base}/my/family`);
    assert.equal(await page.locator(`[data-family-person="${config.person_a}"]`).count(),1);
    assert.equal(await page.locator(`[data-family-person="${config.person_b}"]`).count(),1);
    const source=await rpc(reviewer.page,'federation.person.membership','read',[[config.membership_a,config.membership_b],['state','person_id','lifecycle_revision']]);
    assert(source.every(row=>row.state==='active'));
    const form=page.locator(`[data-membership="${config.membership_a}"] form[action$="/renew"]`);
    const csrf=await form.locator('[name="csrf_token"]').inputValue();
    const post=async(person)=>page.evaluate(async({id,season,person,csrf})=>{
        const response=await fetch(`/my/family/memberships/${id}/renew`,{method:'POST',body:new URLSearchParams({season_id:String(season),person_id:String(person),confirmed:'yes',csrf_token:csrf})});
        return {status:response.status,text:await response.text()};
    },{id:config.membership_a,season:config.next_season,person,csrf});
    const wrong=await post(config.person_b);
    assert(wrong.text.includes('Renewal not accepted'));
    const domain=[['person_id','=',config.person_a],['season_id','=',config.next_season]];
    assert.equal(await rpc(reviewer.page,'federation.person.membership','search_count',[domain]),0);
    // Two simultaneous requests share an authenticated browser session but distinct HTTP transactions.
    const concurrent=await Promise.all([post(config.person_a),post(config.person_a)]);
    assert(concurrent.every(response=>response.status===200));
    assert.equal(await rpc(reviewer.page,'federation.person.membership','search_count',[domain]),1);
    const renewed=await rpc(reviewer.page,'federation.person.membership','search_read',[domain,['state','previous_id']]);
    assert.equal(renewed[0].state,'draft');assert.equal(renewed[0].previous_id[0],config.membership_a);
    const unchanged=await rpc(reviewer.page,'federation.person.membership','read',[[config.membership_b],['lifecycle_revision']]);
    assert.equal(unchanged[0].lifecycle_revision,source.find(row=>row.id===config.membership_b).lifecycle_revision);
    await page.goto(`${base}/my/family?person_id=${config.person_a}`);
    assert.equal(await page.locator(`[data-family-person="${config.person_b}"]`).count(),0);
    const upload=page.locator(`[data-document-request="${config.document_a}"] form`);
    await upload.locator('[type="file"]').setInputFiles(config.evidence_path);
    await upload.locator('[name="confirmed"]').check();
    await upload.locator('button[type="submit"]').focus();await page.keyboard.press('Enter');
    await page.waitForURL(url=>url.searchParams.has('feedback'));
    const action=await rpc(reviewer.page,'federation.person.request','action_verify',[[config.document_a]]);
    assert.equal(action.res_model,'federation.person.request.review');
    await rpc(reviewer.page,action.res_model,'write',[[action.res_id],{inspected:true}]);
    await rpc(reviewer.page,'federation.person.request','write',[[config.document_a],{review_note:'Replace for staging stale-snapshot test'}]);
    await rpc(reviewer.page,'federation.person.request','action_return',[[config.document_a]]);
    await page.goto(`${base}/my/family?person_id=${config.person_a}`);
    const replacement=page.locator(`[data-document-request="${config.document_a}"] form`);
    await replacement.locator('[type="file"]').setInputFiles(config.evidence_path);
    await replacement.locator('[name="confirmed"]').check();await replacement.locator('button[type="submit"]').click();
    await page.waitForURL(url=>url.searchParams.has('feedback'));
    await assert.rejects(()=>rpc(reviewer.page,action.res_model,'action_confirm',[[action.res_id]]));
    const matchingName=`Matching-${Date.now()}`;
    const creates=await Promise.allSettled([
        rpc(reviewer.page,'federation.player','create',[{first_name:matchingName,last_name:'Concurrency fixture',birth_date:'2000-01-01'}]),
        rpc(reviewer.page,'federation.player','create',[{first_name:matchingName.toUpperCase(),last_name:'CONCURRENCY FIXTURE',birth_date:'2000-01-01'}])
    ]);
    assert.equal(creates.filter(result=>result.status==='fulfilled').length,1);
    assert.equal(await rpc(reviewer.page,'federation.player','search_count',[[['first_name','in',[matchingName,matchingName.toUpperCase()]],['birth_date','=','2000-01-01']]]),1);
    // Current access is rechecked during the same active browser session.
    await rpc(reviewer.page,'federation.person.relationship','action_revoke',[[config.relationship_a]]);
    const revoked=await page.goto(`${base}/my/family/requests/${config.document_a}/download?person_id=${config.person_a}`);
    assert.equal(revoked.status(),404);
    const focused=await page.goto(`${base}/my/family?person_id=${config.person_a}`);assert.equal(focused.status(),404);
    console.log('Family browser/adversarial smoke passed. Full matching/company suite and human metrics remain separate.');
} finally {await browser.close();}
