import assert from 'node:assert/strict'
import test from 'node:test'
import { createWorkspacePanels, createCommitNotifier } from '../src/course-graph/workspace-panels.ts'

test('unsaved_review_blocks_close_until_user_choice', async () => {
  let allow=false, guards=0
  const p=createWorkspacePanels(async()=>{guards++;return allow})
  await p.open('manager'); assert.equal(await p.close('manager'),false)
  assert.equal(p.state.active,'manager'); allow=true
  assert.equal(await p.close('manager'),true); assert.equal(guards,2)
})
test('successful_commit_emits_once_failed_refresh_does_not_reconfirm', async()=>{
  let reads=0
  const notify=createCommitNotifier(()=>{reads++;throw new Error('offline')})
  await assert.rejects(notify('c','receipt'),/offline/)
  await notify('c','receipt'); assert.equal(reads,1)
  await assert.rejects(notify('other','receipt'),/offline/); assert.equal(reads,2)
})
test('closing_manager_does_not_cancel_or_restart_saved_work', async()=>{
  const p=createWorkspacePanels(async()=>true)
  await p.open('manager'); const epoch=p.state.managerEpoch
  await p.close('manager'); await p.open('manager')
  assert.equal(p.state.managerMounted,true); assert.equal(p.state.managerEpoch,epoch)
})
test('restoring_backup_invalidates_preview_and_read_bundle', async()=>{
  const p=createWorkspacePanels(async()=>false)
  await p.open('manager'); p.invalidate()
  assert.equal(p.state.managerMounted,false); assert.equal(p.state.managerEpoch,1)
  assert.equal(p.state.active,'none')
})
test('one_modal_at_a_time_restores_focus', async()=>{
  const focused=[]; const p=createWorkspacePanels(async()=>true, id=>focused.push(id))
  await p.open('directory','directory-trigger'); await p.open('source','citation-trigger')
  assert.equal(p.state.active,'source'); await p.close('source')
  assert.deepEqual(focused,['citation-trigger']); assert.equal(p.state.active,'none')
})
test('late_close_does_not_close_a_new_modal',async()=>{
  let resolve; const gate=new Promise(r=>resolve=r)
  const p=createWorkspacePanels(()=>gate); await p.open('manager')
  const close=p.close('manager'); p.invalidate(); await p.open('source')
  resolve(true); await close; assert.equal(p.state.active,'source')
})

test('panel_tab_cycle_wraps_in_both_directions', async()=>{
  const { nextPanelFocus }=await import('../src/course-graph/workspace-panels.ts')
  assert.equal(nextPanelFocus(2,3,false),0); assert.equal(nextPanelFocus(0,3,true),2)
  assert.equal(nextPanelFocus(-1,3,false),0); assert.equal(nextPanelFocus(1,3,false),2)
})
