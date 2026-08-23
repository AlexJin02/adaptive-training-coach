import { useCallback, useEffect, useState } from 'react'
import { ApiError } from './client'

export interface ResourceState<T> {
  data: T | null
  loading: boolean
  error: ApiError | null
  reload: () => void
  setData: React.Dispatch<React.SetStateAction<T | null>>
}

export function useResource<T>(loader: () => Promise<T>, dependencies: readonly unknown[] = []): ResourceState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [nonce, setNonce] = useState(0)

  const reload = useCallback(() => setNonce((value) => value + 1), [])

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    loader()
      .then((value) => {
        if (active) setData(value)
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof ApiError ? reason : new ApiError('Unable to load this view.'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
    // The caller intentionally controls refetch inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, ...dependencies])

  return { data, loading, error, reload, setData }
}
