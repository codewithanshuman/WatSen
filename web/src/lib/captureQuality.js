async function loadBitmap(file) {
  if ('createImageBitmap' in window) return createImageBitmap(file)
  const url = URL.createObjectURL(file)
  try {
    const image = new Image()
    image.src = url
    await image.decode()
    return image
  } finally {
    URL.revokeObjectURL(url)
  }
}

export async function assessCaptureQuality(file) {
  const image = await loadBitmap(file)
  const width = image.width, height = image.height
  const scale = Math.min(1, 320 / Math.max(width, height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(width * scale))
  canvas.height = Math.max(1, Math.round(height * scale))
  const context = canvas.getContext('2d', { willReadFrequently: true })
  context.drawImage(image, 0, 0, canvas.width, canvas.height)
  image.close?.()
  const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data
  const luminance = new Float32Array(canvas.width * canvas.height)
  let sum = 0
  for (let index = 0, pixel = 0; index < pixels.length; index += 4, pixel += 1) {
    const value = .2126 * pixels[index] + .7152 * pixels[index + 1] + .0722 * pixels[index + 2]
    luminance[pixel] = value
    sum += value
  }
  const mean = sum / luminance.length
  let variance = 0, edge = 0, edgeCount = 0
  for (let y = 0; y < canvas.height; y += 1) {
    for (let x = 0; x < canvas.width; x += 1) {
      const index = y * canvas.width + x
      variance += (luminance[index] - mean) ** 2
      if (x && y) {
        edge += Math.abs(luminance[index] - luminance[index - 1])
          + Math.abs(luminance[index] - luminance[index - canvas.width])
        edgeCount += 2
      }
    }
  }
  const contrast = Math.sqrt(variance / luminance.length)
  const sharpness = edge / Math.max(1, edgeCount)
  const checks = [
    { key: 'resolution', label: 'Enough detail', pass: width >= 900 && height >= 700, value: `${width} × ${height}`, guidance: 'Move closer or use the full-resolution camera.' },
    { key: 'exposure', label: 'Balanced light', pass: mean >= 48 && mean <= 215, value: `${Math.round(mean)}/255`, guidance: mean < 48 ? 'Add indirect light; avoid flash glare.' : 'Reduce glare or move out of direct sun.' },
    { key: 'contrast', label: 'Specimen separation', pass: contrast >= 28, value: contrast.toFixed(0), guidance: 'Place the specimen against a plain light tray.' },
    { key: 'sharpness', label: 'Focus and stability', pass: sharpness >= 6.5, value: sharpness.toFixed(1), guidance: 'Hold steady, tap to focus and retake closer.' },
  ]
  const passed = checks.filter(check => check.pass).length
  const score = Math.round((passed / checks.length) * 100)
  return {
    score, label: passed === checks.length ? 'field-ready' : passed >= 3 ? 'usable' : 'retake recommended',
    checks, width, height,
    boundary: 'On-device capture guidance only; server-side quality and taxon review remain authoritative.',
  }
}
