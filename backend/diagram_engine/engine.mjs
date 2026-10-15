import ELK from 'elkjs/lib/elk.bundled.js'
import { JSDOM } from 'jsdom'
import style from '../../shared/flowchart-style.json' with { type: 'json' }

const input = JSON.parse(await new Promise((resolve, reject) => {
  let data = ''
  process.stdin.setEncoding('utf8')
  process.stdin.on('data', chunk => { data += chunk })
  process.stdin.on('end', () => resolve(data))
  process.stdin.on('error', reject)
}))

try {
  if (input.action === 'parse') {
    const dom = new JSDOM('')
    globalThis.window = dom.window
    globalThis.document = dom.window.document
    const { default: mermaid } = await import('mermaid')
    mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' })
    const diagram = await mermaid.mermaidAPI.getDiagramFromText(input.source)
    if (!diagram.type.startsWith('flowchart')) throw new Error('Only flowcharts are supported')
    const db = diagram.db
    const nodes = [...db.getVertices().values()].map(vertex => ({
      id: vertex.id,
      title: String(vertex.text || vertex.id).replace(/<br\s*\/?\s*>/gi, '\n').replace(/<[^>]*>/g, ''),
      desc: '',
      kind: ['diamond', 'question'].includes(vertex.type) ? 'decision' : 'process',
    }))
    const edges = []
    for (const edge of db.getEdges()) {
      const label = String(edge.text || '').replace(/<[^>]*>/g, '') || null
      const common = { source: edge.start, target: edge.end, label }
      edges.push(common)
      if (String(edge.type).startsWith('double_')) {
        edges.push({ ...common, source: edge.end, target: edge.start })
      }
    }
    process.stdout.write(JSON.stringify({ nodes, edges, direction: db.getDirection() }))
  } else if (input.action === 'layout') {
    const elk = new ELK()
    const graphs = await Promise.all((input.graphs || [input]).map(request => elk.layout({
      id: 'root',
      layoutOptions: {
        ...style.layout_options,
        'elk.direction': request.direction || 'DOWN',
        'elk.aspectRatio': String(request.aspectRatio || 2),
        'elk.layered.wrapping.strategy': request.wrap ? 'MULTI_EDGE' : 'OFF',
      },
      children: request.nodes,
      edges: request.edges.map((edge, index) => ({
        id: `edge-${index}`, sources: [edge.source], targets: [edge.target],
        labels: edge.label ? [{ text: edge.label, width: edge.label_width, height: edge.label_height,
          layoutOptions: { 'elk.edgeLabels.inline': 'true' } }] : [],
      })),
    })))
    process.stdout.write(JSON.stringify(input.graphs ? graphs : graphs[0]))
  } else {
    throw new Error('Unknown diagram action')
  }
} catch (error) {
  process.stderr.write(String(error.message || error))
  process.exitCode = 1
}
