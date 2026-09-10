'use client'

import { useEffect, useRef, useState } from 'react'
import { cn } from '@jobnok/ui'
import { PREVIEW_BASE_WIDTH, PREVIEW_BASE_HEIGHT } from '@/lib/resumePreview'
import { ResumeSkeleton } from './ResumeSkeleton'

// A resume thumbnail that measures its OWN rendered width (via
// ResizeObserver) and scales the fixed-size iframe content to match, instead
// of assuming a fixed pixel width up front. A fixed-width thumbnail breaks
// the moment its container is narrower than that assumption — e.g. the
// template-picker dialog's grid going from 4 columns down to 2 on mobile
// gives each cell ~90px, and a thumbnail hardcoded to 168px wide doesn't
// shrink to fit, so it overflows into neighboring cells. Sizing off the
// container's actual width instead works at any column count or rail width.
// Shared across the editor's Layouts rail/template picker and the My Docs
// page's document cards — not editor-scoped, lives in components/shared/.
//
// cropHeight: when set, shows a short "peek" at a fixed pixel height instead
// of the full page (Layouts rail/template picker need the whole page shape
// to compare layouts; My Docs just wants a glance, not a full A4-tall card).
// The iframe still scales off the container's actual width exactly as
// before — a fixed height container with overflow-hidden just clips
// whatever of the scaled page falls past it, so text isn't shrunk any
// further, only the visible portion is shorter.
export function ScaledResumeThumb({ html, label, className, cropHeight }: {
  html: string | null | undefined
  label: string
  className?: string
  cropHeight?: number
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(0)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const compute = () => {
      const width = el.clientWidth
      if (width > 0) setScale(width / PREVIEW_BASE_WIDTH)
    }
    compute()
    const ro = new ResizeObserver(compute)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  return (
    <div
      ref={containerRef}
      className={cn('w-full overflow-hidden relative', className)}
      style={cropHeight ? { height: cropHeight } : { aspectRatio: `${PREVIEW_BASE_WIDTH} / ${PREVIEW_BASE_HEIGHT}` }}
    >
      {html && scale > 0 ? (
        <>
          <iframe
            srcDoc={html}
            className="border-0 pointer-events-none block"
            style={{
              width: PREVIEW_BASE_WIDTH, height: PREVIEW_BASE_HEIGHT,
              transform: `scale(${scale})`, transformOrigin: 'top left',
            }}
            sandbox=""
            scrolling="no"
            title={label}
            tabIndex={-1}
          />
          {cropHeight && (
            <div className="absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-white to-transparent pointer-events-none" />
          )}
        </>
      ) : (
        <ResumeSkeleton compact />
      )}
    </div>
  )
}
