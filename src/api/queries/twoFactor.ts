import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import apiClient from '@/api/client'
import { showMessage } from '@/utils/messages'
import { hashPassword } from '@/utils/auth'
import { getFirstRow } from '@/core/api/response'

export interface TwoFactorStatus {
  isTFAEnabled: boolean
  isAuthorized: boolean
  authenticationStatus: string
}

export interface EnableTwoFactorResponse {
  secret: string
  userEmail: string
  authType: string
  result: string
}

// Get TFA status for current user
export const useGetTFAStatus = () => {
  const userEmail = useSelector((state: RootState) => state.auth.user?.email)
  
  return useQuery({
    queryKey: ['tfa-status', userEmail],
    queryFn: async () => {
      const response = await apiClient.get('/GetRequestAuthenticationStatus')

      let data =
        getFirstRow<Record<string, unknown>>(response, 1) ??
        getFirstRow<Record<string, unknown>>(response, 0) ??
        (response.isTFAEnabled !== undefined ? (response as unknown as Record<string, unknown>) : null)
      
      if (!data) {
        return {
          isTFAEnabled: false,
          isAuthorized: false,
          authenticationStatus: 'Unable to determine TFA status'
        } as TwoFactorStatus
      }
      
      // Handle potential type coercion issues (SQL Server might return 0/1 or "true"/"false")
      const isTFAEnabled = data.isTFAEnabled === true || 
                          data.isTFAEnabled === 1 || 
                          data.isTFAEnabled === "true" ||
                          data.isTFAEnabled === "1"
      
      const isAuthorized = data.isAuthorized === true || 
                          data.isAuthorized === 1 || 
                          data.isAuthorized === "true" ||
                          data.isAuthorized === "1"
      
      return {
        isTFAEnabled: isTFAEnabled,
        isAuthorized: isAuthorized,
        authenticationStatus: data.authenticationStatus || 'No TFA configured'
      } as TwoFactorStatus
    },
    enabled: !!userEmail
  })
}

// Enable TFA for current user
export const useEnableTFA = () => {
  const queryClient = useQueryClient()
  const userEmail = useSelector((state: RootState) => state.auth.user?.email)
  
  return useMutation({
    mutationFn: async (data: { 
      password?: string; 
      generateOnly?: boolean;
      verificationCode?: string;
      secret?: string;
      confirmEnable?: boolean;
    }) => {
      // Generate only mode - get secret without saving
      if (data.generateOnly && data.password) {
        const passwordHash = await hashPassword(data.password)
        const response = await apiClient.post('/UpdateUserTFA', {
          enable: true,
          userHash: passwordHash,
          generateOnly: true,
        })

        const responseData = getFirstRow<EnableTwoFactorResponse>(response, 1)

        if (!responseData) {
          throw new Error('Unexpected response format: missing TFA data table')
        }

        if (!responseData.secret) {
          throw new Error('TFA secret not returned by server')
        }

        return responseData
      }
      
      // Confirm enable mode - verify code and save
      if (data.confirmEnable && data.verificationCode && data.secret) {
        const response = await apiClient.post('/UpdateUserTFA', {
          enable: true,
          verificationCode: data.verificationCode,
          secret: data.secret,
          confirmEnable: true,
        })

        return getFirstRow<EnableTwoFactorResponse>(response, 0)
      }
      
      throw new Error('Invalid parameters for TFA operation')
    },
    onSuccess: (_data, variables) => {
      // Only update cache and show success if we're confirming enable
      if (variables.confirmEnable) {
        // Immediately update the cache with the new status
        queryClient.setQueryData(['tfa-status', userEmail], {
          isTFAEnabled: true,
          isAuthorized: true,
          authenticationStatus: 'TFA enabled'
        } as TwoFactorStatus)
        
        // Then invalidate to ensure fresh data on next fetch
        queryClient.invalidateQueries({ queryKey: ['tfa-status'] })
        showMessage('success', 'TFA has been successfully enabled and verified.')
      }
    },
    onError: (error: any) => {
      // The error message will come from the API's error array or the extracted error message
      const errorMessage = error.message || 'Failed to enable TFA'
      
      // If it's a 409 conflict error (TFA already enabled), refresh the status
      if (errorMessage.includes('already enabled')) {
        queryClient.invalidateQueries({ queryKey: ['tfa-status'] })
      }
      
      showMessage('error', errorMessage)
    },
  })
}

// Disable TFA for current user
export const useDisableTFA = () => {
  const queryClient = useQueryClient()
  const userEmail = useSelector((state: RootState) => state.auth.user?.email)
  
  return useMutation({
    mutationFn: async (data: { password: string; currentCode: string }) => {
      const passwordHash = await hashPassword(data.password)
      const response = await apiClient.post('/UpdateUserTFA', {
        enable: false,
        userHash: passwordHash,
        currentCode: data.currentCode,
      })

      return getFirstRow<Record<string, unknown>>(response, 0)
    },
    onSuccess: () => {
      // Immediately update the cache with the new status
      queryClient.setQueryData(['tfa-status', userEmail], {
        isTFAEnabled: false,
        isAuthorized: true,
        authenticationStatus: 'No TFA configured'
      } as TwoFactorStatus)
      
      // Then invalidate to ensure fresh data on next fetch
      queryClient.invalidateQueries({ queryKey: ['tfa-status'] })
      showMessage('success', 'TFA has been disabled successfully')
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to disable TFA')
    },
  })
}

// Verify TFA code after login (privilege elevation)
export const useVerifyTFA = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { code: string }) => {
      const response = await apiClient.post('/PrivilegeAuthenticationRequest', {
        TFACode: data.code,
      })

      const responseData =
        getFirstRow<Record<string, unknown>>(response, 1) ?? getFirstRow<Record<string, unknown>>(response, 0)
      return {
        isAuthorized: responseData?.isAuthorized || false,
        result: responseData?.result || '',
        hasTFAEnabled: responseData?.hasTFAEnabled
      }
    },
    onSuccess: (data) => {
      if (data.isAuthorized) {
        queryClient.invalidateQueries({ queryKey: ['tfa-status'] })
        showMessage('success', 'TFA verification successful')
      }
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Invalid TFA code')
    },
  })
}
