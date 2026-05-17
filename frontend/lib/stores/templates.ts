'use client'

import { create } from 'zustand'
import { Template } from '@/lib/types'
import { PREBUILT_TEMPLATES } from '@/lib/templates/prebuilt'

interface TemplateStore {
  savedTemplates: Template[]
  setSavedTemplates: (templates: Template[]) => void
  addTemplate: (template: Template) => void
  updateTemplate: (id: string, updates: Partial<Template>) => void
  removeTemplate: (id: string) => void
  allTemplates: () => Template[]
}

export const useTemplateStore = create<TemplateStore>((set, get) => ({
  savedTemplates: [],

  setSavedTemplates: (templates) => set({ savedTemplates: templates }),

  addTemplate: (template) =>
    set((state) => ({ savedTemplates: [template, ...state.savedTemplates] })),

  updateTemplate: (id, updates) =>
    set((state) => ({
      savedTemplates: state.savedTemplates.map((t) =>
        t.id === id ? { ...t, ...updates } : t
      ),
    })),

  removeTemplate: (id) =>
    set((state) => ({
      savedTemplates: state.savedTemplates.filter((t) => t.id !== id),
    })),

  allTemplates: () => {
    const { savedTemplates } = get()
    return [...savedTemplates, ...PREBUILT_TEMPLATES]
  },
}))
