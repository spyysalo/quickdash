// Public-fixture browser checks: no private evaluation export is required.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url),{parseCatalogue,serializeCatalogue}=require('../app/eval_config.js'),{parseWeightProfile,serializeWeightProfile,serializeSuite}=require('../app/suite_config.js');
const root=fileURLToPath(new URL('../',import.meta.url));
const shippedChoices=directory=>({
 files:fs.readdirSync(path.join(root,directory)).filter(name=>/\.ya?ml$/i.test(name)).sort(),
 defaultFile:fs.readFileSync(path.join(root,directory,'default.txt'),'utf8').trim(),
});
const shippedSets=shippedChoices('configs/sets'),shippedProfiles=shippedChoices('configs/weights');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'quickdash-browser-'));
let ws;
try{
 const fixture=parseCatalogue(fs.readFileSync(path.join(root,'configs/examples/catalogue.yaml'),'utf8'));
 fixture.evals[0].match.regex='example_reasoning_(en|fr|de)';
 fixture.languages[1].tasks.push('example_reasoning_de');
 const weighting=parseWeightProfile(fs.readFileSync(path.join(root,'configs/examples/weights.yaml'),'utf8'));
 const profiles=path.join(temporary,'weights');fs.mkdirSync(profiles);
 fs.copyFileSync(path.join(root,'configs/weights/oellm.yaml'),path.join(profiles,'oellm.yaml'));
 fs.writeFileSync(path.join(profiles,'default.txt'),'oellm.yaml\n');
 fs.writeFileSync(path.join(profiles,'example.yaml'),serializeWeightProfile(weighting));
 const empty=path.join(temporary,'empty');
 execFileSync('python3',['-m','app.build','--weights-dir',profiles,'--output',empty],{cwd:root,stdio:'pipe'});
 let tabs;
 // A cold CI runner can take longer than five seconds to launch Chrome.
 const startupDeadline=Date.now()+30_000;
 while(Date.now()<startupDeadline){
  try{tabs=await(await fetch(`http://127.0.0.1:${process.env.QUICKDASH_CHROME_PORT || 9227}/json/list`)).json();if(tabs.some(t=>t.type==='page'))break;}catch{}
  await new Promise(r=>setTimeout(r,200));
 }
 assert.ok(tabs?.some(t=>t.type==='page'),'Start an isolated Chrome session on QUICKDASH_CHROME_PORT (default 9227)');
 ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
 await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 let id=0;const pending=new Map(),errors=[],network=[];
 ws.addEventListener('message',e=>{
  const m=JSON.parse(e.data);
  if(m.id){const p=pending.get(m.id);if(!p)return;pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result);}
  else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);
  else if(m.method==='Network.requestWillBeSent'&&/^https?:/.test(m.params.request.url))network.push(m.params.request.url);
 });
 const send=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
 const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert.ok(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;};
 const click=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
 const change=(selector,value)=>evaluate(`{const e=document.querySelector(${JSON.stringify(selector)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));}`);
 const navigate=async url=>{await send('Page.navigate',{url});for(let i=0;i<50;i++){await new Promise(r=>setTimeout(r,50));if(await evaluate("document.querySelector('#view')?.textContent.length>0"))return;}throw Error('Dashboard did not render');};
 await send('Runtime.discardConsoleEntries');
 await send('Runtime.enable');await send('Network.enable');await send('Page.enable');
 await navigate(pathToFileURL(path.join(empty,'index.html')).href);
 assert.equal(await evaluate("document.querySelector('#modelA').options.length"),0);
 assert.equal(await evaluate("document.querySelector('#cards').hidden"),true);
 assert.match(await evaluate("document.querySelector('#view').textContent"),/Compare your evaluation results/);
 assert.equal(await evaluate("document.querySelector('#suitePreset').options.length"),shippedSets.files.length);
 assert.equal(await evaluate("DATA.suites[Number(document.querySelector('#suitePreset').value)].file"),shippedSets.defaultFile);
 for(const view of ['categories','languages','comparisons','config','warnings','score'])await click('[data-view='+view+']');
 const upload=async(selector,content,name)=>evaluate(`(async()=>{const dt=new DataTransfer();dt.items.add(new File([${JSON.stringify(content)}],${JSON.stringify(name)}));const e=document.querySelector(${JSON.stringify(selector)});e.files=dt.files;if(e.id==='modelFile')await e.onchange({target:e});else await document.querySelector('#view').onchange({target:e});})()`);
 await click('[data-view=config]');await upload('#suiteFile',serializeSuite({version:1,name:'Any example',mode:'available'}),'any.yaml');await upload('#configFile',serializeCatalogue(fixture),'catalogue.yaml');
 await change('#weightPreset','1');
 await upload('#modelFile',fs.readFileSync(path.join(root,'examples/scores.csv'),'utf8'),'scores.csv');
 assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
 assert.equal(await evaluate("document.querySelector('#modelA').value"),'Example A');
 assert.equal(await evaluate("document.querySelector('#modelB').value"),'Example B');
 assert.equal(await evaluate("document.querySelector('#warningCount').textContent"),'0');
 assert.equal(await evaluate("document.querySelector('#cards .score-card:last-child strong').textContent"),'-2.50');
 // Category score deltas sit before weighted contributions and use sign colors.
 await click('[data-view=score]');
 const categoryCells=()=>evaluate("[...document.querySelector('#view table').tBodies[0].rows].map(r=>[...r.cells].map(c=>({text:c.textContent,classes:c.className})))");
 assert.deepEqual(await evaluate("[...document.querySelector('#view table').tHead.rows[0].cells].map(c=>c.textContent)"),['Category','Weight','A','B','A − B','A contribution','B contribution','Contribution Δ','Explore']);
 let cells=await categoryCells();
 assert.equal(cells[0][4].text,'5.00');assert.match(cells[0][4].classes,/positive/);
 assert.equal(cells[1][4].text,'-10.00');assert.match(cells[1][4].classes,/negative/);
 assert.equal(cells[0][7].text,'2.5000');assert.equal(cells[1][7].text,'-5.0000');
 await click('#swap');cells=await categoryCells();
 assert.equal(cells[0][4].text,'-5.00');assert.match(cells[0][4].classes,/negative/);
 assert.equal(cells[1][4].text,'10.00');assert.match(cells[1][4].classes,/positive/);
 await click('#swap');await change('#modelB','Example A');cells=await categoryCells();
 assert.equal(cells[0][4].text,'0.00');assert.doesNotMatch(cells[0][4].classes,/positive|negative/);
 await change('#modelB','Example B');
 const evalTable=()=>evaluate("[...document.querySelectorAll('#view table')].find(t=>t.tHead.rows[0].cells[0].textContent==='Eval').outerHTML");
 const evalDelta=()=>evaluate("(()=>{const t=[...document.querySelectorAll('#view table')].find(t=>t.tHead.rows[0].cells[0].textContent==='Eval');const c=t.tBodies[0].rows[0].cells[5];return {text:c.textContent,classes:c.className};})()");
 await click('[data-score-category=Reasoning]');
 assert.match(await evalTable(),/A − B<\/th><th[^>]*>Effective weight/);
 assert.deepEqual(await evalDelta(),{text:'5.00',classes:'num positive'});
 await click('[data-score-category=Math]');
 assert.deepEqual(await evalDelta(),{text:'-10.00',classes:'num negative'});
 await change('#modelB','Example A');assert.deepEqual(await evalDelta(),{text:'0.00',classes:'num '});
 await change('#modelB','Example B');
 await click('[data-view=config]');
 const original=await evaluate("document.querySelector('#cards').textContent");
 // A catalogue without loaded data is not a coverage requirement.
 const extended=structuredClone(fixture);extended.evals.push({...extended.evals[0],name:'Unused eval',match:{name:'unused'}});
 await upload('#configFile',serializeCatalogue(extended),'extended.yaml');
 assert.equal(await evaluate("document.querySelector('#warningCount').textContent"),'0');
 const invalid=structuredClone(fixture);invalid.evals[0].score.scale=.1;
 await upload('#configFile',serializeCatalogue(invalid),'invalid.yaml');
 assert.match(await evaluate("document.querySelector('#error').textContent"),/Invalid score/);
 assert.equal(await evaluate("document.querySelector('#cards').textContent"),original);
 // Named sets check requirements missing from both models and retain extras for inspection.
 const fixed={version:1,name:'Example required set',mode:'fixed',evals:[{name:'Example reasoning',variants:[{task:'example_reasoning_en',n_shot:0},{task:'example_reasoning_de',n_shot:0}]}]};
 await upload('#suiteFile',serializeSuite(fixed),'set.yaml');
 assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
 assert.match(await evaluate("document.querySelector('#coverage').textContent"),/INCOMPLETE.*1\/2 requirements shared.*4 extra/);
 assert.equal(await evaluate("document.querySelector('#weightPreset').value"),'1');
 await click('[data-view=score]');cells=await categoryCells();
 assert.equal(cells[1][4].text,'—');assert.doesNotMatch(cells[1][4].classes,/positive|negative/);
 await click('[data-view=warnings]');
 assert.match(await evaluate("document.querySelector('#view').textContent"),/Missing suite data.*example_reasoning_de/s);
 assert.match(await evaluate("document.querySelector('#view').textContent"),/Not used/);
 await click('[data-view=config]');
 assert.match(await evaluate("document.querySelector('#view').textContent"),/Example math/);
 await click('[data-view=score]');await change('[data-weight=Reasoning]','.8');await change('[data-weight=Math]','.2');
 await click('[data-view=config]');await upload('#suiteFile',serializeSuite({version:1,name:'Any example',mode:'available'}),'any.yaml');await click('[data-view=score]');
 assert.equal(await evaluate("document.querySelector('[data-weight=Reasoning]').value"),'0.8');
 await click('[data-view=config]');
 const unavailable={...fixed,evals:[{name:'Absent eval'}]};
 await upload('#suiteFile',serializeSuite(unavailable),'invalid-set.yaml');
 assert.match(await evaluate("document.querySelector('#error').textContent"),/no catalogue rule/);
 assert.equal(await evaluate("document.querySelector('#suitePreset').value"),'custom');
 await upload('#suiteFile',serializeSuite(fixed),'set.yaml');
 await change('#weightPreset','0');
 assert.equal(await evaluate("document.querySelector('#suitePreset').value"),'custom');
 await change('#weightPreset','1');
 await evaluate(`window.originalCreate=URL.createObjectURL;window.originalClick=HTMLAnchorElement.prototype.click;URL.createObjectURL=b=>{window.exportBlob=b;return 'blob:test'};HTMLAnchorElement.prototype.click=function(){};`);
 await click('#exportConfig');assert.deepEqual(await evaluate('exportBlob.text().then(parseCatalogue)'),extended);
 await click('#exportSuite');assert.deepEqual(await evaluate('exportBlob.text().then(parseSuite)'),fixed);
 await click('#exportWeights');assert.deepEqual(await evaluate('exportBlob.text().then(parseWeightProfile)'),{...weighting,english_weights:weighting.english_weights,aggregate:'standard'});
 await evaluate('URL.createObjectURL=originalCreate;HTMLAnchorElement.prototype.click=originalClick');
 await click('[data-view=config]');await upload('#suiteFile',serializeSuite({version:1,name:'Any example',mode:'available'}),'any.yaml');await click('[data-view=score]');await click('#clearModels');
 assert.equal(await evaluate("document.querySelector('#modelA').options.length"),0);
 await click('[data-view=config]');await upload('#configFile',serializeCatalogue(invalid),'small.yaml');
 await upload('#modelFile',fs.readFileSync(path.join(root,'examples/scores.csv'),'utf8'),'bad-for-config.csv');
 assert.match(await evaluate("document.querySelector('#error').textContent"),/Invalid score/);
 assert.equal(await evaluate("document.querySelector('#modelA').options.length"),0);
 // A shared-results build embeds both models and defaults to the real comparison.
 const results=path.join(temporary,'results');fs.mkdirSync(results);
 fs.copyFileSync(path.join(root,'examples/scores.csv'),path.join(results,'example.csv'));
 const shared=path.join(temporary,'shared');
 execFileSync('python3',['-m','app.build','--results-dir',results,'--catalogue',path.join(root,'configs/examples/catalogue.yaml'),'--weights',path.join(root,'configs/examples/weights.yaml'),'--eval-set',path.join(root,'configs/examples/eval-set.yaml'),'--output',shared],{cwd:root,stdio:'pipe'});
 await navigate(pathToFileURL(path.join(shared,'index.html')).href);
 assert.equal(await evaluate("document.querySelector('#modelB').value"),'Example B');
 for(const view of ['score','categories','languages','comparisons','config','warnings'])await click('[data-view='+view+']');
 assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
 // Synthetic score differences use the controlled example data and config.
 const syntheticNames=await evaluate("syntheticOptions.map(o=>o.name)"),syntheticScores=[];
 for(const name of syntheticNames){
  await change('#modelB',name);
  assert.match(await evaluate("document.querySelector('#demo').textContent"),/synthetic scores/);
  assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
  syntheticScores.push(await evaluate("document.querySelector('#cards').textContent"));
  for(const view of ['categories','languages','comparisons','config','warnings','score'])await click('[data-view='+view+']');
 }
 assert.equal(new Set(syntheticScores).size,syntheticNames.length);
 // Explicit defaults can select any embedded pair without hiding older models.
 const preferred=path.join(temporary,'preferred');
 fs.writeFileSync(path.join(results,'alternative.csv'),fs.readFileSync(path.join(root,'examples/scores.csv'),'utf8').replaceAll('Example A','Alternative A').replaceAll('Example B','Alternative B'));
 fs.writeFileSync(path.join(results,'default.yaml'),'a: Example B\nb: Alternative A\n');
 execFileSync('python3',['-m','app.build','--results-dir',results,'--catalogue',path.join(root,'configs/examples/catalogue.yaml'),'--weights',path.join(root,'configs/examples/weights.yaml'),'--eval-set',path.join(root,'configs/examples/eval-set.yaml'),'--output',preferred],{cwd:root,stdio:'pipe'});
 await navigate(pathToFileURL(path.join(preferred,'index.html')).href);
 assert.equal(await evaluate("document.querySelector('#modelA').value"),'Example B');
 assert.equal(await evaluate("document.querySelector('#modelB').value"),'Alternative A');
 assert.equal(await evaluate("document.querySelector('#cards .score-card:last-child strong').textContent"),'2.50');
 // Published preview links resolve to their own dashboard; production stays separate.
 const previewSite=path.join(temporary,'preview-site');
 execFileSync('python3',['-c',`
from pathlib import Path
import sys
from scripts.pages_preview import reconcile
from tests.test_pages_preview import Source, archive, pull
source = Source()
source.open = [pull(11, title='<script>window.injected=true</script>')]
source.previews = {11: source.previews[11]}
source.main['bundle'] = archive(files={'index.html': Path(sys.argv[1]).read_bytes()})
source.previews[11]['bundle'] = archive(files={'index.html': Path(sys.argv[2]).read_bytes()})
reconcile(Path(sys.argv[3]), source)
 `,path.join(shared,'index.html'),path.join(preferred,'index.html'),previewSite],{cwd:root,stdio:'pipe'});
 await send('Page.navigate',{url:pathToFileURL(path.join(previewSite,'pr-preview/index.html')).href});
 for(let i=0;i<50;i++){
  if(await evaluate("document.title==='Quickdash PR previews' && !!document.querySelector('tbody tr')"))break;
  await new Promise(r=>setTimeout(r,50));
 }
 assert.equal(await evaluate('document.title'),'Quickdash PR previews');
 assert.equal(await evaluate('window.injected===undefined'),true);
 assert.match(await evaluate('document.body.textContent'),/Current/);
 const previewLinks=await evaluate("({main:document.querySelector('a[href=\"../index.html\"]').href,pr:document.querySelector('a[href=\"pr-11/index.html\"]').href})");
 await navigate(previewLinks.pr);
 assert.equal(await evaluate("document.querySelector('#modelA').value"),'Example B');
 assert.equal(await evaluate("document.querySelector('#modelB').value"),'Alternative A');
 assert.equal(await evaluate("document.querySelector('#cards .score-card:last-child strong').textContent"),'2.50');
 await navigate(previewLinks.main);
 assert.equal(await evaluate("document.querySelector('#modelA').value"),'Example A');
 assert.equal(await evaluate("document.querySelector('#modelB').value"),'Example B');
 assert.equal(await evaluate("document.querySelector('#cards .score-card:last-child strong').textContent"),'-2.50');
 await navigate(pathToFileURL(path.join(preferred,'index.html')).href);
 assert.ok(await evaluate("[...document.querySelector('#modelA').options].some(o=>o.value==='Example A')"));
 await click('#swap');await click('[data-view=categories]');
 assert.equal(await evaluate("document.querySelector('#modelA').value"),'Alternative A');
 await click('#clearModels');
 await upload('#modelFile',fs.readFileSync(path.join(root,'examples/scores.csv'),'utf8'),'scores.csv');
 assert.equal(await evaluate("document.querySelector('#modelA').value"),'Example A');
 assert.equal(await evaluate("document.querySelector('#modelB').value"),'Example B');
 fs.unlinkSync(path.join(results,'default.yaml'));fs.unlinkSync(path.join(results,'alternative.csv'));
 // Starting directly on a named subset must retain out-of-set data, including the demo.
 const subset=path.join(temporary,'subset.yaml');
 fs.writeFileSync(subset,serializeSuite({version:1,name:'Reasoning only',mode:'fixed',evals:[{name:'Example reasoning'}]}));
 const fixedBuild=path.join(temporary,'fixed-build');
 execFileSync('python3',['-m','app.build','--results-dir',results,'--catalogue',path.join(root,'configs/examples/catalogue.yaml'),'--weights',path.join(root,'configs/examples/weights.yaml'),'--eval-set',subset,'--output',fixedBuild],{cwd:root,stdio:'pipe'});
 await navigate(pathToFileURL(path.join(fixedBuild,'index.html')).href);
 assert.match(await evaluate("document.querySelector('#coverage').textContent"),/Reasoning only.*Complete.*2 extra measurements excluded/);
 await click('[data-view=config]');assert.match(await evaluate("document.querySelector('#view').textContent"),/Example math/);
 // Caveats follow comparison membership; excluded data remains inspectable with its caveat.
 const caveated=structuredClone(fixture);caveated.evals[1].warning='Example math requires review.';
 await upload('#configFile',serializeCatalogue(caveated),'caveat.yaml');
 await click('[data-view=warnings]');
 assert.match(await evaluate("document.querySelector('#view').textContent"),/Not used.*Example math/s);
 assert.doesNotMatch(await evaluate("document.querySelector('#view').textContent"),/Example math requires review/);
 await click('[data-view=config]');
 assert.match(await evaluate("document.querySelector('[data-eval=\"Example math\"] .normalization-info').textContent"),/Example math requires review/);
 await upload('#suiteFile',serializeSuite({version:1,name:'Freeform',mode:'available'}),'freeform.yaml');
 await click('[data-view=warnings]');
 assert.match(await evaluate("document.querySelector('#view').textContent"),/Config caveat.*Example math requires review/s);
 // Weighted components use fictional scores and remain inspectable after exclusion.
 await click('#clearModels');await click('[data-view=config]');
 const levels=['low','medium','high','top'];
 const componentCatalogue={version:1,name:'Component example',evals:[{name:'Poly example',category:'Reasoning',match:{regex:'poly_.+'},metric:'acc',metric_filter:'none',score:{scale:1},aggregation:{components:levels.map((name,i)=>({name,match:{regex:'poly_.+_'+name},relative_weight:2**i})),note:'Fictional component fixture.'}}],languages:['en','de'].map((lang,i)=>({tasks:levels.map(l=>'poly_'+lang+'_'+l),scope:'single',language:i?'deu_Latn':'eng_Latn'}))};
 await upload('#configFile',serializeCatalogue(componentCatalogue),'components.yaml');
 await upload('#weightsFile',serializeWeightProfile({version:1,name:'Component weights',weights:{Reasoning:1},english_weights:{Reasoning:.5}}),'weights.yaml');
 const componentCSV=(model,omit=false)=>['checkpoint,task,metric,filter,n_shot,harness,backend,value',...['en','de'].flatMap(lang=>levels.flatMap((l,i)=>omit&&lang==='en'&&l==='top'?[]:[`${model},poly_${lang}_${l},acc,none,0,test,cpu,${model==='Component A'?(lang==='en'?[.6,.3,.15,0][i]:.2):(lang==='en'?.3:.1)}`]))].join('\n');
 await upload('#modelFile',componentCSV('Component A'),'a.csv');
 await upload('#modelFile',componentCSV('Component B'),'b.csv');
 assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
 assert.deepEqual(await evaluate("[...document.querySelectorAll('.score-card strong')].map(e=>e.textContent)"),['16.00','20.00','-4.00']);
 for(const view of ['categories','languages']){
  await click('[data-view='+view+']');
  const parent= view==='categories'?'[data-kind=eval][data-label="Poly example"]':'[data-kind=language][data-label=eng_Latn]';
  const expected=view==='categories'?'16.00':'12.00';
  assert.equal(await evaluate(`document.querySelector(${JSON.stringify(parent)}+' > summary').children[2].textContent`),expected);
  const leaf='[data-kind=variant][data-label=poly_en_low]';
  assert.deepEqual(await evaluate(`Array.from(document.querySelector(${JSON.stringify(leaf)}).children).slice(2).map(e=>e.textContent)`),['60.00','30.00','30.00','1 · 6.67%','4.000','2.000']);
  await evaluate("document.querySelectorAll('.breakdown-node').forEach(e=>e.open=true)");
  const aligned=await evaluate(`{const header=[...document.querySelector('.tree-head').children].map(e=>e.getBoundingClientRect().right),row=[...document.querySelector(${JSON.stringify(leaf)}).children].map(e=>e.getBoundingClientRect().right);header.every((x,i)=>i===0||Math.abs(x-row[i])<2)}`);
  assert.equal(aligned,true);
  if(view==='languages'){await click('[data-language-sort=componentA]');assert.match(await evaluate("document.querySelector('#view').textContent"),/Group contribution/);}
 }
 await click('[data-view=config]');
 assert.match(await evaluate("document.querySelector('.component-info').textContent"),/sum\(relative_weight × normalized score\) \/ 15/);
 await evaluate(`window.originalCreate=URL.createObjectURL;window.originalClick=HTMLAnchorElement.prototype.click;URL.createObjectURL=b=>{window.exportBlob=b;return 'blob:test'};HTMLAnchorElement.prototype.click=function(){};`);
 await click('#exportConfig');assert.deepEqual(await evaluate('exportBlob.text().then(parseCatalogue)'),componentCatalogue);
 await evaluate('URL.createObjectURL=originalCreate;HTMLAnchorElement.prototype.click=originalClick');
 await upload('#configFile',serializeCatalogue(componentCatalogue).replace('relative_weight: 1','relative_weight: 0'),'invalid-components.yaml');
 assert.match(await evaluate("document.querySelector('#error').textContent"),/positive/);
 assert.equal(await evaluate("document.querySelector('.score-card strong').textContent"),'16.00');
 await upload('#modelFile',componentCSV('Component C',true),'incomplete.csv');
 assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
 assert.deepEqual(await evaluate("[...document.querySelectorAll('.score-card strong')].map(e=>e.textContent)"),['20.00','10.00','10.00']);
 await click('[data-view=warnings]');assert.match(await evaluate("document.querySelector('#view').textContent"),/Incomplete components.*top: missing/s);
 await click('[data-view=config]');
 await click('[data-task=poly_en_low] > summary');
 assert.match(await evaluate("document.querySelector('[data-task=poly_en_low] .task-details').textContent"),/Excluded from comparison/);
 const componentSet={version:1,name:'All component tasks',mode:'fixed',evals:[{name:'Poly example',variants:componentCatalogue.languages.flatMap(g=>g.tasks.map(task=>({task,n_shot:0})))}]};
 const cardsBeforeRejectedConfig=await evaluate("document.querySelector('#cards').textContent");
 for(const modify of [s=>s.evals[0].variants.pop(),s=>s.evals[0].variants[0].n_shot=5,s=>delete s.evals[0].variants[0].n_shot]){
  const bad=structuredClone(componentSet);modify(bad);
  await upload('#suiteFile',serializeSuite(bad),'incompatible-set.yaml');
  assert.match(await evaluate("document.querySelector('#error').textContent"),/Incompatible aggregation config/);
  assert.equal(await evaluate("document.querySelector('#cards').textContent"),cardsBeforeRejectedConfig);
 }
 const incompatibleCatalogue=structuredClone(componentCatalogue);incompatibleCatalogue.evals[0].select={regex:'poly_.+_(low|medium|high)'};
 await upload('#configFile',JSON.stringify(incompatibleCatalogue),'incompatible-catalogue.yaml');
 assert.match(await evaluate("document.querySelector('#error').textContent"),/Incompatible aggregation config.*top/);
 assert.equal(await evaluate("document.querySelector('#cards').textContent"),cardsBeforeRejectedConfig);
 await upload('#suiteFile',serializeSuite(componentSet),'components-set.yaml');
 assert.match(await evaluate("document.querySelector('#coverage').textContent"),/INCOMPLETE.*4\/8 requirements shared/);
 await click('[data-view=comparisons]');await change('#compareGroup','variant');await change('#compareMeasure','weighted');
 assert.match(await evaluate("document.querySelector('#view').textContent"),/10.0000 index points/);
 // Editable weights resolve a category missing from the loaded profile.
 const beforeCategoryEdit=await evaluate("document.querySelector('#cards').textContent");
 const customCategory=structuredClone(componentCatalogue);customCategory.evals[0].category='Custom';
 await click('[data-view=config]');await upload('#configFile',serializeCatalogue(customCategory),'custom-category.yaml');
 await click('[data-view=warnings]');assert.match(await evaluate("document.querySelector('#view').textContent"),/No category weight/);
 await click('[data-view=score]');
 await evaluate(`{for(const input of document.querySelectorAll('[data-weight]')){input.value=input.dataset.weight==='Custom'?'1':'0';document.querySelector('#view').onchange({target:input});}}`);
 assert.equal(await evaluate("document.querySelector('#cards').textContent"),beforeCategoryEdit);
 await click('[data-view=warnings]');assert.doesNotMatch(await evaluate("document.querySelector('#view').textContent"),/No category weight/);
 // Smoke-test shipped configs with the Pages sample without fixing their scoring outcomes.
 const sample=path.join(temporary,'sample'),resultsDir=path.join(temporary,'empty-results');fs.mkdirSync(resultsDir);
 execFileSync('python3',['-m','app.build','--results-dir',resultsDir,'--sample-csv','examples/sample-evals.csv','--output',sample],{cwd:root,stdio:'pipe'});
 await navigate(pathToFileURL(path.join(sample,'index.html')).href);
 assert.match(await evaluate("document.querySelector('#modelA').value"),/^SAMPLE/);
 assert.deepEqual(await evaluate("DATA.suites.map(s=>s.file).sort()"),shippedSets.files);
 assert.deepEqual(await evaluate("DATA.profiles.map(p=>p.file).sort()"),shippedProfiles.files);
 assert.equal(await evaluate("DATA.suites[Number(document.querySelector('#suitePreset').value)].file"),shippedSets.defaultFile);
 assert.equal(await evaluate("DATA.profiles[Number(document.querySelector('#weightPreset').value)].file"),shippedProfiles.defaultFile);
 // The generated catalogue contains every eval and language, with no filesystem dependency.
 const exportedCatalogue=fs.readFileSync(path.join(sample,'catalogue.yaml'),'utf8');
 assert.deepEqual(parseCatalogue(exportedCatalogue),require('../app/catalogue_io.cjs').loadCatalogue(path.join(root,'configs/catalogue.yaml')));
 const sampleScore=await evaluate("document.querySelector('#cards').textContent");
 await click('[data-view=config]');await upload('#configFile',exportedCatalogue,'portable-catalogue.yaml');
 assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
 assert.equal(await evaluate("document.querySelector('#cards').textContent"),sampleScore);
 // A manifest needs files on disk; importing it must preserve the current dashboard.
 await upload('#configFile',fs.readFileSync(path.join(root,'configs/catalogue.yaml'),'utf8'),'catalogue-manifest.yaml');
 assert.match(await evaluate("document.querySelector('#error').textContent"),/manifest.*build/i);
 assert.equal(await evaluate("document.querySelector('#cards').textContent"),sampleScore);
 await upload('#configFile',exportedCatalogue,'portable-catalogue.yaml');

 assert.equal(await evaluate("document.querySelector('#cards').hidden"),false);
 for(let s=0;s<shippedSets.files.length;s++)for(let p=0;p<shippedProfiles.files.length;p++){
  await change('#suitePreset',String(s));await change('#weightPreset',String(p));
  assert.equal(await evaluate("document.querySelector('#suitePreset').value"),String(s));
  assert.equal(await evaluate("document.querySelector('#weightPreset').value"),String(p));
  const strictCards=await evaluate("document.querySelector('#cards').textContent");
  for(const matching of ['relaxed','strict']){
   await change('#matching',matching);
   assert.equal(await evaluate("document.querySelector('#matching').value"),matching);
   for(const view of ['categories','languages','comparisons','config','warnings','score']){
    await click('[data-view='+view+']');
    assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
   }
  }
  assert.equal(await evaluate("document.querySelector('#cards').textContent"),strictCards);
 }
 for(const name of syntheticNames){
  await change('#modelB',name);
  assert.match(await evaluate("document.querySelector('#demo').textContent"),/synthetic scores/);
  assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
  for(const view of ['categories','languages','comparisons','config','warnings','score'])await click('[data-view='+view+']');
 }
 await change('#modelB',await evaluate("document.querySelector('#modelA').value"));
 assert.match(await evaluate("document.querySelector('#demo').textContent"),/Sample dataset/);
 await click('#clearModels');
 assert.equal(await evaluate("document.querySelector('#modelA').options.length"),0);
 // Controlled few-shot data groups warnings by actual setting, suppresses duplicate
 // missing-set warnings, and exposes excluded tasks in the catalogue view.
 await navigate(pathToFileURL(path.join(empty,'index.html')).href);
 const shotCatalogue={version:1,name:'Shot fixture',evals:[{name:'Shot reasoning',category:'Reasoning',match:{regex:'shot_(en|fr|de)'},metric:'acc',metric_filter:'none',shots:5,score:{scale:1}}],languages:[
  {tasks:['shot_en'],scope:'single',language:'eng_Latn'},
  {tasks:['shot_fr'],scope:'single',language:'fra_Latn'},
  {tasks:['shot_de'],scope:'single',language:'deu_Latn'},
 ]};
 const shotAvailable={version:1,name:'Available shots',mode:'available'};
 const shotRequired={version:1,name:'Required shots',mode:'fixed',evals:[{name:'Shot reasoning'}]};
 await click('[data-view=config]');await upload('#suiteFile',serializeSuite(shotAvailable),'available-shots.yaml');
 await upload('#configFile',serializeCatalogue(shotCatalogue),'shot-catalogue.yaml');
 await upload('#weightsFile',serializeWeightProfile({version:1,name:'Shot weights',weights:{Reasoning:1}}),'shot-weights.yaml');
 await upload('#modelFile','checkpoint,task,metric,filter,n_shot,harness,backend,value\nShot model,shot_en,acc,none,5,test,cpu,0.8\nShot model,shot_fr,acc,none,0,test,cpu,0.6\nShot model,shot_de,acc,none,0,test,cpu,0.4','shot-model.csv');
 await change('#modelB','Shot model');
 for(const expected of [5,25]){
  await click('[data-view=config]');
  shotCatalogue.evals[0].shots=expected;
  await upload('#configFile',serializeCatalogue(shotCatalogue),'shot-catalogue.yaml');
  await upload('#suiteFile',serializeSuite(shotRequired),'required-shots.yaml');
  assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
  const strictScores=await evaluate("[...document.querySelectorAll('.score-card strong')].map(e=>e.textContent)");
  assert.equal(await evaluate("document.querySelector('.score-card strong').textContent"),expected===5?'80.00':'—');
  await click('[data-view=warnings]');
  const warnings=await evaluate("[...document.querySelectorAll('#view tbody tr')].map(r=>({type:r.cells[0].textContent,eval:r.cells[1].textContent,detail:r.cells[3].textContent,tasks:[...r.querySelectorAll('details')].map(e=>e.textContent).join(' ')}))");
  assert.deepEqual(warnings.map(w=>[w.type,w.eval]),Array.from({length:expected===5?1:2},()=>['Few-shot mismatch excluded','Shot reasoning']));
  assert.ok(warnings[0].detail.startsWith(`2 tasks use 0 shots; expected ${expected}.`));
  for(const task of ['shot_fr','shot_de'])assert.ok(warnings[0].tasks.includes(task));
  if(expected===25){assert.ok(warnings[1].detail.startsWith('1 task uses 5 shots; expected 25.'));assert.match(warnings[1].tasks,/shot_en/);}
  assert.match(await evaluate("document.querySelector('#coverage').textContent"),/INCOMPLETE/);
  await click('[data-view=config]');await click('.catalogue-eval[data-eval="Shot reasoning"] > summary');
  await new Promise(r=>setTimeout(r,50));
  assert.equal(await evaluate("document.querySelectorAll('.catalogue-eval[data-eval=\"Shot reasoning\"] .has-missing-field').length"),expected===5?2:3);
  await upload('#suiteFile',serializeSuite(shotAvailable),'available-shots.yaml');
  assert.deepEqual(await evaluate("[...document.querySelectorAll('.score-card strong')].map(e=>e.textContent)"),strictScores);
  const strictCards=await evaluate("document.querySelector('#cards').textContent");
  await change('#matching','relaxed');
  assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
  assert.match(await evaluate("document.querySelector('#matchingNotice').textContent"),/INCONSISTENT EVALUATION SETTINGS/);
  assert.equal(await evaluate("document.querySelector('.score-card strong').textContent"),'60.00');
  await click('[data-view=warnings]');
  assert.ok((await evaluate("document.querySelector('#view').textContent")).includes(`Using 0 shots despite expected ${expected}`));
  if(expected===25)assert.match(await evaluate("document.querySelector('#view').textContent"),/Using 5 shots despite expected 25/);
  await change('#matching','strict');
  assert.equal(await evaluate("document.querySelector('#cards').textContent"),strictCards);
 }
 // Named sets select a corrected protocol once and never substitute an older run.
 await navigate(pathToFileURL(path.join(empty,'index.html')).href);
 const protocolCatalogue={version:1,name:'Protocol fixture',evals:[
  {name:'Original protocol',category:'Reasoning',match:{name:'protocol'},metric:'accuracy_avg',metric_filter:'',shots:0,score:{scale:1}},
  {name:'CoT protocol',category:'Reasoning',match:{name:'protocol_cot'},metric:'pass@1',metric_filter:'all',shots:0,score:{scale:1}},
 ],languages:[{tasks:['protocol','protocol_cot'],scope:'single',language:'eng_Latn'}]};
 await click('[data-view=config]');await upload('#suiteFile',serializeSuite(shotAvailable),'available.yaml');
 await upload('#configFile',serializeCatalogue(protocolCatalogue),'protocols.yaml');
 await upload('#weightsFile',serializeWeightProfile({version:1,name:'Protocol weights',weights:{Reasoning:1}}),'weights.yaml');
 await upload('#suiteFile',serializeSuite({version:1,name:'Corrected protocol',mode:'fixed',evals:[{name:'CoT protocol'}]}),'corrected.yaml');
 const protocolRows=['checkpoint,task,metric,filter,n_shot,harness,backend,value',
  'Protocol A,protocol,accuracy_avg,,0,test,cpu,1','Protocol B,protocol,accuracy_avg,,0,test,cpu,1',
  'Protocol A,protocol_cot,pass@1,all,0,test,cpu,0.6','Protocol B,protocol_cot,pass@1,all,0,test,cpu,0.4',
  'Protocol A,protocol_cot,pass@4,all,0,test,cpu,1','Protocol B,protocol_cot,pass@4,all,0,test,cpu,1',
  'Original only,protocol,accuracy_avg,,0,test,cpu,1'];
 await upload('#modelFile',protocolRows.join('\n'),'protocols.csv');
 await change('#modelA','Protocol A');await change('#modelB','Protocol B');
 assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
 assert.deepEqual(await evaluate("[...document.querySelectorAll('.score-card strong')].map(e=>e.textContent)"),['60.00','40.00','20.00']);
 assert.match(await evaluate("document.querySelector('#coverage').textContent"),/Complete.*1\/1 requirements shared/);
 await click('[data-view=warnings]');assert.match(await evaluate("document.querySelector('#view').textContent"),/Not used.*Original protocol/s);
 await click('[data-view=config]');
 assert.ok(await evaluate("document.querySelector('[data-eval=\"Original protocol\"]')!==null"));
 assert.ok(await evaluate("document.querySelector('[data-eval=\"CoT protocol\"]')!==null"));
 await change('#modelB','Original only');
 for(const matching of ['strict','relaxed']){
  await change('#matching',matching);
  assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
  assert.deepEqual(await evaluate("[...document.querySelectorAll('.score-card strong')].map(e=>e.textContent)"),['—','—','—']);
  assert.match(await evaluate("document.querySelector('#coverage').textContent"),/INCOMPLETE.*0\/1 requirements shared/);
  await click('[data-view=warnings]');assert.match(await evaluate("document.querySelector('#view').textContent"),/Missing suite data.*CoT protocol.*Original only/s);
 }
 // Real A/B few-shot differences are allowed only through the explicit runtime option.
 await navigate(pathToFileURL(path.join(empty,'index.html')).href);
 const expectedShots=structuredClone(fixture);expectedShots.evals[0].shots=5;
 await click('[data-view=config]');await upload('#suiteFile',serializeSuite({version:1,name:'Any example',mode:'available'}),'any.yaml');
 await click('[data-view=config]');await upload('#configFile',serializeCatalogue(expectedShots),'expected-shots.yaml');
 await change('#weightPreset','1');
 const shotCSV=(value='0.625')=>'checkpoint,task,metric,filter,n_shot,harness,backend,value\nShots A,example_reasoning_en,acc_norm,none,5,test,cpu,1\nShots B,example_reasoning_en,acc_norm,none,0,test,cpu,'+value;
 await upload('#modelFile',shotCSV(),'shots.csv');
 const noShared=await evaluate("document.querySelector('#cards').textContent");
 await click('[data-view=score]');await click('[data-score-category=Reasoning]');
 assert.deepEqual(await evalDelta(),{text:'—',classes:'num '});
 await click('[data-view=config]');
 await change('#matching','relaxed');
 assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
 assert.match(await evaluate("document.querySelector('#matchingNotice').textContent"),/INCONSISTENT/);
 assert.equal(await evaluate("document.querySelector('#cards .score-card:last-child strong').textContent"),'50.00');
 await click('[data-view=warnings]');assert.match(await evaluate("document.querySelector('#view').textContent"),/Using 0 shots despite expected 5/);
 await change('#matching','strict');assert.equal(await evaluate("document.querySelector('#cards').textContent"),noShared);
 // Set overrides reinterpret all models, while catalogue export retains defaults.
 await click('[data-view=config]');
 const shotSet={version:1,name:'Override example',mode:'fixed',evals:[{name:'Example reasoning',shots:0,exclude_languages:['fra_Latn']}]};
 await upload('#suiteFile',serializeSuite(shotSet),'override.yaml');
 assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
 assert.match(await evaluate("document.querySelector('#view').textContent"),/Eval-set overrides: shots = 0/);
 await change('#matching','relaxed');
 assert.match(await evaluate("document.querySelector('#coverage').textContent"),/1\/1 requirements shared/);
 await click('[data-view=warnings]');
 assert.match(await evaluate("document.querySelector('#view').textContent"),/Using 5 shots despite expected 0/);
 await change('#matching','strict');await click('[data-view=config]');
 const beforeInvalidSet=await evaluate("document.querySelector('#cards').textContent");
 await upload('#suiteFile',serializeSuite({...shotSet,exclude_languages:['kat_Geor']}),'unknown-language.yaml');
 assert.match(await evaluate("document.querySelector('#error').textContent"),/no catalogue assignment/);
 assert.equal(await evaluate("document.querySelector('#cards').textContent"),beforeInvalidSet);
 const alternateCSV=shotCSV()+'\nShots A,example_reasoning_en,acc,,0,test,cpu,0.25\nShots B,example_reasoning_en,acc,,0,test,cpu,1';
 await click('#clearModels');await upload('#modelFile',alternateCSV,'alternates.csv');await click('[data-view=config]');
 assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
 const metricSet=structuredClone(shotSet);Object.assign(metricSet.evals[0],{metric:'acc',metric_filter:''});
 await upload('#suiteFile',serializeSuite(metricSet),'metric.yaml');
 assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
 assert.equal(await evaluate("document.querySelector('#cards .score-card:last-child strong').textContent"),'-100.00');
 assert.match(await evaluate("document.querySelector('#view').textContent"),/Eval-set overrides: metric = "acc", metric_filter = "", shots = 0/);
 await evaluate(`window.originalCreate=URL.createObjectURL;window.originalClick=HTMLAnchorElement.prototype.click;URL.createObjectURL=b=>{window.exportBlob=b;return 'blob:test'};HTMLAnchorElement.prototype.click=function(){};`);
 await click('#exportConfig');assert.deepEqual(await evaluate('exportBlob.text().then(parseCatalogue)'),expectedShots);
 await click('#exportSuite');assert.deepEqual(await evaluate('exportBlob.text().then(parseSuite)'),metricSet);
 await evaluate('URL.createObjectURL=originalCreate;HTMLAnchorElement.prototype.click=originalClick');
 await upload('#suiteFile',serializeSuite({version:1,name:'Any example',mode:'available'}),'any.yaml');
 assert.equal(await evaluate("document.querySelector('#cards').textContent"),noShared);
 // A present excluded language warns; absent excluded languages are not requirements.
 const frenchCSV='checkpoint,task,metric,filter,n_shot,harness,backend,value\nShots A,example_reasoning_fr,acc_norm,none,5,test,cpu,0.5\nShots B,example_reasoning_fr,acc_norm,none,5,test,cpu,0.5';
 await click('#clearModels');await upload('#modelFile',shotCSV()+'\n'+frenchCSV.split('\n').slice(1).join('\n'),'languages.csv');await click('[data-view=config]');
 assert.equal(await evaluate("document.querySelector('#error').textContent"),'');
 await upload('#suiteFile',serializeSuite({...shotSet,exclude_languages:['fra_Latn']}),'exclusions.yaml');
 await click('[data-view=warnings]');assert.match(await evaluate("document.querySelector('#view').textContent"),/Not used.*example_reasoning_fr/s);
 await click('[data-view=config]');await upload('#suiteFile',serializeSuite({version:1,name:'Any example',mode:'available'}),'any.yaml');
 await click('#clearModels');await upload('#modelFile',shotCSV('bad'),'invalid-alternative.csv');
 const beforeRelax=await evaluate("document.querySelector('#cards').textContent");
 await change('#matching','relaxed');
 assert.equal(await evaluate("document.querySelector('#matching').value"),'strict');
 assert.match(await evaluate("document.querySelector('#error').textContent"),/Invalid score/);
 assert.equal(await evaluate("document.querySelector('#cards').textContent"),beforeRelax);
 // Address fragments restore a complete published comparison without storing CSVs.
 const waitFor=async expression=>{for(let i=0;i<100;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,50));}assert.fail('Timed out: '+expression);};
 const openLink=async url=>{await send('Page.navigate',{url:'about:blank'});await new Promise(r=>setTimeout(r,100));await navigate(url);};
 await openLink(pathToFileURL(path.join(shared,'index.html')).href);
 await click('#swap');await change('#matching','relaxed');await click('[data-aggregate=english_eval]');
 await change('[data-weight=Reasoning]','0.6');await change('[data-weight=Math]','0.4');await change('[data-english-weight=Reasoning]','0.7');
 await click('[data-view=comparisons]');await change('#category','Reasoning');await change('#language','eng_Latn');
 await change('#compareMeasure','weighted');await click('[data-sort-column=weightedDelta]');await click('[data-expand-eval="Example reasoning"]');
 const link=await evaluate('location.href'),linkedCards=await evaluate("document.querySelector('#cards').textContent"),linkedView=await evaluate("document.querySelector('#view').textContent");
 assert.equal(new URL(link).search,'');assert.ok(new URL(link).hash.includes('view=comparisons'));
 await openLink(link);
 assert.equal(await evaluate("document.querySelector('#linkNotice').hidden"),true);
 assert.equal(await evaluate("document.querySelector('#cards').textContent"),linkedCards);
 assert.equal(await evaluate("document.querySelector('#view').textContent"),linkedView);
 assert.equal(await evaluate("document.querySelector('#modelA').value"),'Example B');
 assert.equal(await evaluate("document.querySelector('#category').value"),'Reasoning');
 assert.equal(await evaluate("document.querySelector('#language').value"),'eng_Latn');
 assert.equal(await evaluate("document.querySelector('#matching').value"),'relaxed');
 // Tab navigation supplies useful browser history; in-tab edits replace that entry.
 await click('[data-view=languages]');await click('[data-language-sort=delta]');
 await evaluate("document.querySelector('.breakdown-node').open=true");
 await waitFor("new URLSearchParams(location.hash.slice(1)).has('open')");
 const languageLink=await evaluate('location.href');
 await click('[data-view=categories]');await evaluate('history.back()');
 await waitFor("document.querySelector('[data-view=languages]').classList.contains('active')");
 assert.ok(await evaluate("document.querySelectorAll('.breakdown-node[open]').length>0"));
 await evaluate('history.forward()');await waitFor("document.querySelector('[data-view=categories]').classList.contains('active')");
 await openLink(languageLink);assert.ok(await evaluate("document.querySelectorAll('.breakdown-node[open]').length>0"));
 await click('[data-view=config]');
 await evaluate("document.querySelector('.catalogue-eval').open=true");
 await waitFor("!!document.querySelector('.catalogue-variant')");
 await evaluate("document.querySelector('.catalogue-variant').open=true");
 await waitFor("JSON.parse(new URLSearchParams(location.hash.slice(1)).get('open')||'[]').some(k=>k.startsWith('task:'))");
 await openLink(await evaluate('location.href'));
 assert.ok(await evaluate("!!document.querySelector('.catalogue-eval[open] .catalogue-variant[open] .task-details').textContent"));
 // Stale or malformed links retain the live comparison and remain visible as errors.
 const beforeBad=await evaluate("document.querySelector('#cards').textContent");
 await evaluate("location.hash='#view=score&modelA=missing-model'");
 await waitFor("!document.querySelector('#linkNotice').hidden");
 assert.match(await evaluate("document.querySelector('#linkNotice').textContent"),/missing-model/);
 assert.equal(await evaluate("document.querySelector('#cards').textContent"),beforeBad);
 await new Promise(r=>setTimeout(r,100));assert.ok(await evaluate("location.hash.includes('missing-model')"));
 for(const parameter of ['suite','profile','category','language']){
  await evaluate(`location.hash='#view=score&${parameter}=missing-${parameter}'`);
  await waitFor(`document.querySelector('#linkNotice').textContent.includes(${JSON.stringify(parameter==='suite'||parameter==='profile'?'not available on this page':'missing-'+parameter)})`);
  assert.equal(await evaluate("document.querySelector('#cards').textContent"),beforeBad);
 }
 await click('[data-view=score]');
 await click('[data-view=config]');await upload('#configFile',fs.readFileSync(path.join(root,'configs/examples/catalogue.yaml'),'utf8'),'temporary.yaml');
 assert.ok(await evaluate("new URLSearchParams(location.hash.slice(1)).get('local')==='1'"));
 assert.match(await evaluate("document.querySelector('#linkNotice').textContent"),/temporary uploads/);
 await openLink(await evaluate('location.href'));
 assert.match(await evaluate("document.querySelector('#linkNotice').textContent"),/Could not restore.*temporary uploads/);
 // Profile and suite references use filenames, independent of selector order.
 await openLink(pathToFileURL(path.join(sample,'index.html')).href);
 const linkedPresets=await evaluate("({profile:DATA.profiles.at(-1),suite:DATA.suites.at(-1)})");
 await change('#weightPreset',String(shippedProfiles.files.length-1));
 await change('#suitePreset',String(shippedSets.files.length-1));
 await click('[data-view=score]');
 const linkedCategory=await evaluate("document.querySelector('#scoreCategory').options[0].value");
 await change('#scoreCategory',linkedCategory);
 const presetLink=await evaluate('location.href'),presetCards=await evaluate("document.querySelector('#cards').textContent");
 assert.equal(new URLSearchParams(new URL(presetLink).hash.slice(1)).get('profile'),linkedPresets.profile.file);
 assert.equal(new URLSearchParams(new URL(presetLink).hash.slice(1)).get('suite'),linkedPresets.suite.file);
 await openLink(presetLink);
 assert.equal(await evaluate("document.querySelector('#weightPreset').selectedOptions[0].textContent"),linkedPresets.profile.config.name);
 assert.equal(await evaluate("document.querySelector('#suitePreset').selectedOptions[0].textContent"),linkedPresets.suite.config.name);
 assert.equal(await evaluate("document.querySelector('#scoreCategory').value"),linkedCategory);
 assert.equal(await evaluate("document.querySelector('#cards').textContent"),presetCards);
 assert.deepEqual(errors,[]);assert.deepEqual(network,[],'Loading and comparing local files must not send HTTP requests');
 console.log('Public browser checks passed: empty start, shared models, independent weights and eval sets, required coverage, temporary uploads, rollback, Pages sample, synthetic choices, clear models and no uploads.');
}finally{
 ws?.close();fs.rmSync(temporary,{recursive:true,force:true});
}
