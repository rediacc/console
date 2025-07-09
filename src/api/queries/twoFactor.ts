import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import apiClient from '@/api/client'
import { createMutation } from '@/api/utils/mutationFactory'
import { showMessage } from '@/utils/messages'
import { hashPassword } from '@/utils/auth'

export interface TwoFactorStatus {
  is2FAEnabled: boolean
  isAuthorized: boolean
  authenticationStatus: string
}

export interface EnableTwoFactorResponse {
  secret: string
  userEmail: string
  authType: string
  result: string
}

// Get 2FA status for current user
export const useGet2FAStatus = () => {
  const userEmail = useSelector((state: RootState) => state.auth.user?.email)
  
  return useQuery({
    queryKey: ['2fa-status', userEmail],
    queryFn: async () => {
      const response = await apiClient.get('/GetRequestAuthenticationStatus')
      
      // Try to find the data in all possible locations
      let data = null
      
      // Check table 1 (expected location)
      if (response.tables && response.tables[1] && response.tables[1].data && response.tables[1].data[0]) {
        data = response.tables[1].data[0]
      }
      // Fallback to table 0
      else if (response.tables && response.tables[0] && response.tables[0].data && response.tables[0].data[0]) {
        data = response.tables[0].data[0]
      }
      // Check if data is directly in the response
      else if (response.is2FAEnabled !== undefined) {
        data = response
      }
      
      if (!data) {
        return {
          is2FAEnabled: false,
          isAuthorized: false,
          authenticationStatus: 'Unable to determine 2FA status'
        } as TwoFactorStatus
      }
      
      // Handle potential type coercion issues (SQL Server might return 0/1 or "true"/"false")
      const is2FAEnabled = data.is2FAEnabled === true || 
                          data.is2FAEnabled === 1 || 
                          data.is2FAEnabled === "true" ||
                          data.is2FAEnabled === "1"
      
      const isAuthorized = data.isAuthorized === true || 
                          data.isAuthorized === 1 || 
                          data.isAuthorized === "true" ||
                          data.isAuthorized === "1"
      
      return {
        is2FAEnabled: is2FAEnabled,
        isAuthorized: isAuthorized,
        authenticationStatus: data.authenticationStatus || 'No 2FA configured'
      } as TwoFactorStatus
    },
    enabled: !!userEmail
  })
}

// Enable 2FA for current user
export const useEnable2FA = () => {
  const queryClient = useQueryClient()
  const userEmail = useSelector((state: RootState) => state.auth.user?.email)
  
  return useMutation({
    mutationFn: async (data: { password: string }) => {
      const passwordHash = await hashPassword(data.password)
      const response = await apiClient.post('/UpdateUser2FA', {
        enable: true,
        userHash: passwordHash
      })
      
      // If we get here, the response has failure: 0
      // The API client's interceptor handles non-zero failure codes as errors
      
      // The 2FA secret is in the second table (index 1)
      const responseData = response.tables[1]?.data[0]
      
      // Ensure we have the expected response structure
      if (!response.tables[1]) {
        throw new Error('Unexpected response format: missing 2FA data table')
      }
      
      // Ensure we have a secret in the response
      if (!responseData?.secret) {
        throw new Error('2FA secret not returned by server')
      }
      
      return responseData as EnableTwoFactorResponse
    },
    onSuccess: (data, variables, context) => {
      // Immediately update the cache with the new status
      queryClient.setQueryData(['2fa-status', userEmail], {
        is2FAEnabled: true,
        isAuthorized: true,
        authenticationStatus: '2FA enabled'
      } as TwoFactorStatus)
      
      // Then invalidate to ensure fresh data on next fetch
      queryClient.invalidateQueries({ queryKey: ['2fa-status'] })
      showMessage('success', '2FA has been enabled. Please scan the QR code with your authenticator app.')
    },
    onError: (error: any) => {
      // The error message will come from the API's error array or the extracted error message
      const errorMessage = error.message || 'Failed to enable 2FA'
      
      // If it's a 409 conflict error (2FA already enabled), refresh the status
      if (errorMessage.includes('already enabled')) {
        queryClient.invalidateQueries({ queryKey: ['2fa-status'] })
      }
      
      showMessage('error', errorMessage)
    },
  })
}

// Disable 2FA for current user
export const useDisable2FA = () => {
  const queryClient = useQueryClient()
  const userEmail = useSelector((state: RootState) => state.auth.user?.email)
  
  return useMutation({
    mutationFn: async (data: { password: string; currentCode: string }) => {
      const passwordHash = await hashPassword(data.password)
      const response = await apiClient.post('/UpdateUser2FA', {
        enable: false,
        userHash: passwordHash,
        currentCode: data.currentCode
      })
      
      return response.tables[0]?.data[0]
    },
    onSuccess: () => {
      // Immediately update the cache with the new status
      queryClient.setQueryData(['2fa-status', userEmail], {
        is2FAEnabled: false,
        isAuthorized: true,
        authenticationStatus: 'No 2FA configured'
      } as TwoFactorStatus)
      
      // Then invalidate to ensure fresh data on next fetch
      queryClient.invalidateQueries({ queryKey: ['2fa-status'] })
      showMessage('success', '2FA has been disabled successfully')
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to disable 2FA')
    },
  })
}

// Verify 2FA code after login (privilege elevation)
export const useVerify2FA = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { code: string }) => {
      const response = await apiClient.post('/PrivilegeAuthenticationRequest', {
        '2FACode': data.code
      })
      
      // Check both tables for the response data
      const responseData = response.tables[1]?.data[0] || response.tables[0]?.data[0]
      return {
        isAuthorized: responseData?.isAuthorized || false,
        result: responseData?.result || '',
        has2FAEnabled: responseData?.has2FAEnabled
      }
    },
    onSuccess: (data) => {
      if (data.isAuthorized) {
        queryClient.invalidateQueries({ queryKey: ['2fa-status'] })
        showMessage('success', '2FA verification successful')
      }
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Invalid 2FA code')
    },
  })
}