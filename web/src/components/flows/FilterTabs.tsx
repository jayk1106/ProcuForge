'use client'

import type { FilterTab, WorkflowSummary } from '@/types/workflow'
import { cn } from '@/lib/utils'

interface FilterTabsProps {
  activeTab: FilterTab
  summary: WorkflowSummary
  onTabChange: (tab: FilterTab) => void
}

const TABS: { key: FilterTab; label: string; countKey: keyof WorkflowSummary }[] = [
  { key: 'ALL', label: 'ALL', countKey: 'total' },
  { key: 'IN_PROGRESS', label: 'IN PROGRESS', countKey: 'inProgress' },
  { key: 'NEEDS_ACTION', label: 'NEEDS YOUR ACTION', countKey: 'needsAction' },
  { key: 'COMPLETED', label: 'COMPLETED', countKey: 'completed' },
  { key: 'WALKED_AWAY', label: 'WALKED AWAY', countKey: 'walkedAway' },
]

export function FilterTabs({ activeTab, summary, onTabChange }: FilterTabsProps) {
  return (
    <div className="flex items-center gap-0 border-b" style={{ borderColor: '#CBBF9F' }}>
      {TABS.map((tab) => {
        const isActive = tab.key === activeTab
        const count = summary[tab.countKey]

        return (
          <button
            key={tab.key}
            onClick={() => onTabChange(tab.key)}
            className={cn(
              'cursor-pointer border-b-2 px-4 py-2 text-xs font-bold transition-colors',
              isActive ? '-mb-px' : 'border-transparent'
            )}
            style={{
              borderBottomColor: isActive ? '#1C1816' : 'transparent',
              color: isActive ? '#1C1816' : '#7A6E5C',
              background: 'transparent',
            }}
          >
            {tab.label}
            <span className="ml-1 font-normal">· {count}</span>
          </button>
        )
      })}
    </div>
  )
}
