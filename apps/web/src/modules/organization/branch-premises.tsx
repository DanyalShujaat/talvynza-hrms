import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useQueryClient } from '@tanstack/react-query'
import { LocateFixed, MapPin, Plus } from 'lucide-react'
import * as React from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardBody, ErrorState, Skeleton } from '@/components/ui/card'
import { ConfirmButton, SlideOver } from '@/components/ui/extras'
import { Field, Input } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { useGet, useSend } from '@/lib/hooks'
import { readLocation } from '@/lib/location'

interface Premise { name: string; latitude: number; longitude: number; radius_m: number }
interface Draft { name: string; latitude: string; longitude: string; radius: string }
const empty: Draft = { name: '', latitude: '', longitude: '', radius: '100' }

function coordinates(draft: Draft): [number, number] | null {
  const latitude = Number(draft.latitude)
  const longitude = Number(draft.longitude)
  return draft.latitude.trim() && draft.longitude.trim() && Number.isFinite(latitude) && Number.isFinite(longitude)
    && Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180 ? [latitude, longitude] : null
}

function PremisesMap({ premises, draft, focus, onPick, onResize }: {
  premises: Premise[]
  draft: Draft
  focus: [number, number] | null
  onPick: (latitude: number, longitude: number) => void
  onResize: (radius: number) => void
}) {
  const node = React.useRef<HTMLDivElement>(null)
  const mapRef = React.useRef<L.Map | null>(null)
  const circles = React.useRef<L.LayerGroup | null>(null)
  const initial = React.useRef(premises[0])
  const [tileError, setTileError] = React.useState(false)
  React.useEffect(() => {
    if (!node.current) return
    const first = initial.current
    const map = L.map(node.current, { scrollWheelZoom: false }).setView(
      first ? [first.latitude, first.longitude] : [20, 0], first ? 16 : 2,
    )
    mapRef.current = map
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
      referrerPolicy: 'strict-origin-when-cross-origin',
    }).addTo(map)
    tiles.on('tileerror', () => setTileError(true))
    tiles.on('tileload', () => setTileError(false))
    circles.current = L.layerGroup().addTo(map)
    map.on('click', ({ latlng }) => {
      const point = latlng.wrap()
      onPick(point.lat, point.lng)
      if (map.getZoom() < 14) map.setView(point, 16)
    })
    const resize = new ResizeObserver(() => map.invalidateSize())
    resize.observe(node.current)
    return () => { resize.disconnect(); map.remove(); mapRef.current = null; circles.current = null }
  }, [onPick])

  React.useEffect(() => {
    const layer = circles.current
    if (!layer) return
    layer.clearLayers()
    for (const p of premises) {
      L.circle([p.latitude, p.longitude], { radius: p.radius_m, color: '#138074', weight: 2 }).addTo(layer)
    }
    const point = coordinates(draft)
    const radius = Number(draft.radius)
    if (point && radius >= 10 && radius <= 10_000) {
      const map = mapRef.current
      if (!map) return
      const center = L.latLng(point)
      const circle = L.circle(center, { radius, color: '#2563eb', weight: 2, dashArray: '5 4' }).addTo(layer)
      const handle = (position: L.LatLng, title: string, color: string) => L.marker(position, {
        draggable: true, title, alt: title,
        icon: L.divIcon({ className: '', iconSize: [18, 18], iconAnchor: [9, 9],
          html: `<span style="display:block;width:18px;height:18px;background:${color};border:2px solid white;border-radius:50%;box-shadow:0 0 0 1px #182744"></span>` }),
      }).addTo(layer)
      const delta = radius / (111_195 * Math.max(0.08, Math.cos(center.lat * Math.PI / 180)))
      const centerHandle = handle(center, 'Drag to move the center', '#2563eb')
      const radiusHandle = handle(L.latLng(center.lat, center.lng + delta), 'Drag to resize the perimeter', '#d97706')
      centerHandle.on('drag', () => {
        const point = centerHandle.getLatLng()
        circle.setLatLng(point)
        radiusHandle.setLatLng([point.lat, point.lng + delta])
      })
      centerHandle.on('dragend', () => {
        const point = centerHandle.getLatLng().wrap()
        onPick(point.lat, point.lng)
      })
      const distance = () => Math.min(10_000, Math.max(10, Math.round(map.distance(center, radiusHandle.getLatLng()))))
      radiusHandle.on('drag', () => circle.setRadius(distance()))
      radiusHandle.on('dragend', () => onResize(distance()))
    }
  }, [premises, draft, onPick, onResize])
  React.useEffect(() => {
    if (focus) mapRef.current?.setView(focus, 16)
  }, [focus])

  return (
    <>
      <div ref={node} aria-label="Map for placing branch premises" className="relative z-0 h-64 overflow-hidden rounded-lg border border-border bg-surface-2 sm:h-80" />
      {tileError && <p className="mt-2 text-xs text-muted" role="status">Map tiles are unavailable. You can enter the coordinates below.</p>}
    </>
  )
}

function PremisesEditor({ branchId, premises }: { branchId: string; premises: Premise[] }) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = React.useState<Draft>(empty)
  const [editing, setEditing] = React.useState<number | null>(null)
  const [focus, setFocus] = React.useState<[number, number] | null>(null)
  const [locating, setLocating] = React.useState(false)
  const reset = () => { setDraft(empty); setEditing(null) }
  const path = `/branches/${branchId}/premises`
  const save = useSend<{ premises: Premise[] }, { premises: Premise[] }>('PUT', path, {
    invalidate: ['/branches', '/attendance'], success: 'Branch premises updated',
    onSuccess: result => { queryClient.setQueryData([path, {}], result); reset() },
  })
  const pick = React.useCallback((latitude: number, longitude: number) => {
    setDraft(value => ({ ...value, latitude: latitude.toFixed(6), longitude: longitude.toFixed(6) }))
  }, [])
  const resize = React.useCallback((radius: number) => setDraft(value => ({ ...value, radius: String(radius) })), [])
  const locate = async () => {
    setLocating(true)
    try {
      const location = await readLocation()
      pick(location.latitude, location.longitude)
      setFocus([location.latitude, location.longitude])
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setLocating(false)
    }
  }
  const position = coordinates(draft)
  const radius = Number(draft.radius)
  const canSave = !!position && draft.name.trim().length >= 2 && Number.isInteger(radius) && radius >= 10 && radius <= 10_000
    && (editing != null || premises.length < 20)
  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!position || !canSave) return
    const replacement = { name: draft.name.trim(), latitude: position[0], longitude: position[1], radius_m: radius }
    save.mutate({ premises: editing == null ? [...premises, replacement] : premises.map((p, i) => i === editing ? replacement : p) })
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">{premises.length
        ? 'Web punches are blocked for this branch. Mobile punches must fall inside a saved perimeter. Biometric punches are imported separately.'
        : 'No premises set. Employees in this branch can punch from anywhere without sharing their location.'}</p>
      <PremisesMap premises={premises} draft={draft} focus={focus} onPick={pick} onResize={resize} />
      <Card><CardBody>
        <form onSubmit={submit} className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold">{editing == null ? 'Add a premise' : 'Edit premise'}</h3>
            <Button type="button" variant="outline" size="sm" onClick={locate} loading={locating}><LocateFixed className="h-4 w-4" />Use my location</Button>
          </div>
          <p className="text-xs text-muted">Click the map to place the center. Drag the blue handle to move it or the amber handle to resize the perimeter. You can also enter exact values below.</p>
          <Field id="premise-name" label="Premise name">{a => <Input {...a} maxLength={80} required value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} />}</Field>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field id="premise-latitude" label="Latitude">{a => <Input {...a} type="number" step="any" min="-90" max="90" required value={draft.latitude} onChange={e => setDraft({ ...draft, latitude: e.target.value })} />}</Field>
            <Field id="premise-longitude" label="Longitude">{a => <Input {...a} type="number" step="any" min="-180" max="180" required value={draft.longitude} onChange={e => setDraft({ ...draft, longitude: e.target.value })} />}</Field>
            <Field id="premise-radius" label="Radius in meters">{a => <Input {...a} type="number" min="10" max="10000" required value={draft.radius} onChange={e => setDraft({ ...draft, radius: e.target.value })} />}</Field>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" loading={save.isPending} disabled={!canSave}><Plus className="h-4 w-4" />Save premise</Button>
            {editing != null && <Button type="button" variant="ghost" onClick={reset}>Cancel editing</Button>}
          </div>
        </form>
      </CardBody></Card>
      {premises.length > 0 && <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
        {premises.map((p, index) => (
          <li key={p.name} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5">
            <div className="flex items-center gap-2"><MapPin className="h-4 w-4 text-primary" aria-hidden /><div><p className="text-sm font-semibold">{p.name}</p><p className="text-xs text-muted">{p.radius_m} m radius</p></div></div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={save.isPending} onClick={() => {
                setEditing(index)
                setDraft({ name: p.name, latitude: String(p.latitude), longitude: String(p.longitude), radius: String(p.radius_m) })
                setFocus([p.latitude, p.longitude])
              }}>Edit</Button>
              <ConfirmButton label="Remove" title={`Remove ${p.name}?`}
                message={premises.length === 1 ? 'Removing the last perimeter restores any enabled web punches and removes the mobile location check.' : 'This location will be removed from the branch’s allowed areas.'}
                confirmLabel="Remove premise" loading={save.isPending} onConfirm={() => save.mutate({ premises: premises.filter((_, i) => i !== index) })} />
            </div>
          </li>
        ))}
      </ul>}
    </div>
  )
}

export default function BranchPremises({ branch, onClose }: { branch: { id: string; name: string }; onClose: () => void }) {
  const q = useGet<{ premises: Premise[] }>(`/branches/${branch.id}/premises`)
  return (
    <SlideOver open onOpenChange={open => { if (!open) onClose() }} title={`Premises · ${branch.name}`} wide>
      {q.isPending ? <Skeleton className="h-64" /> : q.isError
        ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} />
        : <PremisesEditor branchId={branch.id} premises={q.data.premises} />}
    </SlideOver>
  )
}
