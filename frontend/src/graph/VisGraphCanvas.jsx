import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import { DataSet, Network } from 'vis-network/standalone'
import 'vis-network/styles/vis-network.min.css'
import './vis-graph.css'
import {
  buildVisEdges,
  buildVisNodes,
  buildVisOptions,
  edgeKey,
  edgeRelation,
  graphSizeTier,
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
    showEdgeLabels = false,
    /** true — узлы продолжают «жить» после стабилизации; false — фиксированная раскладка */
    physicsEnabled = true,
    onReady,
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
  const physicsEnabledRef = useRef(physicsEnabled)

  useEffect(() => {
    physicsEnabledRef.current = physicsEnabled
  }, [physicsEnabled])

  const applyPhysicsMode = (network, { afterStabilize = false } = {}) => {
    if (physicsEnabledRef.current) {
      network.setOptions({
        physics: { enabled: true, stabilization: afterStabilize ? false : undefined },
      })
    } else {
      network.setOptions({ physics: { enabled: false, stabilization: false } })
    }
  }

  useImperativeHandle(ref, () => ({
    fit: () => networkRef.current?.fit({ animation: false }),
    zoomIn: () => {
      const net = networkRef.current
      if (!net) return
      net.moveTo({ scale: Math.min(net.getScale() * 1.25, 4), animation: false })
    },
    zoomOut: () => {
      const net = networkRef.current
      if (!net) return
      net.moveTo({ scale: Math.max(net.getScale() / 1.25, 0.08), animation: false })
    },
    stabilize: () => {
      const net = networkRef.current
      if (!net) return
      const n = nodesDsRef.current?.length ?? nodes.length
      const tier = graphSizeTier(n, edges.length)
      const iterations = tier === 'large' ? 35 : 70
      net.setOptions({ physics: { enabled: true, stabilization: { iterations } } })
      net.stabilize(iterations)
      if (!physicsEnabledRef.current) {
        net.once('stabilizationIterationsDone', () => applyPhysicsMode(net, { afterStabilize: true }))
      }
    },
    focusNode: (nodeId) => {
      const net = networkRef.current
      if (!net || !nodeId) return
      net.focus(nodeId, { scale: 1.15, animation: false })
    },
  }))

  useEffect(() => {
    const host = hostRef.current
    if (!host) return undefined

    if (networkRef.current) {
      networkRef.current.destroy()
      networkRef.current = null
    }

    if (!nodes.length) {
      nodesDsRef.current = null
      edgesDsRef.current = null
      return undefined
    }

    let cancelled = false
    const mount = () => {
      if (cancelled || !hostRef.current) return

      const degrees = buildDegrees(edges)
      const tier = graphSizeTier(nodes.length, edges.length)
      const visNodes = buildVisNodes(nodes, degrees, tier)
      const visEdges = buildVisEdges(edges, relationMeta, showEdgeLabels, tier)

      edgesMapRef.current = new Map(visEdges.map((e) => [e.id, e._raw]))

      const nodesDs = new DataSet(visNodes)
      const edgesDs = new DataSet(visEdges)
      nodesDsRef.current = nodesDs
      edgesDsRef.current = edgesDs

      const network = new Network(
        hostRef.current,
        { nodes: nodesDs, edges: edgesDs },
        buildVisOptions(tier, { physicsEnabled: physicsEnabledRef.current }),
      )
      networkRef.current = network

      network.on('click', (params) => {
        if (params.edges.length > 0) {
          onEdgeSelect?.(edgesMapRef.current.get(params.edges[0]) || null)
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
        onEdgeHover?.(edgesMapRef.current.get(params.edge) || null)
      })
      network.on('blurEdge', () => onEdgeHover?.(null))

      network.on('dragEnd', () => {
        if (physicsEnabledRef.current) {
          network.setOptions({ physics: { enabled: true, stabilization: false } })
        }
      })

      network.once('stabilizationIterationsDone', () => {
        network.fit({ animation: false })
        applyPhysicsMode(network, { afterStabilize: true })
        onReady?.()
      })
    }

    const ric = typeof requestIdleCallback === 'function'
      ? requestIdleCallback(mount, { timeout: 400 })
      : setTimeout(mount, 0)

    return () => {
      cancelled = true
      if (typeof cancelIdleCallback === 'function') cancelIdleCallback(ric)
      else clearTimeout(ric)
      networkRef.current?.destroy()
      networkRef.current = null
    }
  }, [nodes, edges, relationMeta, showEdgeLabels, physicsEnabled]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const nodesDs = nodesDsRef.current
    const edgesDs = edgesDsRef.current
    const net = networkRef.current
    if (!net || !nodesDs || !edgesDs) return

    const connected = new Set()
    if (selectedNodeId) {
      edges.forEach((e) => {
        if (e.source === selectedNodeId) connected.add(e.target)
        if (e.target === selectedNodeId) connected.add(e.source)
      })
    }
    if (selectedEdgeId) {
      const edge = edges.find((e, idx) => edgeKey(e, idx) === selectedEdgeId || e.visId === selectedEdgeId)
      if (edge) {
        connected.add(edge.source)
        connected.add(edge.target)
      }
    }

    const hasFocus = selectedNodeId || selectedEdgeId
    const tier = graphSizeTier(nodes.length, edges.length)
    const degrees = buildDegrees(edges)
    const labelMinDegree = tier === 'large' ? 4 : tier === 'medium' ? 2 : 0

    nodesDs.update(nodes.map((n) => {
      const deg = degrees[n.id] || 1
      const showLabel = n.id === selectedNodeId || connected.has(n.id) || deg >= labelMinDegree || tier === 'small'
      return {
        id: n.id,
        opacity: hasFocus && n.id !== selectedNodeId && !connected.has(n.id) ? 0.12 : 1,
        borderWidth: n.id === selectedNodeId ? 4 : 2,
        label: showLabel ? truncateLabel(n.name || n.id, 22) : '',
        font: { size: showLabel ? 11 : 0 },
      }
    }))

    edgesDs.update(edges.map((e, i) => {
      const id = e.visId || edgeKey(e, i)
      const isSel = id === selectedEdgeId
      const isConn = selectedNodeId && (e.source === selectedNodeId || e.target === selectedNodeId)
      const showLabel = showEdgeLabels || isSel || isConn
      return {
        id,
        width: isSel ? 2.5 : isConn ? 1.8 : 1,
        color: { opacity: hasFocus && !isSel && !isConn ? 0.12 : 0.85 },
        label: showLabel ? truncateLabel(relationLabel(e, relationMeta), 22) : '',
      }
    }))

    if (selectedNodeId) net.selectNodes([selectedNodeId])
    else net.unselectAll()
    if (selectedEdgeId) net.selectEdges([selectedEdgeId])
  }, [selectedNodeId, selectedEdgeId, nodes, edges, showEdgeLabels, relationMeta])

  return <div ref={hostRef} className="vis-graph-host" />
})

export default VisGraphCanvas
