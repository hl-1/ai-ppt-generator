import type { DiagramBlock, DiagramEdge, DiagramNode } from './types'

const COMPLEX_FLOW_KEYWORDS = [
  '故障', '预警', '分流', '分类', '分支', '并行', '汇聚', '判断', '条件', '决策',
  '审批', '应急', '处置', '排查', '恢复', '复盘', '上报', '异常', '失败', '成功',
  '通过', '驳回', '回退', '派单', '流转',
]
const SIMPLE_STEP_KEYWORDS = [
  '步骤', '路径', '推进', '路线', '阶段', '第一步', '第二步', '第三步', '第四步',
  '第五步', '前两步', '最后', '先', '再', '然后',
]
const STEP_PREFIX = /^(?:第一步|第二步|第三步|第四步|第五步|第六步|第七步|第八步|第九步|前两步|最后一步|步骤[一二三四五])\s*[:：\-—]?\s*/

export function normalizeFlowEdges(
  diagramType: DiagramBlock['diagram_type'],
  nodes: DiagramNode[],
  edges: DiagramEdge[],
): DiagramEdge[] {
  if (diagramType !== 'flow' || nodes.length < 4) return [...edges]
  const valid = edges.filter(
    (edge) =>
      nodes.some((node) => node.id === edge.source) &&
      nodes.some((node) => node.id === edge.target) &&
      edge.source !== edge.target,
  )
  if (hasBranchingEdges(nodes, valid)) return valid
  if (!shouldKeepFlowDiagram(nodes, valid)) return valid

  const branchIndex = nodes.length >= 6 ? 1 : 0
  const mergeIndex = nodes.length >= 6 ? nodes.length - 3 : nodes.length - 1
  if (mergeIndex <= branchIndex + 1) return [...edges]

  const result: DiagramEdge[] = []
  if (branchIndex > 0) {
    result.push({ source: nodes[0]!.id, target: nodes[branchIndex]!.id, label: null })
  }
  for (const node of nodes.slice(branchIndex + 1, mergeIndex)) {
    result.push({ source: nodes[branchIndex]!.id, target: node.id, label: null })
    result.push({ source: node.id, target: nodes[mergeIndex]!.id, label: null })
  }
  for (let index = mergeIndex; index < nodes.length - 1; index++) {
    result.push({ source: nodes[index]!.id, target: nodes[index + 1]!.id, label: null })
  }
  return result
}

export function hasBranchingEdges(nodes: DiagramNode[], edges: DiagramEdge[]): boolean {
  const outgoing = new Map<string, number>()
  const incoming = new Map<string, number>()
  for (const node of nodes) {
    outgoing.set(node.id, 0)
    incoming.set(node.id, 0)
  }
  for (const edge of edges) {
    outgoing.set(edge.source, (outgoing.get(edge.source) ?? 0) + 1)
    incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1)
  }
  return [...outgoing.values()].some((count) => count > 1)
    || [...incoming.values()].some((count) => count > 1)
}

export function shouldRenderFlowAsCards(
  diagramType: DiagramBlock['diagram_type'],
  nodes: DiagramNode[],
  edges: DiagramEdge[],
): boolean {
  return diagramType === 'flow' && !shouldKeepFlowDiagram(nodes, edges)
}

export function flowCardItems(nodes: DiagramNode[]) {
  return nodes.slice(0, 6).map((node) => {
    const originalTitle = node.title.trim()
    let title = originalTitle.replace(STEP_PREFIX, '').trim()
    const colon = title.indexOf('：') >= 0 ? title.indexOf('：') : title.indexOf(':')
    if (colon > 0 && colon <= 5) title = title.slice(colon + 1).trim()
    title = title.split(/[。；;，,]/, 1)[0] || originalTitle
    const desc = (node.desc.trim() || (title !== originalTitle ? originalTitle : '')).trim()
    return {
      title: compact(title, 18),
      desc: compact(desc, 56),
      icon: null,
    }
  })
}

function shouldKeepFlowDiagram(nodes: DiagramNode[], edges: DiagramEdge[]): boolean {
  if (nodes.length < 3) return false
  const blob = [
    ...nodes.map((node) => `${node.title} ${node.desc}`),
    ...edges.map((edge) => edge.label ?? ''),
  ].join(' ')
  const hasSimpleTerms = SIMPLE_STEP_KEYWORDS.some((keyword) => blob.includes(keyword))
  const stepTitles = nodes.filter((node) => /^(?:第|步骤[一二三四五六七八九])/.test(node.title.trim()))
  if (hasBranchingEdges(nodes, edges)) {
    return !hasSimpleTerms && stepTitles.length < Math.max(2, Math.floor(nodes.length / 2))
  }
  if (hasSimpleTerms || stepTitles.length >= Math.max(2, Math.floor(nodes.length / 2))) return false
  if (nodes.length < 4) return false
  return COMPLEX_FLOW_KEYWORDS.some((keyword) => blob.includes(keyword))
}

function compact(value: string, limit: number): string {
  const text = value.replace(/\s+/g, ' ').trim()
  return text.length <= limit ? text : `${text.slice(0, limit - 1).trimEnd()}…`
}

export function flowLevels(
  nodes: DiagramNode[],
  edges: DiagramEdge[],
): Map<string, number> {
  const incoming = new Map<string, number>(nodes.map((node) => [node.id, 0]))
  const outgoing = new Map<string, string[]>(nodes.map((node) => [node.id, []]))
  for (const edge of edges) {
    if (!incoming.has(edge.target) || !outgoing.has(edge.source)) continue
    incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1)
    outgoing.get(edge.source)!.push(edge.target)
  }

  const levels = new Map<string, number>()
  const queue: string[] = []
  for (const node of nodes) {
    if (incoming.get(node.id) === 0) {
      levels.set(node.id, 0)
      queue.push(node.id)
    }
  }
  while (queue.length > 0) {
    const current = queue.shift()!
    for (const target of outgoing.get(current) ?? []) {
      levels.set(target, Math.max(levels.get(target) ?? 0, (levels.get(current) ?? 0) + 1))
      incoming.set(target, (incoming.get(target) ?? 0) - 1)
      if (incoming.get(target) === 0) queue.push(target)
    }
  }
  return levels
}
