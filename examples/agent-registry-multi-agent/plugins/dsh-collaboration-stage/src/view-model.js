/** Keep discovery breadth out of the collaboration topology.
 * Registry may return many candidates, but only agents with a real A2A Task
 * are participants. The aggregate Registry event remains visible.
 */
export function participationView(snapshot) {
  const invokedNodeIds = new Set(snapshot.invocations.map(invocation => invocation.node.id))
  return {
    agentNodes: snapshot.agentNodes.filter(node => invokedNodeIds.has(node.id)),
    events: snapshot.events.filter(event => event.action !== 'agent-discovered'
      || invokedNodeIds.has(event.nodeId)),
  }
}
