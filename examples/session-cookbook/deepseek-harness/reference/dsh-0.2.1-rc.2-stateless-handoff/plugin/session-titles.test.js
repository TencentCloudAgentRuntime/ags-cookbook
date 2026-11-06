import test from 'node:test'
import assert from 'node:assert/strict'
import { withSessionTitles, dshEventTitle, piEventTitle } from './session-titles.js'
const key = { SpaceId: 'space', UserId: 'user', SessionId: 'session' }
const event = (sequence, title) => ({ EventId: 'event-'+sequence, Extensions: JSON.stringify({ dshEvent: { seq: sequence, type: 'session/title', data: { title } } }) })

test('new DSH titles are mirrored only after their native event persists', async () => {
 const calls=[];const request=withSessionTitles(async(a,p)=>{calls.push([a,p]);return {}},dshEventTitle)
 await request('AppendEvent',{...key,Event:event(1,'自动标题')})
 assert.deepEqual(calls.map(c=>c[0]),['AppendEvent','ModifySession'])
 assert.equal(calls[1][1].Title,'自动标题')
 await request('DescribeSession',key);await request('DescribeSessions',{SpaceId:'space'})
 assert.deepEqual(calls.slice(2).map(c=>c[0]),['DescribeSession','DescribeSessions'])
})

test('failed native appends never change Title',async()=>{
 const calls=[];const request=withSessionTitles(async(a)=>{calls.push(a);throw Error('append failure')},dshEventTitle)
 await assert.rejects(request('AppendEvent',{...key,Event:event(1,'未保存')}),/append failure/)
 assert.deepEqual(calls,['AppendEvent'])
})

test('a failed old title stays observable but cannot overwrite a newer successful title on retry',async()=>{
 const titles=[];let fail=true
 const request=withSessionTitles(async(a,p)=>{if(a==='ModifySession'){titles.push(p.Title);if(fail){fail=false;throw Error('title API failed')}}return {}},dshEventTitle)
 await assert.rejects(request('AppendEvent',{...key,Event:event(1,'旧标题')}),/title API failed/)
 await request('AppendEvent',{...key,Event:event(2,'最新标题')})
 await request('AppendEvent',{...key,Event:event(1,'旧标题')})
 assert.deepEqual(titles,['旧标题','最新标题'])
})

test('retrying an event whose title update failed retries the pending title',async()=>{
 let tries=0;const request=withSessionTitles(async(a)=>{if(a==='ModifySession'&&++tries===1)throw Error('offline');return {}},dshEventTitle)
 const p={...key,Event:event(1,'标题')};await assert.rejects(request('AppendEvent',p),/offline/)
 await request('AppendEvent',p);assert.equal(tries,2)
})

test('pi clearing a native name sends an explicit empty Title and keeps it after a later user append',async()=>{
 const titles=[];const request=withSessionTitles(async(a,p)=>{if(a==='ModifySession')titles.push(p.Title);return {}},piEventTitle)
 const pi=(seq,name)=>({...key,Event:{Extensions:JSON.stringify({pi:{seq,entry:{type:'session_info',name}}})}})
 await request('AppendEvent',pi(0,'名称'));await request('AppendEvent',pi(1,''))
 await request('AppendEvent',{...key,Event:{Content:{Role:'user'},Extensions:JSON.stringify({pi:{seq:2,entry:{type:'message'}}})}})
 assert.deepEqual(titles,['名称','',''])
})

test('concurrent native title appends stay ordered within a session',async()=>{
 const titles=[];const request=withSessionTitles(async(a,p)=>{if(a==='ModifySession'){await Promise.resolve();titles.push(p.Title)}return {}},dshEventTitle)
 await Promise.all([request('AppendEvent',{...key,Event:event(1,'一')}),request('AppendEvent',{...key,Event:event(2,'二')})])
 assert.deepEqual(titles,['一','二'])
})

test('a clear written by this protocol survives a new client without mutating anything on read',async()=>{
 let saved;let title='';let updates=0
 const api=async(a,p)=>{
  if(a==='AppendEvent'&&p.Event.Actions?.StateDelta)saved=JSON.parse(p.Event.Actions.StateDelta).sessionTitleSync
  if(a==='AppendEvent'&&!p.Event.Actions)title='user fallback'
  if(a==='ModifySession'){updates++;title=p.Title}
  if(a==='DescribeSession')return {Session:{Title:title,State:{CustomState:JSON.stringify({sessionTitleSync:saved})}}}
  return {}
 }
 const first=withSessionTitles(api,piEventTitle)
 await first('AppendEvent',{...key,Event:{Extensions:JSON.stringify({pi:{seq:0,entry:{type:'session_info',name:''}}})}})
 const count=updates;const second=withSessionTitles(api,piEventTitle)
 await second('DescribeSession',key);assert.equal(updates,count)
 await second('AppendEvent',{...key,Event:{Content:{Role:'user'},Extensions:JSON.stringify({pi:{seq:1,entry:{type:'message'}}})}})
 assert.equal(title,'');assert.equal(updates,count+1)
})

test('pending Title can be retried when content validation has already advanced the event cursor',async()=>{
 let fail=true;const writes=[]
 const request=withSessionTitles(async(a,p)=>{if(a==='ModifySession'){writes.push(p.Title);if(fail){fail=false;throw Error('outage')}}return {}},dshEventTitle)
 await assert.rejects(request('AppendEvent',{...key,Event:event(1,'待重试')}),/outage/)
 await request.flush(key);assert.deepEqual(writes,['待重试','待重试'])
 await request.flush(key);assert.equal(writes.length,2)
})


test('a newer cloud marker supersedes another instance pending title', async () => {
 let cloudTitle='';let marker;let fail=true;const writes=[]
 const api=async(a,p)=>{
  if(a==='AppendEvent'&&p.Event.Actions?.StateDelta)marker=JSON.parse(p.Event.Actions.StateDelta).sessionTitleSync
  if(a==='ModifySession'){if(fail){fail=false;throw Error('offline')}writes.push(p.Title);cloudTitle=p.Title}
  if(a==='DescribeSession')return {Session:{Title:cloudTitle,State:{CustomState:JSON.stringify({sessionTitleSync:marker})}}}
  return {}
 }
 const a=withSessionTitles(api,dshEventTitle),b=withSessionTitles(api,dshEventTitle)
 await assert.rejects(a('AppendEvent',{...key,Event:event(5,'T1')}),/offline/)
 await b('AppendEvent',{...key,Event:event(8,'T2')})
 await a('DescribeSession',key);await a.flush(key)
 await a('AppendEvent',{...key,Event:{Extensions:'{}'}})
 assert.equal(cloudTitle,'T2');assert.deepEqual(writes,['T2'])
})

test('malformed optional JSON cannot break reads or ordinary appends',async()=>{
 const calls=[]
 const request=withSessionTitles(async(a,p)=>{calls.push([a,p]);return {Session:{State:{CustomState:'invalid'}}}},dshEventTitle)
 await request('DescribeSession',key)
 await request('AppendEvent',{...key,Event:{Extensions:'invalid'}})
 for(const delta of ['invalid','42','"text"','[]']) {
  await assert.rejects(request('AppendEvent',{...key,Event:{...event(2,'title'),Actions:{StateDelta:delta}}}),/StateDelta must be a JSON object/)
 }
 assert.equal(calls.length,2)
 assert.equal(piEventTitle({Extensions:'invalid'}),undefined)
})


test('standalone title synchronization copies remain identical in the cookbook checkout', async () => {
 const {readFile,access}=await import('node:fs/promises')
 const {fileURLToPath}=await import('node:url')
 const {dirname,join}=await import('node:path')
 let root=dirname(fileURLToPath(import.meta.url))
 while(root!==dirname(root)){
  try{await access(join(root,'CONTRIBUTING.md'));break}catch{root=dirname(root)}
 }
 if(root===dirname(root))return // Installed standalone packages have no sibling examples.
 // Every directory ships its own copy so that it builds on its own. Keep them equal.
 const groups=[[
  'pi/extension/session-titles.js',
  'pi/reference/pi-1.4.0-stateless-handoff/extension/session-titles.js',
  'deepseek-harness/dsh-0.2.1-rc.2/plugin/session-titles.js',
  'deepseek-harness/reference/dsh-0.2.1-rc.2-stateless-handoff/plugin/session-titles.js'],[
  'deepseek-harness/dsh-0.2.1-rc.2/plugin/cloud-title-hints.js',
  'deepseek-harness/reference/dsh-0.2.1-rc.2-stateless-handoff/plugin/cloud-title-hints.js']]
 for(const paths of groups){
  const sources=await Promise.all(paths.map(p=>readFile(join(root,'examples/session-cookbook',p),'utf8')))
  for(const source of sources)assert.equal(source,sources[0],`copies differ: ${paths.join(', ')}`)
 }
})

test('a malformed title event is a permanent error and forget() releases session state',async()=>{
 const request=withSessionTitles(async()=>({}),dshEventTitle)
 await assert.rejects(request('AppendEvent',{...key,Event:{...event(1,'t'),Actions:{StateDelta:'[]'}}}),{code:'invalid-title-event',retryable:false})
 await request('AppendEvent',{...key,Event:event(1,'t')})
 request.forget(key)
 const writes=[];const again=withSessionTitles(async(a,p)=>{if(a==='ModifySession')writes.push(p.Title);return {}},dshEventTitle)
 await again.flush(key);assert.deepEqual(writes,[],'nothing pending after forget')
})
