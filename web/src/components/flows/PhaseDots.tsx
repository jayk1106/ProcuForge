import type { PhaseLabel } from '@/types/workflow'

const PHASES: PhaseLabel[] = ['RFQ', 'NEG', 'PO', 'GRN', 'INV', 'DONE']

interface PhaseDotsProps {
  phase: PhaseLabel
}

export function PhaseDots({ phase }: PhaseDotsProps) {
  const activeIndex = PHASES.indexOf(phase)

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1">
        {PHASES.map((p, i) => {
          const isCompleted = i < activeIndex
          const isActive = i === activeIndex
          const isEmpty = i > activeIndex

          let bgColor: string
          let borderColor: string
          let borderWidth = '0px'

          if (isCompleted) {
            bgColor = '#3A2E22'
            borderColor = '#3A2E22'
          } else if (isActive) {
            bgColor = '#8B3A0F'
            borderColor = '#8B3A0F'
          } else {
            bgColor = 'transparent'
            borderColor = '#C4B898'
            borderWidth = '1.5px'
          }

          return (
            <div
              key={p}
              title={p}
              style={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                backgroundColor: bgColor,
                border: `${borderWidth} solid ${borderColor}`,
                flexShrink: 0,
              }}
            />
          )
        })}
      </div>
      <span
        className="text-[10px] font-bold tracking-widest"
        style={{ color: '#7A6E5C' }}
      >
        {phase}
      </span>
    </div>
  )
}
