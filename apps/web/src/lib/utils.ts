import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs))

export function formatDate(
  iso: string | null | undefined,
  opts: Intl.DateTimeFormatOptions = { dateStyle: 'medium', timeStyle: 'short' },
) {
  return iso ? new Intl.DateTimeFormat(undefined, opts).format(new Date(iso)) : '-'
}

export function daysUntil(iso: string | null | undefined) {
  return iso ? Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000)) : null
}

export const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join('')
