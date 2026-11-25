/** 类别占比环形图：数据源为 GET /api/stats?group_by=category 的 items。 */
import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import type { StatsItem } from '../../types/contract'
import { categoryColor } from '../../lib/categories'
import { formatMoney } from '../../lib/format'
import { useChart } from '../../hooks/useChart'

export function CategoryPie({ items, total }: { items: StatsItem[]; total: number }) {
  const option = useMemo<EChartsOption | null>(() => {
    if (items.length === 0) return null
    return {
      tooltip: {
        trigger: 'item',
        borderColor: '#e5ded3',
        backgroundColor: '#fffdfa',
        textStyle: { color: '#171a1c', fontSize: 12 },
        formatter: (params: unknown) => {
          const p = params as { name: string; value: number; percent: number }
          return `${p.name}<br/><b>${formatMoney(p.value)}</b> 元 · ${p.percent}%`
        },
      },
      legend: {
        bottom: 0,
        icon: 'circle',
        itemWidth: 8,
        itemHeight: 8,
        textStyle: { color: 'rgba(23,26,28,0.6)', fontSize: 11 },
      },
      series: [
        {
          type: 'pie',
          radius: ['52%', '74%'],
          center: ['50%', '44%'],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: '#fffdfa', borderWidth: 2 },
          label: {
            show: true,
            formatter: (params: unknown) => {
              const p = params as { name: string; percent: number }
              return p.percent >= 8 ? `${p.name} ${p.percent}%` : ''
            },
            fontSize: 11,
            color: 'rgba(23,26,28,0.65)',
          },
          emphasis: {
            label: { show: true, fontWeight: 'bold', fontSize: 12 },
            scaleSize: 6,
          },
          data: items.map((item, index) => ({
            name: item.key,
            value: Number(item.amount.toFixed(2)),
            itemStyle: { color: categoryColor(item.key, index) },
          })),
        },
      ],
      graphic: [
        {
          type: 'text',
          left: 'center',
          top: '38%',
          style: {
            text: formatMoney(total),
            fontSize: 18,
            fontWeight: 600,
            fill: '#171a1c',
            fontFamily: 'DM Mono, ui-monospace, monospace',
          },
        },
        {
          type: 'text',
          left: 'center',
          top: '48%',
          style: { text: '总支出（元）', fontSize: 11, fill: 'rgba(23,26,28,0.4)' },
        },
      ],
    }
  }, [items, total])

  const ref = useChart(option, [option])

  if (!option) {
    return <p className="py-10 text-center text-xs text-ink/35">该范围内没有支出数据</p>
  }
  return <div ref={ref} className="h-72 w-full" />
}
