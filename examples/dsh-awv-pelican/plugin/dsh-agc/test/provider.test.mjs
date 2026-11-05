import assert from 'node:assert/strict'
import test from 'node:test'
import { agentJob } from '../src/job-builder.ts'
import { codeResult, reviewResult } from '../src/subagent-provider.ts'

const config = {
  namespace: 'dsh-awv',
  workspaceClaim: 'workspace',
  workerImage: 'worker@sha256:test',
  siteImage: 'site@sha256:test',
  modelSecret: 'model',
  serviceType: 'LoadBalancer',
}

test('agent Job directly starts dsh without business scripts', () => {
  const job = agentJob('review-agent-test', 'review', config)
  const pod = job.spec.template.spec
  const container = pod.containers[0]

  assert.deepEqual(container.command, ['/usr/bin/tini', '--', 'dsh'])
  assert.equal(container.args.at(-1), '$(DSH_TASK)')
  assert.equal(container.env.find((item) => item.name === 'HOME')?.value, '/tmp/dsh')
  assert.equal(JSON.stringify(container).includes('/bin/sh'), false)
  assert.equal(JSON.stringify(container).includes('/opt/pelican/checks'), false)
  assert.deepEqual(container.volumeMounts[0], {
    name: 'workspace',
    mountPath: '/workspace/site',
    readOnly: true,
  })
})

test('Code result requires a valid result marker', () => {
  assert.deepEqual(
    codeResult('2026-09-22T00:00:00Z DSH_CODE_RESULT={"status":"OK","summary":"done"}'),
    { status: 'OK', summary: 'done' },
  )
  assert.throws(() => codeResult('completed without marker'))
})

test('Review result keeps blocking issues and evidence', () => {
  assert.deepEqual(
    reviewResult('DSH_REVIEW_RESULT={"status":"FAIL","summary":"overflow","blocking_issues":["mobile overflow"],"evidence":["mobile.png"]}'),
    {
      status: 'FAIL',
      summary: 'overflow',
      blocking_issues: ['mobile overflow'],
      evidence: ['mobile.png'],
    },
  )
  assert.throws(() => reviewResult('DSH_REVIEW_RESULT={"status":"PASS","summary":"bad","blocking_issues":["still broken"],"evidence":[]}'))
})
