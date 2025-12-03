import { useEffect, useState, useRef, useCallback } from 'react'

/**
 * Hook that returns a debounced value
 */
export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => {
      clearTimeout(handler)
    }
  }, [value, delay])

  return debouncedValue
}

/**
 * Hook that returns a debounced callback
 */
export function useDebouncedCallback<TArgs extends unknown[]>(
  callback: (...args: TArgs) => void | Promise<void>,
  delay: number
): [(...args: TArgs) => void, () => void] {
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)
  const callbackRef = useRef(callback)

  // Update callback ref when it changes
  useEffect(() => {
    callbackRef.current = callback
  }, [callback])

  // Cancel function
  const cancel = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
  }, [])

  // Debounced function
   
  const debouncedCallback = useCallback(
    (...args: TArgs) => {
      cancel()

      timeoutRef.current = setTimeout(() => {
        callbackRef.current(...args)
      }, delay)
    },
    [delay, cancel]
  )

  // Cleanup on unmount
  useEffect(() => {
    return cancel
  }, [cancel])

  return [debouncedCallback, cancel]
}

/**
 * Hook for debounced validation
 */
export function useDebouncedValidation<T>(
  value: T,
  validator: (value: T) => Promise<boolean> | boolean,
  delay: number = 300
): {
  isValidating: boolean
  isValid: boolean | null
  error: Error | null
} {
  const [isValidating, setIsValidating] = useState(false)
  const [isValid, setIsValid] = useState<boolean | null>(null)
  const [error, setError] = useState<Error | null>(null)
  
  const debouncedValue = useDebounce(value, delay)

  useEffect(() => {
    let cancelled = false

    const validate = async () => {
      if (debouncedValue === null || debouncedValue === undefined) {
        setIsValid(null)
        setError(null)
        return
      }

      setIsValidating(true)
      setError(null)

      try {
        const result = await validator(debouncedValue)
        if (!cancelled) {
          setIsValid(result)
          setIsValidating(false)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err : new Error('Validation failed'))
          setIsValid(false)
          setIsValidating(false)
        }
      }
    }

    validate()

    return () => {
      cancelled = true
    }
  }, [debouncedValue, validator])

  return { isValidating, isValid, error }
}

/**
 * Hook for debounced search with loading state
 */
export function useDebouncedSearch<T>(
  searchFn: (query: string) => Promise<T[]>,
  delay: number = 500
): {
  search: (query: string) => void
  results: T[]
  isSearching: boolean
  error: Error | null
} {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<T[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  
  const debouncedQuery = useDebounce(query, delay)

  useEffect(() => {
    let cancelled = false

    const performSearch = async () => {
      if (!debouncedQuery) {
        setResults([])
        setError(null)
        return
      }

      setIsSearching(true)
      setError(null)

      try {
        const searchResults = await searchFn(debouncedQuery)
        if (!cancelled) {
          setResults(searchResults)
          setIsSearching(false)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err : new Error('Search failed'))
          setResults([])
          setIsSearching(false)
        }
      }
    }

    performSearch()

    return () => {
      cancelled = true
    }
  }, [debouncedQuery, searchFn])

  const search = useCallback((newQuery: string) => {
    setQuery(newQuery)
  }, [])

  return { search, results, isSearching, error }
}
