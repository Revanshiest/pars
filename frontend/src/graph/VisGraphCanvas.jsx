import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import { DataSet, Network } from 'vis-network/standalone'
import 'vis-network/styles/vis-network.min.css'
import './vis-graph.css'
import {
  buildVisEdges,
  buildVisNodes,
  buildVisOptions,
  edgeKey,
  relationLabel,
  truncateLabel,
} from './constants'

function buildDegrees(edges) {
  const d = {}
  edges.forEach((e) => {
    d[e.source] = (d[e.source] || 0) + 1
    d[e.target] = (d[e.target] || 0) + 1
  })
  return d
}

const VisGraphCanvas = forwardRef(function VisGraphCanvas(
  {
    nodes = [],
    edges = [],
    relationMeta = {},
    selectedNodeId = null,
    selectedEdgeId = null,
    showEdgeLabels = true,
    onNodeSelect,
    onEdgeSelect,
    onNodeHover,
    onEdgeHover,
    onBackgroundClick,
  },
  ref,
) {
  const hostRef = useRef(null)
  const networkRef = useRef(null)
  const nodesDsRef = useRef(null)
  const edgesDsRef = useRef(null)
  const edgesMapRef = useRef(new Map())

  useImperativeHandle(ref, () => ({
    fit: () => networkRef.current?.fit({ animation: { duration: 450, easingFunction: 'easeInOutQuad' } }),
    zoomIn: () => {
      const net = networkRef.current
      if (!net) return
      const scale = net.getScale()
      net.moveTo({ scale: Math.min(scale * 1.25, 4), animation: { duration: 200 } })
    },
    zoomOut: () => {
      const net = networkRef.current
      if (!net) return
      const scale = net.getScale()
      net.moveTo({ scale: Math.max(scale / 1.25, 0.08), animation: { duration: 200 } })
    },
    stabilize: () => {
      const net = networkRef.current
      if (!net) return
      net.setOptions({ physics: { enabled: true } })
      net.stabilize(80)
    },
    focusNode: (nodeId) => {
      const net = networkRef.current
      if (!net || !nodeId) return
      net.focus(nodeId, {
        scale: 1.2,
        animation: { duration: 500, easingFunction: 'easeInOutQuad' },
      })
    },
  }))

  // Полная пересборка при смене данных
  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    if (networkRef.current) {
      networkRef.current.destroy()
      networkRef.current = null
    }

    if (!nodes.length) {
      nodesDsRef.current = null
      edgesDsRef.current = null
      return
    }

    const degrees = buildDegrees(edges)
    const visNodes = buildVisNodes(nodes, degrees)
    const visEdges = buildVisEdges(edges, relationMeta, showEdgeLabels)

    edgesMapRef.current = new Map(visEdges.map((e) => [e.id, e._raw]))

    const nodesDs = new DataSet(visNodes)
    const edgesDs = new DataSet(visEdges)
    nodesDsRef.current = nodesDs
    edgesDsRef.current = edgesDs

    const network = new Network(host, { nodes: nodesDs, edges: edgesDs }, buildVisOptions(showEdgeLabels))
    networkRef.current = network

    network.on('click', (params) => {
      if (params.edges.length > 0) {
        const raw = edgesMapRef.current.get(params.edges[0])
        onEdgeSelect?.(raw || null)
        return
      }
      if (params.nodes.length > 0) {
        onNodeSelect?.(params.nodes[0])
        return
      }
      onBackgroundClick?.()
      onNodeSelect?.(null)
      onEdgeSelect?.(null)
    })

    network.on('hoverNode', (params) => onNodeHover?.(params.node))
    network.on('blurNode', () => onNodeHover?.(null))
    network.on('hoverEdge', (params) => {
      const raw = edgesMapRef.current.get(params.edge)
      onEdgeHover?.(raw || null)
    })
    network.on('blurEdge', () => onEdgeHover?.(null))

    network.once('stabilizationIterationsDone', () => {
      network.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } })
      network.setOptions({ physics: { enabled: true, stabilization: false } })
    })

    return () => {
      network.destroy()
      networkRef.current = null
    }
  }, [nodes, edges, relationMeta, showEdgeLabels]) // eslint-disable-line react-hooks/exhaustive-deps

  // Подсветка выбранного узла / связи без пересборки
  useEffect(() => {
    const net = networkRef.current
    const nodesDs = nodesDsRef.current
    const edgesDs = edgesDsRef.current
    if (!net || !nodesDs || !edgesDs) return

    const connected = new Set()
    if (selectedNodeId) {
      edges.forEach((e) => {
        if (e.source === selectedNodeId) connected.add(e.target)
        if (e.target === selectedNodeId) connected.add(e.source)
      })
    }
    if (selectedEdgeId) {
      const edge = edges.find((e) => edgeKey(e) === selectedEdgeId)
      if (edge) {
        connected.add(edge.source)
        connected.add(edge.target)
      }
    }

    const hasFocus = selectedNodeId || selectedEdgeId

    const nodeUpdates = nodes.map((n) => ({
      id: n.id,
      opacity: hasFocus && n.id !== selectedNodeId && !connected.has(n.id) ? 0.15 : 1,
      borderWidth: n.id === selectedNodeId ? 4 : 2,
    }))
    nodesDs.update(nodeUpdates)

    const edgeUpdates = edges.map((e) => {
      const id = edgeKey(e)
      const isSel = id === selectedEdgeId
      const isConn = selectedNodeId && (e.source === selectedNodeId || e.target === selectedNodeId)
      const showLabel = showEdgeLabels || isSel || isConn
      return {
        id,
        width: isSel ? 3 : isConn ? 2.2 : 1.5,
        color: {
          opacity: hasFocus && !isSel && !isConn ? 0.15 : 0.9,
        },
        label: showLabel ? truncateLabel(relationLabel(e, relationMeta), 22) : '',
      }
    })
    edgesDs.update(edgeUpdates)

    if (selectedNodeId) {
      net.selectNodes([selectedNodeId])
    } else {
      net.unselectAll()
    }
    if (selectedEdgeId) {
      net.selectEdges([selectedEdgeId])
    }
  }, [selectedNodeId, selectedEdgeId, nodes, edges, showEdgeLabels, relationMeta])

  // Обновить подписи рёбер при переключении чекбокса
  useEffect(() => {
    const edgesDs = edgesDsRef.current
    if (!edgesDs) return
    edgesDs.update(
      edges.map((e) => ({
        id: edgeKey(e),
        label: showEdgeLabels ? truncateLabel(relationLabel(e, relationMeta), 22) : '',
      })),
    )
  }, [showEdgeLabels, edges, relationMeta])

  return <div ref={hostRef} className="vis-graph-host" />
})

export default VisGraphCanvas
