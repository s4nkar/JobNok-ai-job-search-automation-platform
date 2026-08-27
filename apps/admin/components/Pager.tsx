'use client'

import { Button } from '@jobnok/ui'

interface PagerProps {
  offset: number
  pageSize: number
  total: number
  onOffsetChange: (offset: number) => void
}

export function Pager({ offset, pageSize, total, onOffsetChange }: PagerProps) {
  if (total === 0) return null

  const from = offset + 1
  const to = Math.min(offset + pageSize, total)
  const canPrev = offset > 0
  const canNext = to < total

  return (
    <div className="flex items-center justify-between pt-2">
      <p className="text-xs text-muted-foreground">
        Showing {from}-{to} of {total}
      </p>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!canPrev}
          onClick={() => onOffsetChange(Math.max(0, offset - pageSize))}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={!canNext}
          onClick={() => onOffsetChange(offset + pageSize)}
        >
          Next
        </Button>
      </div>
    </div>
  )
}
