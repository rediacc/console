import React, { lazy, Suspense, useEffect } from 'react';
import { Flex } from 'antd';
import { useDispatch, useSelector } from 'react-redux';
import { BrowserRouter, HashRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { initializeApiClient } from '@/api/init';
import { AppProviders } from '@/components/app/AppProviders';
import { ErrorBoundary } from '@/components/app/ErrorBoundary';
import { InteractionTracker } from '@/components/app/InteractionTracker';
import { SessionExpiredModal } from '@/components/app/SessionExpiredModal';
import { ThemedToaster } from '@/components/app/ThemedToaster';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { TelemetryProvider } from '@/components/common/TelemetryProvider';
import AuthLayout from '@/components/layout/AuthLayout';
import MainLayout from '@/components/layout/MainLayout';
import { featureFlags } from '@/config/featureFlags';
import LoginPage from '@/pages/login';
import { selectIsAuthenticated } from '@/store/auth/authSelectors';
import { loginSuccess } from '@/store/auth/authSlice';
import { RootState } from '@/store/store';
import { getAuthData, migrateFromLocalStorage } from '@/utils/auth';
import { getBasePath } from '@/utils/basePath';
import { isElectron } from '@/utils/environment';

// Lazy load heavy pages
const DashboardPage = lazy(() =>
  import('@/features/dashboard').then((m) => ({ default: m.DashboardPage }))
);
const MachinesPage = lazy(() =>
  import('@/features/machines').then((m) => ({ default: m.MachinesPage }))
);
const MachineRepositoriesPage = lazy(() =>
  import('@/features/resources').then((m) => ({ default: m.MachineRepositoriesPage }))
);
const RepositoryContainersPage = lazy(() =>
  import('@/features/resources').then((m) => ({ default: m.RepositoryContainersPage }))
);
const CephPage = lazy(() => import('@/features/ceph').then((m) => ({ default: m.CephPage })));
const QueuePage = lazy(() => import('@/features/queue').then((m) => ({ default: m.QueuePage })));
const AuditPage = lazy(() => import('@/features/audit').then((m) => ({ default: m.AuditPage })));
const CredentialsPage = lazy(() =>
  import('@/features/credentials').then((m) => ({ default: m.CredentialsPage }))
);
const StoragePage = lazy(() =>
  import('@/features/storage').then((m) => ({ default: m.StoragePage }))
);
const UsersPage = lazy(() =>
  import('@/features/organization').then((m) => ({ default: m.UsersPage }))
);
const TeamsPage = lazy(() =>
  import('@/features/organization').then((m) => ({ default: m.TeamsPage }))
);
const AccessPage = lazy(() =>
  import('@/features/organization').then((m) => ({ default: m.AccessPage }))
);
const ProfilePage = lazy(() =>
  import('@/features/settings').then((m) => ({ default: m.ProfilePage }))
);
const CompanyPage = lazy(() =>
  import('@/features/settings').then((m) => ({ default: m.CompanyPage }))
);
const InfrastructurePage = lazy(() =>
  import('@/features/settings').then((m) => ({ default: m.InfrastructurePage }))
);

// Loading component
const PageLoader: React.FC = () => {
  return (
    <Flex data-testid="page-loader" align="center" justify="center" vertical>
      <LoadingWrapper loading centered minHeight={400}>
        <Flex />
      </LoadingWrapper>
    </Flex>
  );
};

// Component to handle GitHub Pages 404 redirect via sessionStorage
const RedirectHandler: React.FC = () => {
  const navigate = useNavigate();

  useEffect(() => {
    // Check if we were redirected from a 404 page
    const redirectPath = sessionStorage.getItem('redirect_path');

    if (redirectPath) {
      // Clear the redirect path immediately to prevent loops
      sessionStorage.removeItem('redirect_path');

      // Navigate to the intended path
      void navigate(redirectPath, { replace: true });
    }
  }, [navigate]);

  return null;
};

const AppContent: React.FC = () => {
  const dispatch = useDispatch();
  const isAuthenticated = useSelector(selectIsAuthenticated);
  const showSessionExpiredModal = useSelector(
    (state: RootState) => state.auth.showSessionExpiredModal
  );
  const stayLoggedOutMode = useSelector((state: RootState) => state.auth.stayLoggedOutMode);
  const [featureFlagVersion, setFeatureFlagVersion] = React.useState<number>(0);
  // Prevent unused variable warnings - feature flag triggers re-renders
  void featureFlagVersion;

  useEffect(() => {
    const initialize = async () => {
      // Initialize API client with correct URL
      await initializeApiClient();

      // Initialize feature flags after API connection is established
      // This determines if we're in local development mode or production
      featureFlags.updateDevelopmentState();

      // Migrate any existing localStorage data to secure memory storage
      await migrateFromLocalStorage();

      // Check for existing auth data on mount
      const authData = await getAuthData();
      if (authData.token && authData.email) {
        // Token exists in secure storage, restore session (token not stored in Redux for security)
        dispatch(
          loginSuccess({
            user: { email: authData.email, company: authData.company ?? undefined },
            company: authData.company ?? undefined,
          })
        );
      }
    };

    void initialize();
  }, [dispatch]);

  useEffect(() => {
    const unsubscribe = featureFlags.subscribe(() => {
      setFeatureFlagVersion((version) => version + 1);
    });
    return unsubscribe;
  }, []);

  // Use HashRouter for Electron (file:// protocol), BrowserRouter for web
  const Router = isElectron() ? HashRouter : BrowserRouter;
  const routerProps = isElectron() ? {} : { basename: getBasePath() };

  return (
    <AppProviders>
      <Router {...routerProps}>
        <RedirectHandler />
        <TelemetryProvider>
          <ErrorBoundary>
            <InteractionTracker>
              <Routes>
                {/* Auth routes */}
                <Route element={<AuthLayout />}>
                  <Route path="/login" element={<LoginPage />} />
                </Route>

                {/* Protected routes */}
                <Route
                  element={
                    isAuthenticated || showSessionExpiredModal || stayLoggedOutMode ? (
                      <MainLayout />
                    ) : (
                      <Navigate to="/login" replace />
                    )
                  }
                >
                  <Route path="/" element={<Navigate to="/machines" replace />} />

                  {/* Dashboard */}
                  <Route
                    path="/dashboard"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <DashboardPage />
                      </Suspense>
                    }
                  />

                  {/* Organization */}
                  <Route
                    path="/machines"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <MachinesPage />
                      </Suspense>
                    }
                  />
                  <Route path="/resources" element={<Navigate to="/machines" replace />} />
                  <Route
                    path="/credentials"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <CredentialsPage />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/storage"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <StoragePage />
                      </Suspense>
                    }
                  />

                  {/* Organization redirects */}
                  <Route
                    path="/organization"
                    element={<Navigate to="/organization/users" replace />}
                  />
                  <Route path="/settings" element={<Navigate to="/settings/profile" replace />} />

                  {/* Organization */}
                  <Route
                    path="/organization/users"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <UsersPage />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/organization/teams"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <TeamsPage />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/organization/access"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <AccessPage />
                      </Suspense>
                    }
                  />

                  {/* Settings */}
                  <Route
                    path="/settings/profile"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <ProfilePage />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/settings/company"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <CompanyPage />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/settings/infrastructure"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <InfrastructurePage />
                      </Suspense>
                    }
                  />

                  {/* Machine Repositories */}
                  <Route
                    path="/machines/:machineName/repositories"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <MachineRepositoriesPage />
                      </Suspense>
                    }
                  />

                  {/* Repository Containers */}
                  <Route
                    path="/machines/:machineName/repositories/:repositoryName/containers"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <RepositoryContainersPage />
                      </Suspense>
                    }
                  />

                  {/* Legacy repos routes - redirect to repositories */}
                  <Route
                    path="/machines/:machineName/repos"
                    element={<Navigate to="../repositories" replace />}
                  />
                  <Route
                    path="/machines/:machineName/repos/:repositoryName/containers"
                    element={
                      <Navigate to="../../repositories/:repositoryName/containers" replace />
                    }
                  />

                  {/* Ceph */}
                  <Route path="/ceph" element={<Navigate to="/ceph/clusters" replace />} />
                  <Route
                    path="/ceph/clusters"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <CephPage view="clusters" />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/ceph/pools"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <CephPage view="pools" />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/ceph/machines"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <CephPage view="machines" />
                      </Suspense>
                    }
                  />

                  {/* Queue */}
                  <Route
                    path="/queue"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <QueuePage />
                      </Suspense>
                    }
                  />

                  {/* Audit */}
                  <Route
                    path="/audit"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <AuditPage />
                      </Suspense>
                    }
                  />
                </Route>
              </Routes>
            </InteractionTracker>
          </ErrorBoundary>
        </TelemetryProvider>
      </Router>
      <ThemedToaster />
      <SessionExpiredModal />
    </AppProviders>
  );
};

const App: React.FC = () => {
  return <AppContent />;
};

export default App;
