/** ECharts 轻量封装：按需注册 Pie/Bar 与常用组件，避免整包引入。 */
import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, PieChart } from 'echarts/charts'
import { GraphicComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'

echarts.use([PieChart, BarChart, TooltipComponent, LegendComponent, GridComponent, GraphicComponent, CanvasRenderer])

type ChartInstance = ReturnType<typeof echarts.init>

export function useChart(option: EChartsOption | null, deps: unknown[] = []) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<ChartInstance | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const chart = echarts.init(containerRef.current, undefined, { renderer: 'canvas' })
    chartRef.current = chart
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(containerRef.current)
    return () => {
      observer.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!chartRef.current || !option) return
    chartRef.current.setOption(option, true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps.length ? deps : [option])

  return containerRef
}
