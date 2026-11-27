export interface PunchLocation {
  latitude: number
  longitude: number
  accuracy_m: number
}

export function readLocation(): Promise<PunchLocation> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Location is unavailable. Open the app over HTTPS on a device with location services.'))
      return
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => resolve({ latitude: coords.latitude, longitude: coords.longitude, accuracy_m: coords.accuracy }),
      error => reject(new Error(error.code === 1
        ? 'Allow location access in your browser and try again.'
        : 'Could not get your location. Check your device location settings and try again.')),
      { enableHighAccuracy: true, maximumAge: 0, timeout: 12_000 },
    )
  })
}
