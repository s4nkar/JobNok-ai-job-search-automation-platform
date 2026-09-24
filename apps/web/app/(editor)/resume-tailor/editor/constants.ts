// ZOOM_LEVELS is editor-specific; PREVIEW_BASE_WIDTH/HEIGHT are shared more
// broadly (My Docs' card previews too) and live in lib/resumePreview - kept
// re-exported here so every existing `from './constants'` import in this
// route keeps working unchanged.
export { PREVIEW_BASE_WIDTH, PREVIEW_BASE_HEIGHT } from '@/lib/resumePreview'

export const ZOOM_LEVELS = [50, 65, 75, 90, 100, 110, 125, 150]
