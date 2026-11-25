/** 日/月趋势柱状图：数据源为 GET /api/stats?group_by=day|month。 */
import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import type { StatsGroupBy, StatsItem } from '../../types/contract'
import { formatMoney, shortBucketLabel } from '../../lib/format'
import { useChart } from '../../hooks/useChart'

export function TrendChart({
  items,
  groupBy,
}: {
  items: StatsItem[]
  groupBy: Extract<StatsGroupBy, 'day' | 'month'>
}) {
  const option = useMemo<EChartsOption>(() => {
    return {
      grid: { left: 8, right: 12, top: 24, bottom: 8, containLabel: true },
      tooltip: {
        trigger: 'axis',
        borderColor: '#e5ded3',
        backgroundColor: '#fffdfa',
        textStyle: { color: '#171a1c', fontSize: 12 },
        axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(47,143,121,0.06)' } },
        formatter: (params: unknown) => {
          const list = params as { axisValue: string; data: number }[]
          if (!list.length) return ''
          return `${list[0].axisValue}<br/><b>${formatMoney(list[0].data)}</b> 元`
        },
      },
      xAxis: {
        type: 'category',
        data: items.map((item) => shortBucketLabel(item.key, groupBy)),
        axisLine: { lineStyle: { color: '#e5ded3' } },
        axisTick: { show: false },
        axisLabel: { color: 'rgba(23,26,28,0.45)', fontSize: 11 },
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: 'rgba(23,26,28,0.06)' } },
        axisLabel: { color: 'rgba(23,26,28,0.4)', fontSize: 11 },
      },
      series: [
        {
          type: 'bar',
          data: items.map((item) => Number(item.amount.toFixed(2))),
          barMaxWidth: 26,
          itemStyle: {
            borderRadius: [6, 6, 0, 0],
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: '#2f8f79' },
                { offset: 1, color: 'rgba(47,143,121,0.25)' },
              ],
            },
          },
        },
      ],
    }
  }, [items, groupBy])

  const ref = useChart(option, [option])

  if (items.length === 0) {
    return <p className="py-10 text-center text-xs text-ink/35">该范围内没有支出数据</p>
  }
  return <div ref={ref} className="h-64 w-full" />
}
