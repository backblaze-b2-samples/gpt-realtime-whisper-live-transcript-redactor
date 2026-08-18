import * as React from "react"

const MOBILE_BREAKPOINT = 768
const MOBILE_MEDIA_QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`

let mobileMediaQuery: MediaQueryList | undefined

function getMobileMediaQuery() {
  mobileMediaQuery ??= window.matchMedia(MOBILE_MEDIA_QUERY)
  return mobileMediaQuery
}

function subscribeToMobileChange(onStoreChange: () => void) {
  const mql = getMobileMediaQuery()
  mql.addEventListener("change", onStoreChange)
  return () => mql.removeEventListener("change", onStoreChange)
}

function getMobileSnapshot() {
  return getMobileMediaQuery().matches
}

function getServerMobileSnapshot() {
  return false
}

export function useIsMobile() {
  return React.useSyncExternalStore(
    subscribeToMobileChange,
    getMobileSnapshot,
    getServerMobileSnapshot,
  )
}
