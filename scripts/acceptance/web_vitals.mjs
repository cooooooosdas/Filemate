// Run against the currently open page with playwright-cli run-code --filename.
async (page) => {
  const target = page.url()
  if (!/^https?:\/\//.test(target)) throw new Error('Open the target website first.')
  const failures = []
  const consoleErrors = []
  page.on('requestfailed', request => failures.push({ url: request.url(), error: request.failure()?.errorText }))
  page.on('pageerror', error => consoleErrors.push(error.message))
  await page.addInitScript(() => {
    if (window.__filemateVitalsInstalled) return
    window.__filemateVitalsInstalled = true
    window.__filemateVitals = { cls: 0, lcp: 0, shifts: [] }
    new PerformanceObserver(list => {
      for (const entry of list.getEntries()) {
        if (entry.hadRecentInput) continue
        window.__filemateVitals.cls += entry.value
        window.__filemateVitals.shifts.push({
          value: entry.value,
          sources: (entry.sources || []).map(source => source.node?.className || source.node?.nodeName || 'removed'),
        })
      }
    }).observe({ type: 'layout-shift', buffered: true })
    new PerformanceObserver(list => {
      for (const entry of list.getEntries()) window.__filemateVitals.lcp = entry.startTime
    }).observe({ type: 'largest-contentful-paint', buffered: true })
  })
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Network.enable')
  await cdp.send('Network.setCacheDisabled', { cacheDisabled: true })
  const samples = []
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    for (let round = 0; round < 3; round++) {
      await page.setViewportSize(viewport)
      await cdp.send('Network.clearBrowserCache')
      await page.goto(target, { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(5000)
      const metrics = await page.evaluate(() => {
        const navigation = performance.getEntriesByType('navigation')[0]
        const resources = performance.getEntriesByType('resource')
        return {
          ...window.__filemateVitals,
          fcp_ms: performance.getEntriesByName('first-contentful-paint')[0]?.startTime,
          transfer_bytes: navigation.transferSize + resources.reduce((sum, row) => sum + row.transferSize, 0),
          image_bytes: resources.filter(row => row.initiatorType === 'img').reduce((sum, row) => sum + row.transferSize, 0),
          horizontal_overflow: document.documentElement.scrollWidth > innerWidth,
        }
      })
      samples.push({ viewport, round: round + 1, ...metrics })
    }
  }
  const p75 = values => [...values].sort((a, b) => a - b)[Math.ceil(values.length * 0.75) - 1]
  const report = {
    target,
    browser: await page.evaluate(() => navigator.userAgent),
    measurement: 'Six cold-cache laboratory navigations, 5-second observation. This is not field P75.',
    samples,
    laboratory_p75: {
      cls: p75(samples.map(row => row.cls)),
      lcp_ms: p75(samples.map(row => row.lcp)),
    },
    failures,
    console_errors: consoleErrors,
    passed: samples.every(row => row.cls < 0.05 && !row.horizontal_overflow) && consoleErrors.length === 0,
  }
  if (!report.passed) throw new Error(JSON.stringify(report))
  return report
}
