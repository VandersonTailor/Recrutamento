export function avatarDataUri(name) {
  const safe = (name ?? '').trim() || 'Candidato'
  const initials = safe
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join('')

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#2f9b75"/>
      <stop offset="1" stop-color="#183f32"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="18" fill="url(#g)"/>
  <text x="32" y="38" font-family="Plus Jakarta Sans, Arial" font-size="22" text-anchor="middle" fill="#eef9f5" font-weight="700">${escapeXml(
    initials
  )}</text>
</svg>`
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
}

function escapeXml(s) {
  return String(s).replace(/[<>&"]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]))
}

