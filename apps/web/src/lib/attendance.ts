export const attendanceChannels = {
  web: { label: 'Web attendance', description: 'Browser punches. A saved branch perimeter blocks this channel.' },
  mobile: { label: 'Mobile attendance', description: 'Location is checked when the assigned branch has a saved perimeter.' },
  premises: { label: 'Premises attendance (biometric)', description: 'Punches from a branch device import use the employee’s biometric ID.' },
} as const

export type AttendanceChannel = keyof typeof attendanceChannels
export function isAttendanceChannel(value: string | null): value is AttendanceChannel {
  return value === 'web' || value === 'mobile' || value === 'premises'
}
