import {storagePlan,writePlan,readPlan,restorePlan,comparablePlan,destroyRehearsal,recoveryJournal,rehearseRestore} from '../backup-storage.mjs';
import {digest} from '../backup-core.mjs';
if(!crypto.subtle || !crypto.randomUUID){document.querySelector('#status').textContent='BLOCKED: this preview is not a secure context. Run these checks over HTTPS or trusted localhost. No checks or writes were performed.';throw Error('Secure context required for recovery tests.');}
const prefix='cj-backup-rehearsal-test-'+crypto.randomUUID()+'-';
const empty=()=>({version:1,nodes:[],edges:[],sources:[],trail:[]});
const sample={library:[{id:'test',tracks:[]}],recordings:[{artist:'Synthetic artist',title:'Synthetic recording',url:'https://soundcloud.com/fixture/recording'}],automatic_research:{version:1,jobs:{},graph:empty()},concepts:{contexts:[],overrides:[]},exploration:empty()};
const equal=async(a,b)=>{if(await digest(comparablePlan(a))!==await digest(comparablePlan(b)))throw Error('Readback differs');};
let passed=0,failed=0;
async function check(name,fn){const li=document.createElement('li');try{await fn();li.textContent='PASS · '+name;passed++;}catch(e){li.textContent='FAIL · '+name+' · '+e.message;failed++;}document.querySelector('#results').append(li);}
try{
 await check('Write and read library, extra recordings, research, concepts and exploration',async()=>{await writePlan(storagePlan(sample),prefix);await equal(storagePlan(sample),await readPlan(prefix));});
 await check('Restore commits and removes its recovery journal',async()=>{const plan=storagePlan({...sample,library:[{id:'new-test',tracks:[]}]});await restorePlan(plan,prefix);await equal(plan,await readPlan(prefix));if(await recoveryJournal(prefix))throw Error('Journal remains');});
 await check('A later-store failure rolls back earlier-store writes',async()=>{const before=await readPlan(prefix),bad=storagePlan(sample);bad.concepts.contexts=[['uncloneable',()=>{}]];let rejected=false;try{await restorePlan(bad,prefix);}catch(e){rejected=/previous browser data was recovered/.test(e.message);}if(!rejected)throw Error('Failure was not reported as recovered');await equal(before,await readPlan(prefix));});
 await check('Separate storage rehearsal succeeds without touching current stores',async()=>{await rehearseRestore(sample);});
}finally{await check('Temporary test databases are removed',()=>destroyRehearsal(prefix));document.querySelector('#status').textContent=`${passed} passed · ${failed} failed. This is browser database verification, not physical Safari acceptance.`;}
