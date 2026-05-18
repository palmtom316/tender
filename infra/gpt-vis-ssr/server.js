const express = require('express');
require.extensions['.css'] = function ignoreCss(module) {
  module._compile('', module.filename);
};
const { render } = require('@antv/gpt-vis-ssr');

const app = express();
const PORT = process.env.PORT || 7102;
const MAX_CONCURRENT = parseInt(process.env.MAX_CONCURRENT || '4', 10);
const RENDER_TIMEOUT_MS = parseInt(process.env.RENDER_TIMEOUT_MS || '20000', 10);
const SUPPORTED_TYPES = new Set([
  'flow-diagram',
  'network-graph',
  'organization-chart',
  'mindmap',
  'fishbone-diagram',
  'table',
  'summary',
]);

app.use(express.json({ limit: '2mb' }));

let activeRequests = 0;

function acquireSemaphore() {
  return new Promise((resolve) => {
    const tryAcquire = () => {
      if (activeRequests < MAX_CONCURRENT) {
        activeRequests++;
        resolve();
      } else {
        setTimeout(tryAcquire, 50);
      }
    };
    tryAcquire();
  });
}

function releaseSemaphore() {
  activeRequests = Math.max(activeRequests - 1, 0);
}

app.get('/health', (_req, res) => {
  res.json({
    status: 'ok',
    activeRequests,
    maxConcurrent: MAX_CONCURRENT,
    renderTimeoutMs: RENDER_TIMEOUT_MS,
    supportedTypes: Array.from(SUPPORTED_TYPES).sort(),
  });
});

app.post('/render', async (req, res) => {
  await acquireSemaphore();
  let vis = null;
  try {
    const { type, data, theme, width, height } = req.body;
    if (typeof type !== 'string' || !type.trim() || data == null) {
      return res.status(400).json({ success: false, svg: '', errorMessage: 'Missing type or data' });
    }
    if (!SUPPORTED_TYPES.has(type)) {
      return res.status(400).json({ success: false, svg: '', errorMessage: `Unsupported chart type: ${type}` });
    }
    const renderWidth = Number(width) > 0 ? Number(width) : 600;
    const renderHeight = Number(height) > 0 ? Number(height) : 400;
    vis = await withTimeout(
      render({
        type,
        data: normalizeData(type, data),
        theme: theme || 'default',
        width: renderWidth,
        height: renderHeight,
      }),
      RENDER_TIMEOUT_MS,
      `Render timed out after ${RENDER_TIMEOUT_MS}ms`
    );
    const png = vis.toBuffer();
    const svg = wrapPngAsSvg(png, renderWidth, renderHeight, collectText(data));
    res.json({ success: true, svg, errorMessage: '' });
  } catch (err) {
    res.json({ success: false, svg: '', errorMessage: err.message || String(err) });
  } finally {
    if (vis) vis.destroy();
    releaseSemaphore();
  }
});

function withTimeout(promise, timeoutMs, message) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error(message)), timeoutMs)),
  ]);
}

function normalizeData(type, data) {
  if ((type === 'flow-diagram' || type === 'network-graph') && data && Array.isArray(data.nodes)) {
    return {
      ...data,
      nodes: data.nodes.map((node) => ({
        ...node,
        name: node.name || node.id,
        label: node.label || node.name || node.id,
      })),
      edges: Array.isArray(data.edges)
        ? data.edges.map((edge) => ({
            ...edge,
            name: edge.name || edge.label || '',
          }))
        : [],
    };
  }
  if (type === 'organization-chart' && data && !data.name && Array.isArray(data.nodes)) {
    const nodeById = new Map(data.nodes.map((node) => [node.id || node.name, { ...node, name: node.name || node.label || node.id }]));
    const childIds = new Set();
    for (const edge of data.edges || []) {
      const source = nodeById.get(edge.source || edge.from);
      const target = nodeById.get(edge.target || edge.to);
      if (source && target) {
        source.children = source.children || [];
        source.children.push(target);
        childIds.add(target.id || target.name);
      }
    }
    return [...nodeById.values()].find((node) => !childIds.has(node.id || node.name)) || [...nodeById.values()][0] || data;
  }
  return data;
}

function wrapPngAsSvg(pngBuffer, width, height, textValues) {
  const encodedText = escapeXml(textValues.filter(Boolean).join(' '));
  const pngBase64 = pngBuffer.toString('base64');
  return [
    `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`,
    `<title>${encodedText || 'gpt-vis chart'}</title>`,
    `<desc>${encodedText}</desc>`,
    `<image width="${width}" height="${height}" href="data:image/png;base64,${pngBase64}"/>`,
    '</svg>',
  ].join('');
}

function collectText(value) {
  const output = [];
  const visit = (item) => {
    if (!item || typeof item !== 'object') return;
    for (const key of ['title', 'label', 'name', 'description']) {
      if (typeof item[key] === 'string') output.push(item[key]);
    }
    if (Array.isArray(item.nodes)) item.nodes.forEach(visit);
    if (Array.isArray(item.edges)) item.edges.forEach(visit);
    if (Array.isArray(item.children)) item.children.forEach(visit);
  };
  visit(value);
  return output;
}

function escapeXml(value) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

app.listen(PORT, '0.0.0.0', () => {
  console.log(`gpt-vis-ssr wrapper listening on port ${PORT}`);
});
