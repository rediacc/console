# Rediacc Web Application Implementation Plan

## 1. Application Overview

### Purpose
Transform the Rediacc CLI into a web-based graphical interface that maintains all functionality while providing an intuitive user experience through visual menus, forms, and interactive components.

### Core Principles
- **Feature Parity**: Every CLI command must have a corresponding web interface
- **Progressive Disclosure**: Complex operations revealed through logical navigation
- **Context Awareness**: Interface adapts based on user permissions and resource state
- **Visual Feedback**: Clear indication of operations, progress, and results

### Technology Stack (MANDATORY - NO OTHER PACKAGES ALLOWED)

The following packages constitute the COMPLETE technology stack for this project. Developers must NOT add any additional packages without explicit approval:

```json
{
  "dependencies": {
    // Core Framework
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.x",
    "typescript": "^5.x",
    
    // State Management
    "@reduxjs/toolkit": "^2.x",
    "react-redux": "^9.x",
    
    // API & Server State
    "@tanstack/react-query": "^5.x",
    "axios": "^1.x",
    
    // UI Component Library
    "antd": "^5.x",
    "@ant-design/icons": "^5.x",
    
    // Form Handling & Validation
    "react-hook-form": "^7.x",
    "zod": "^3.x",
    
    // Utilities
    "date-fns": "^3.x",
    "lodash": "^4.x",
    
    // Specialized Components
    "@monaco-editor/react": "^4.x",
    "react-hot-toast": "^2.x"
  },
  "devDependencies": {
    "vite": "^5.x",
    "@types/react": "^18.x",
    "@types/react-dom": "^18.x",
    "@types/lodash": "^4.x",
    "@vitejs/plugin-react": "^4.x"
  }
}
```

### Technology Justification

- **Redux Toolkit**: Chosen for complex state management with built-in best practices
- **Ant Design**: Provides comprehensive enterprise-grade components, especially tables and forms
- **React Query**: Handles server state, caching, and token chaining requirements
- **Axios**: Required for request/response interceptors to handle token rotation
- **React Hook Form + Zod**: Optimal combination for form handling with TypeScript-first validation
- **Vite**: Fastest build tool for improved developer experience
- **Monaco Editor**: Essential for JSON vault editing functionality
- **React Hot Toast**: Lightweight notification system for user feedback

## 2. Application Architecture

### 2.1 High-Level Structure

```
┌─────────────────────────────────────────────────┐
│                  Header/Navigation               │
├─────────────────┬───────────────────────────────┤
│                 │                                │
│    Sidebar      │         Main Content          │
│    Navigation   │         Area                   │
│                 │                                │
│                 │                                │
└─────────────────┴───────────────────────────────┘
```

### 2.2 Component Hierarchy

```
Application Root
├── Authentication Layer
│   ├── Login Screen
│   └── Session Management
├── Main Dashboard
│   ├── Header Component
│   │   ├── User Info
│   │   ├── Company Info
│   │   └── Logout
│   ├── Navigation Sidebar
│   │   ├── Resource Management
│   │   ├── User & Permissions
│   │   ├── Queue Operations
│   │   └── System Settings
│   └── Content Area
│       ├── Resource Views
│       ├── Forms
│       └── Data Tables
└── Notification System
```

### 2.3 Implementation Architecture

All components must be built using Ant Design components as the foundation. Custom styling should be minimal and use Ant Design's theming system. The application structure follows Redux Toolkit patterns with feature-based organization.

## 3. Navigation Structure

### 3.1 Primary Navigation Menu

Navigation must be implemented using Ant Design's Menu component in the sidebar with React Router for routing.

#### **Dashboard**
- Overview statistics (using Ant Design Card and Statistic components)
- Recent activities (using Ant Design Timeline component)
- Quick actions (using Ant Design Button components)

#### **Resources**
- **Teams**
  - List Teams (Ant Design Table with built-in sorting/filtering)
  - Create Team (Ant Design Form with React Hook Form integration)
  - Team Details (Ant Design Descriptions component)
  - Team Members Management (Ant Design Table with row actions)
- **Regions & Infrastructure**
  - **Regions**
    - List Regions
    - Create Region
    - Region Management
  - **Bridges**
    - List Bridges (filtered by region using Ant Design Select)
    - Create Bridge
    - Bridge Management
  - **Machines**
    - List Machines (filtered by team)
    - Create Machine
    - Machine Details
    - Machine Vault Configuration (Monaco Editor in Ant Design Modal)
- **Storage & Data**
  - **Repositories**
    - List Repositories
    - Create Repository
    - Repository Management
  - **Storage**
    - List Storage
    - Create Storage
    - Storage Management
  - **Schedules**
    - List Schedules
    - Create Schedule
    - Schedule Management

#### **Queue Management**
- **Queue Dashboard**
  - Active Queue Items (Ant Design Table with auto-refresh via React Query)
  - Queue Statistics (Ant Design Statistic components)
- **Queue Operations**
  - Add Function to Queue
    - Select machine first to auto-populate bridge
    - Bridge is required but determined by machine assignment
  - Available Functions Browser (Ant Design Tree component)
  - Queue Item Details (Ant Design Drawer component)
- **Machine Queues**
  - View by Machine (Ant Design Tabs)
  - Batch Operations (Ant Design Table with row selection)

#### **Users & Permissions**
- **User Management**
  - List Users
    - API: `POST /api/StoredProcedure/GetCompanyUsers`
  - Create User
    - API: `POST /api/StoredProcedure/CreateNewUser`
    - Body: `{"newUserEmail": "email", "newUserHash": "0x..."}`
  - User Activation/Deactivation
    - Activate: `POST /api/StoredProcedure/ActivateUserAccount` (no auth required)
    - Deactivate: `POST /api/StoredProcedure/UpdateUserToDeactivated`
  - Update User Details
    - Email: `POST /api/StoredProcedure/UpdateUserEmail`
    - Password: `POST /api/StoredProcedure/UpdateUserPassword`
- **Permission Groups**
  - List Permission Groups
    - API: `POST /api/StoredProcedure/GetCompanyPermissionGroups`
  - Create Permission Group
    - API: `POST /api/StoredProcedure/CreatePermissionGroup`
  - Manage Group Permissions
    - Add: `POST /api/StoredProcedure/CreatePermissionInGroup`
    - Remove: `POST /api/StoredProcedure/DeletePermissionFromGroup`
  - Assign Users to Groups
    - API: `POST /api/StoredProcedure/UpdateUserAssignedPermissions`
- **Sessions**
  - Active Sessions
    - API: `POST /api/StoredProcedure/GetUserRequests`
  - Session History

#### **Company Settings**
- **Subscription**
  - Plan Details
    - API: `POST /api/StoredProcedure/GetSubscriptionDetails`
  - Resource Limits
    - API: `POST /api/StoredProcedure/GetCompanyResourceLimits`
- **Company Vault**
  - Vault Configuration
    - API: `POST /api/StoredProcedure/UpdateCompanyVault`
    - Body: `{"companyVault": "{...}", "vaultVersion": 1}`
  - Version Management

## 4. User Interface Components

### 4.1 Common Components

All UI components must be built using Ant Design components. No custom UI components should be created unless absolutely necessary.

#### **Resource List View**
```
┌─────────────────────────────────────────────────┐
│ [Resource Type] List                            │
│ ┌───────────────────┐ ┌──────────┐ ┌─────────┐ │
│ │ Search/Filter     │ │ + Create │ │ Actions │ │
│ └───────────────────┘ └──────────┘ └─────────┘ │
│ ┌─────────────────────────────────────────────┐ │
│ │ Name    │ Status │ Details │ Actions        │ │
│ ├─────────┼────────┼─────────┼────────────────┤ │
│ │ Item 1  │ Active │ ...     │ [▼][✏][🗑]    │ │
│ │ Item 2  │ Active │ ...     │ [▼][✏][🗑]    │ │
│ └─────────────────────────────────────────────┘ │
│ [Pagination Controls]                           │
└─────────────────────────────────────────────────┘
```

- Container: Ant Design Card
- Search/Filter: Ant Design Input.Search and Select
- Create Button: Ant Design Button with "primary" type
- Data Display: Ant Design Table with pagination
- Row Actions: Ant Design Button.Group or Dropdown
- Loading State: Ant Design Spin
- Empty State: Ant Design Empty

**API Endpoints for List Views:**
- Teams: `POST /api/StoredProcedure/GetCompanyTeams`
- Regions: `POST /api/StoredProcedure/GetCompanyRegions`
- Bridges: `POST /api/StoredProcedure/GetRegionBridges` (Body: `{"regionName": "region"}`)
- Machines: `POST /api/StoredProcedure/GetTeamMachines` (Body: `{"teamName": "team"}`)
- Repositories: `POST /api/StoredProcedure/GetTeamRepositories` (Body: `{"teamName": "team"}`)
- Storage: `POST /api/StoredProcedure/GetTeamStorages` (Body: `{"teamName": "team"}`)
- Schedules: `POST /api/StoredProcedure/GetTeamSchedules` (Body: `{"teamName": "team"}`)
- Users: `POST /api/StoredProcedure/GetCompanyUsers`
- Queue Items: `POST /api/StoredProcedure/GetTeamQueueItems` (Body: `{"teamName": "team"}`)

#### **Resource Detail View**
```
┌─────────────────────────────────────────────────┐
│ [Resource Name]                                 │
│ ┌─────────────────┬─────────────────────────┐  │
│ │ Info Panel      │ Actions Panel           │  │
│ │                 │ [Edit] [Delete]         │  │
│ │ Key: Value      │ [Vault Config]          │  │
│ │ Key: Value      │ [Additional Actions]    │  │
│ └─────────────────┴─────────────────────────┘  │
│ ┌─────────────────────────────────────────────┐ │
│ │ Related Resources Tab                       │ │
│ │ [Tab 1] [Tab 2] [Tab 3]                    │ │
│ │ Tab Content Area                           │ │
│ └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

- Container: Ant Design Card with tabs
- Info Display: Ant Design Descriptions
- Actions: Ant Design Button components
- Related Resources: Ant Design Tabs with embedded Tables
- Confirmation Dialogs: Ant Design Modal.confirm

**API Endpoints for Detail Views:**
- Team Members: `POST /api/StoredProcedure/GetTeamMembers` (Body: `{"teamName": "team"}`)
- Delete Actions:
  - Team: `POST /api/StoredProcedure/DeleteTeam`
  - Machine: `POST /api/StoredProcedure/DeleteMachine`
  - Bridge: `POST /api/StoredProcedure/DeleteBridge`
  - Region: `POST /api/StoredProcedure/DeleteRegion`
  - Repository: `POST /api/StoredProcedure/DeleteRepository`
  - Storage: `POST /api/StoredProcedure/DeleteStorage`
  - Schedule: `POST /api/StoredProcedure/DeleteSchedule`

### 4.2 Form Components

All forms must use React Hook Form with Ant Design Form components for consistent styling. Validation must be implemented using Zod schemas.

#### **Standard Creation Form**
```
┌─────────────────────────────────────────────────┐
│ Create [Resource Type]                          │
│ ┌─────────────────────────────────────────────┐ │
│ │ Basic Information                           │ │
│ │ ┌─────────────────────────────────────┐     │ │
│ │ │ Field Label *                       │     │ │
│ │ │ [Input Field                      ] │     │ │
│ │ └─────────────────────────────────────┘     │ │
│ │ ┌─────────────────────────────────────┐     │ │
│ │ │ Dropdown Label                     │     │ │
│ │ │ [Select Option              ▼]     │     │ │
│ │ └─────────────────────────────────────┘     │ │
│ └─────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────┐ │
│ │ Advanced Configuration (Optional)           │ │
│ │ [▼ Expand]                                 │ │
│ └─────────────────────────────────────────────┘ │
│ [Cancel] [Create]                               │
└─────────────────────────────────────────────────┘
```

- Form Container: Ant Design Form with React Hook Form Controller
- Input Fields: Ant Design Input
- Dropdowns: Ant Design Select with search enabled
- Advanced Options: Ant Design Collapse
- Submit Buttons: Ant Design Button with loading state
- Validation Errors: Ant Design Form.Item error display

**Dropdown Population:**
All dropdowns in forms are populated using the `GetDropdownValues` endpoint, which returns permission-aware options for the current user. This single API call provides all necessary dropdown data, improving performance and consistency. Results must be cached using React Query.

#### **Vault Configuration Modal**
```
┌─────────────────────────────────────────────────┐
│ Configure Vault                                 │
│ ┌─────────────────────────────────────────────┐ │
│ │ JSON Editor                                 │ │
│ │ {                                           │ │
│ │   "key": "value",                          │ │
│ │   ...                                       │ │
│ │ }                                           │ │
│ └─────────────────────────────────────────────┘ │
│ Version: [1] □ Auto-increment                   │
│ [Validate] [Cancel] [Save]                      │
└─────────────────────────────────────────────────┘
```

- Modal: Ant Design Modal
- JSON Editor: Monaco Editor component
- Version Control: Ant Design InputNumber
- Validation: Real-time JSON validation with error display
- Actions: Ant Design Button.Group

**Vault Update API Endpoints:**
- Team: `POST /api/StoredProcedure/UpdateTeamVault`
  - Body: `{"teamName": "name", "teamVault": "{...}", "vaultVersion": 1}`
- Machine: `POST /api/StoredProcedure/UpdateMachineVault`
  - Body: `{"teamName": "team", "machineName": "name", "machineVault": "{...}", "vaultVersion": 1}`
- Region: `POST /api/StoredProcedure/UpdateRegionVault`
  - Body: `{"regionName": "name", "regionVault": "{...}", "vaultVersion": 1}`
- Bridge: `POST /api/StoredProcedure/UpdateBridgeVault`
  - Body: `{"regionName": "region", "bridgeName": "name", "bridgeVault": "{...}", "vaultVersion": 1}`
- Company: `POST /api/StoredProcedure/UpdateCompanyVault`
  - Body: `{"companyVault": "{...}", "vaultVersion": 1}`
- Repository: `POST /api/StoredProcedure/UpdateRepositoryVault`
  - Body: `{"teamName": "team", "repoName": "name", "repoVault": "{...}", "vaultVersion": 1}`
- Storage: `POST /api/StoredProcedure/UpdateStorageVault`
  - Body: `{"teamName": "team", "storageName": "name", "storageVault": "{...}", "vaultVersion": 1}`
- Schedule: `POST /api/StoredProcedure/UpdateScheduleVault`
  - Body: `{"teamName": "team", "scheduleName": "name", "scheduleVault": "{...}", "vaultVersion": 1}`

### 4.3 Queue Management Interface

#### **Queue Function Browser**
```
┌─────────────────────────────────────────────────┐
│ Available Queue Functions                       │
│ ┌─────────────────────────────────────────────┐ │
│ │ [Search Functions]                          │ │
│ └─────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────┐ │
│ │ ▼ System Functions                          │ │
│ │   ○ os_setup - Setup operating system      │ │
│ │   ○ hello - Simple test function           │ │
│ │ ▼ Repository Functions                      │ │
│ │   ○ repo_new - Create new repository       │ │
│ │   ○ repo_mount - Mount repository          │ │
│ └─────────────────────────────────────────────┘ │
│ Selected: [Function Name]                       │
│ [Configure & Add to Queue]                      │
└─────────────────────────────────────────────────┘
```

- Container: Ant Design Card
- Search: Ant Design Input.Search
- Function List: Ant Design Tree or Collapse
- Selection: Radio buttons for single selection
- Details Display: Ant Design Descriptions

#### **Queue Function Configuration**
```
┌─────────────────────────────────────────────────┐
│ Configure: [Function Name]                      │
│ Description: [Function description]             │
│ ┌─────────────────────────────────────────────┐ │
│ │ Parameters                                  │ │
│ │ ┌─────────────────────────────────────┐     │ │
│ │ │ repo * (Repository name)            │     │ │
│ │ │ [Input Field                      ] │     │ │
│ │ └─────────────────────────────────────┘     │ │
│ │ ┌─────────────────────────────────────┐     │ │
│ │ │ size (optional - default: 10G)     │     │ │
│ │ │ [Input Field                      ] │     │ │
│ │ └─────────────────────────────────────┘     │ │
│ └─────────────────────────────────────────────┘ │
│ Target Machine: [Select Machine ▼]              │
│ Target Bridge: [Auto-populated from Machine]    │
│ Priority: [1-10 slider]                         │
│ [Cancel] [Add to Queue]                         │
└─────────────────────────────────────────────────┘
```

- Form: Ant Design Form with dynamic fields
- Parameter Inputs: Ant Design Input/Select based on type
- Machine Selection: Ant Design Select with grouping by team
- Bridge Display: Ant Design Input (disabled, auto-populated)
- Priority: Ant Design Slider
- Submit: Ant Design Button with loading state

**Note:** The bridge is automatically determined based on the selected machine's assignment and is passed as a required parameter to the API.

**Queue Vault Structure:**
```json
{
  "type": "bash_function",
  "function": "function_name",
  "params": {
    "param1": "value1",
    "param2": "value2"
  },
  "description": "User-provided description",
  "priority": 5,
  "bridge": "bridge_name"
}
```

**Available Functions:** os_setup, hello, uninstall, repo_new, repo_mount, repo_unmount, repo_up, repo_down, repo_resize, repo_rm, repo_plugin, repo_plugout, repo_ownership, repo_list, repo_push, repo_pull, map_socket

## 5. User Interaction Flows

### 5.1 Authentication Flow

```
Start → Login Screen → Enter Credentials → Validate
         ↓                                    ↓
         ↓                              Success/Fail
         ↓                                    ↓
    Session Storage ← Dashboard ← Load User Context
                                        ↓
                                 Load Dropdown Values
```

Authentication must use Axios interceptors to handle token rotation automatically. React Query must be configured to handle authentication state.

**API Calls:**
- Login: `POST /api/StoredProcedure/CreateAuthenticationRequest`
  - Headers: `Rediacc-UserEmail`, `Rediacc-UserHash`
  - Body: `{"name": "session_name"}`
- Get Company: `POST /api/StoredProcedure/GetUserCompany`
  - Headers: `Rediacc-UserEmail`, `Rediacc-UserHash`
- Get Dropdown Values: `POST /api/StoredProcedure/GetDropdownValues`
  - Headers: `Rediacc-RequestToken`
  - Body: `{}`
- Logout: `POST /api/StoredProcedure/DeleteUserRequest`
  - Headers: `Rediacc-RequestToken`

### 5.2 Resource Creation Flow

```
Resource List → Click Create → Load Dropdown Data
                                   ↓
                               Fill Form → Validate
                                   ↓
                            Optional Vault Config
                                   ↓
                              Submit Form
                                   ↓
                         Success: Show in List
                         Failure: Show Errors
```

Forms must use React Hook Form with Zod validation. Success/error feedback must use React Hot Toast.

**API Calls by Resource Type:**
- Team: `POST /api/StoredProcedure/CreateTeam`
  - Body: `{"teamName": "name", "teamVault": "{}"}`
- Region: `POST /api/StoredProcedure/CreateRegion`
  - Body: `{"regionName": "name", "regionVault": "{}"}`
- Bridge: `POST /api/StoredProcedure/CreateBridge`
  - Body: `{"regionName": "region", "bridgeName": "name", "bridgeVault": "{}"}`
- Machine: `POST /api/StoredProcedure/CreateMachine`
  - Body: `{"teamName": "team", "bridgeName": "bridge", "machineName": "name", "machineVault": "{}"}`
- Repository: `POST /api/StoredProcedure/CreateRepository`
  - Body: `{"teamName": "team", "repoName": "name", "repoVault": "{}"}`
- Storage: `POST /api/StoredProcedure/CreateStorage`
  - Body: `{"teamName": "team", "storageName": "name", "storageVault": "{}"}`
- Schedule: `POST /api/StoredProcedure/CreateSchedule`
  - Body: `{"teamName": "team", "scheduleName": "name", "scheduleVault": "{}"}`

### 5.3 Queue Operation Flow

```
Queue Dashboard → Add Function → Browse Functions
                                      ↓
                              Select Function
                                      ↓
                           Configure Parameters
                                      ↓
                            Select Machine
                                      ↓
                           Submit to Queue
                                      ↓
                        Monitor in Dashboard
```

Queue operations must use React Query's mutation hooks with optimistic updates for better UX.

**API Calls:**
- Create Queue Item: `POST /api/StoredProcedure/CreateQueueItem`
  - Body: `{"teamName": "team", "machineName": "machine", "bridgeName": "bridge", "queueVault": "{...}"}`
- Get Queue Items: `POST /api/StoredProcedure/GetQueueItemsNext`
  - Body: `{"machineName": "machine", "itemCount": 5}`
- Update Response: `POST /api/StoredProcedure/UpdateQueueItemResponse`
  - Body: `{"taskId": "id", "responseVault": "{}"}`
- Complete Item: `POST /api/StoredProcedure/UpdateQueueItemToCompleted`
  - Body: `{"taskId": "id", "finalVault": "{}"}`

## 6. State Management Strategy

### 6.1 Redux Toolkit Structure

The application must use Redux Toolkit with the following slice organization:

```
store/
├── auth/
│   ├── authSlice.ts
│   └── authSelectors.ts
├── resources/
│   ├── teamsSlice.ts
│   ├── regionsSlice.ts
│   ├── bridgesSlice.ts
│   ├── machinesSlice.ts
│   ├── repositoriesSlice.ts
│   ├── storageSlice.ts
│   └── schedulesSlice.ts
├── queue/
│   └── queueSlice.ts
├── ui/
│   └── uiSlice.ts
└── store.ts
```

### 6.2 React Query Integration

React Query must handle all server state with the following configuration:
- Stale time: 5 minutes for resource lists
- Cache time: 10 minutes
- Refetch on window focus: enabled for queue items only
- Query key factory pattern for consistent keys

### 6.3 Application State Structure

```
AppState (Redux)
├── Authentication
│   ├── isAuthenticated
│   ├── user
│   ├── token
│   └── company
├── UI
│   ├── activeView
│   ├── selectedResource
│   ├── filters
│   └── modals
└── Notifications[]

ServerState (React Query)
├── Resources
│   ├── teams
│   ├── regions
│   ├── bridges
│   ├── machines
│   ├── repositories
│   ├── storage
│   └── schedules
├── Queue
│   ├── items
│   └── functions
└── Dropdown Data
    ├── cached values
    └── last fetch time
```

### 6.4 Data Flow Patterns

#### **Initial App Load**
1. User authenticates (Redux action)
2. Load company information (React Query)
3. Fetch dropdown values (React Query with 30min cache)
4. Navigate to dashboard (React Router)

#### **List Views**
1. Component mounts → React Query hook fetches data
2. Display Ant Design Spin while loading
3. Render Ant Design Table with data
4. Handle pagination/filtering locally when possible
5. Refetch on CRUD operations using React Query invalidation

#### **Form Submissions**
1. React Hook Form handles form state
2. Zod validates on change/submit
3. React Query mutation on submit
4. Show Ant Design Spin on submit button
5. Success: Invalidate queries + React Hot Toast
6. Error: Show field errors or toast

#### **Dropdown Data Management**
1. Fetch once on app load using React Query
2. Store with 30-minute stale time
3. Invalidate and refetch after resource CRUD operations
4. Provide via React Query hooks to all forms
5. Filter client-side based on user selections

## 7. Advanced Features

### 7.1 Bulk Operations

Implementation using Ant Design Table rowSelection:
- Multi-select checkbox column
- Bulk actions in table toolbar
- Ant Design Modal for confirmation
- Progress tracking with Ant Design Progress
- Batch API calls with React Query mutations

### 7.2 Real-time Updates

Optional WebSocket integration for:
- Queue status updates (badge on menu item)
- Machine status monitoring (status column in table)
- Active session tracking (update user count)
- Resource change notifications (React Hot Toast)

### 7.3 Search and Filtering

Using Ant Design components:
- Global search in header (Input.Search)
- Column filters in tables (built-in Table filters)
- Advanced filter drawer (Drawer with Form)
- Saved filters in localStorage
- Quick filters as Tags

### 7.4 Keyboard Navigation

Implement using native React and Ant Design features:
- Ant Design Modal escape handling
- Form submit on enter (React Hook Form)
- Table keyboard navigation (built-in)
- Menu keyboard navigation (built-in)
- Custom hotkeys via useEffect hooks

### 7.5 Smart Dropdowns

Enhance Ant Design Select components with:
- Built-in search functionality
- Option grouping (OptGroup)
- Custom option rendering with metadata
- Virtual scrolling for large lists
- Loading state while fetching

## 8. Error Handling and Feedback

### 8.1 Error States

All error handling through consistent patterns:
- **Form Validation**: Ant Design Form.Item error messages
- **API Errors**: React Hot Toast notifications
- **Network Errors**: React Query retry with Ant Design Alert
- **Permission Errors**: Ant Design Modal.error

### 8.2 Success Feedback

Consistent success patterns:
- **Creation Success**: React Hot Toast + redirect
- **Update Success**: React Hot Toast + UI update
- **Deletion Success**: React Hot Toast + remove from list
- **Queue Success**: Ant Design Badge update

### 8.3 Loading States

Use Ant Design loading components:
- **Page Loading**: Ant Design Spin (centered)
- **Button Loading**: Button loading prop
- **Table Loading**: Table loading prop
- **Lazy Loading**: React.lazy with Spin

## 9. Responsive Design Considerations

### 9.1 Layout Adaptations

Using Ant Design Grid and responsive utilities:
- **Desktop**: Fixed sidebar + content (Ant Design Layout)
- **Tablet**: Collapsible sidebar (Layout.Sider collapsible)
- **Mobile**: Bottom tab navigation (Ant Design Tabs)

### 9.2 Component Adaptations

Ant Design responsive features:
- **Tables**: Scroll on mobile (scroll={{ x: true }})
- **Forms**: Single column on mobile (Col span)
- **Modals**: Full screen on mobile (custom CSS)
- **Menus**: Drawer on mobile instead of sidebar

## 10. Security and Permissions

### 10.1 UI Adaptations

Permission handling via Redux selectors:
- Disable unauthorized Ant Design Buttons
- Hide menu items based on permissions
- Show permission messages in Empty components
- Conditional rendering based on user role

### 10.2 Session Management

Implemented with Redux and Axios interceptors:
- Token rotation on each request
- Auto-logout on 401 responses
- Session timeout warnings (Ant Design Modal)
- Multi-session detection and handling

## 11. API Endpoint Reference

### 11.1 Authentication Endpoints

All endpoints use base URL: `/api/StoredProcedure/[endpoint]`

| Operation | Endpoint | Headers | Body |
|-----------|----------|---------|------|
| Login | `CreateAuthenticationRequest` | `Rediacc-UserEmail`, `Rediacc-UserHash` | `{"name": "session_name"}` |
| Logout | `DeleteUserRequest` | `Rediacc-RequestToken` | `{}` |
| Get Company | `GetUserCompany` | `Rediacc-UserEmail`, `Rediacc-UserHash` | `{}` |

### 11.2 Resource Management Endpoints

All authenticated endpoints require `Rediacc-RequestToken` header.

#### **List Operations**
| Resource | Endpoint | Body |
|----------|----------|------|
| Teams | `GetCompanyTeams` | `{}` |
| Regions | `GetCompanyRegions` | `{}` |
| Bridges | `GetRegionBridges` | `{"regionName": "region"}` |
| Machines | `GetTeamMachines` | `{"teamName": "team"}` |
| Repositories | `GetTeamRepositories` | `{"teamName": "team"}` |
| Storage | `GetTeamStorages` | `{"teamName": "team"}` |
| Schedules | `GetTeamSchedules` | `{"teamName": "team"}` |
| Users | `GetCompanyUsers` | `{}` |
| Sessions | `GetUserRequests` | `{}` |
| Resource Limits | `GetCompanyResourceLimits` | `{}` |
| Subscription | `GetSubscriptionDetails` | `{}` |
| **Dropdown Values** | **`GetDropdownValues`** | **`{}`** or **`{"context": "optional_context"}`** |

#### **Create Operations**
| Resource | Endpoint | Body |
|----------|----------|------|
| Company | `CreateNewCompany` | `{"companyName": "name", "subscriptionPlan": "ELITE"}` |
| User | `CreateNewUser` | `{"newUserEmail": "email", "newUserHash": "0x..."}` |
| Team | `CreateTeam` | `{"teamName": "name", "teamVault": "{}"}` |
| Region | `CreateRegion` | `{"regionName": "name", "regionVault": "{}"}` |
| Bridge | `CreateBridge` | `{"regionName": "region", "bridgeName": "name", "bridgeVault": "{}"}` |
| Machine | `CreateMachine` | `{"teamName": "team", "bridgeName": "bridge", "machineName": "name", "machineVault": "{}"}` |
| Repository | `CreateRepository` | `{"teamName": "team", "repoName": "name", "repoVault": "{}"}` |
| Storage | `CreateStorage` | `{"teamName": "team", "storageName": "name", "storageVault": "{}"}` |
| Schedule | `CreateSchedule` | `{"teamName": "team", "scheduleName": "name", "scheduleVault": "{}"}` |

#### **Update Operations**
| Resource | Endpoint | Body |
|----------|----------|------|
| Team Name | `UpdateTeamName` | `{"currentTeamName": "old", "newTeamName": "new"}` |
| Region Name | `UpdateRegionName` | `{"currentRegionName": "old", "newRegionName": "new"}` |
| Bridge Name | `UpdateBridgeName` | `{"regionName": "region", "currentBridgeName": "old", "newBridgeName": "new"}` |
| Machine Name | `UpdateMachineName` | `{"teamName": "team", "currentMachineName": "old", "newMachineName": "new"}` |
| Machine Bridge | `UpdateMachineAssignedBridge` | `{"teamName": "team", "machineName": "name", "newBridgeName": "bridge"}` |
| Repository Name | `UpdateRepositoryName` | `{"teamName": "team", "currentRepoName": "old", "newRepoName": "new"}` |
| Storage Name | `UpdateStorageName` | `{"teamName": "team", "currentStorageName": "old", "newStorageName": "new"}` |
| Schedule Name | `UpdateScheduleName` | `{"teamName": "team", "currentScheduleName": "old", "newScheduleName": "new"}` |

#### **Delete Operations**
| Resource | Endpoint | Body |
|----------|----------|------|
| Team | `DeleteTeam` | `{"teamName": "name"}` |
| Region | `DeleteRegion` | `{"regionName": "name"}` |
| Bridge | `DeleteBridge` | `{"regionName": "region", "bridgeName": "name"}` |
| Machine | `DeleteMachine` | `{"teamName": "team", "machineName": "name"}` |
| Repository | `DeleteRepository` | `{"teamName": "team", "repoName": "name"}` |
| Storage | `DeleteStorage` | `{"teamName": "team", "storageName": "name"}` |
| Schedule | `DeleteSchedule` | `{"teamName": "team", "scheduleName": "name"}` |

### 11.3 User Management Endpoints

| Operation | Endpoint | Headers/Body |
|-----------|----------|--------------|
| Activate User | `ActivateUserAccount` | No auth required. Body: `{"userEmail": "email", "activationCode": "111111"}` |
| Deactivate User | `UpdateUserToDeactivated` | Body: `{"userEmail": "email"}` |
| Update Email | `UpdateUserEmail` | Body: `{"currentUserEmail": "old", "newUserEmail": "new"}` |
| Update Password | `UpdateUserPassword` | Body: `{"userNewPass": "0x..."}` |

### 11.4 Team Membership Endpoints

| Operation | Endpoint | Body |
|-----------|----------|------|
| Add Member | `CreateTeamMembership` | `{"teamName": "team", "newUserEmail": "email"}` |
| Remove Member | `DeleteUserFromTeam` | `{"teamName": "team", "removeUserEmail": "email"}` |
| List Members | `GetTeamMembers` | `{"teamName": "team"}` |

### 11.5 Permission Management Endpoints

| Operation | Endpoint | Body |
|-----------|----------|------|
| Create Group | `CreatePermissionGroup` | `{"permissionGroupName": "name"}` |
| Delete Group | `DeletePermissionGroup` | `{"permissionGroupName": "name"}` |
| Add Permission | `CreatePermissionInGroup` | `{"permissionGroupName": "group", "permissionName": "permission"}` |
| Remove Permission | `DeletePermissionFromGroup` | `{"permissionGroupName": "group", "permissionName": "permission"}` |
| Assign to User | `UpdateUserAssignedPermissions` | `{"userEmail": "email", "permissionGroupName": "group"}` |
| List Groups | `GetCompanyPermissionGroups` | `{}` |
| Get Group Details | `GetPermissionGroupDetails` | `{"permissionGroupName": "name"}` |

### 11.6 Queue Management Endpoints

| Operation | Endpoint | Body |
|-----------|----------|------|
| Create Queue Item | `CreateQueueItem` | `{"teamName": "team", "machineName": "machine", "bridgeName": "bridge", "queueVault": "{...}"}` |
| Get Next Items | `GetQueueItemsNext` | `{"machineName": "machine", "itemCount": 5}` |
| Update Response | `UpdateQueueItemResponse` | `{"taskId": "id", "responseVault": "{}"}` |
| Complete Item | `UpdateQueueItemToCompleted` | `{"taskId": "id", "finalVault": "{}"}` |
| List Team Items | `GetTeamQueueItems` | `{"teamName": "team"}` |
| Delete Item | `DeleteQueueItem` | `{"taskId": "id"}` |

**Important Notes for Queue Creation:**
- The `bridgeName` parameter is now required when creating queue items
- The API validates that the specified machine is actually assigned to the specified bridge
- If the machine is not assigned to the bridge, the API returns error code 6

### 11.7 Response Handling

All API responses follow this structure:
```json
{
  "failure": 0,  // 0 for success, non-zero for error
  "errors": [],  // Array of error messages if failure != 0
  "message": "", // Success or error message
  "tables": [    // Array of data tables
    {
      "data": [
        {
          "nextRequestCredential": "token", // New auth token (table 0)
          // ... other fields
        }
      ]
    }
  ]
}
```

**Important Notes:**
- All endpoints use POST method
- Authentication token must be updated after each request (token chaining)
- Table index 0 contains authentication credentials
- Actual data typically starts at table index 1
- All timestamps are in ISO format
- Vault data must be valid JSON strings

### 11.8 Dropdown Values Response Structure

The `GetDropdownValues` endpoint returns a comprehensive JSON structure containing all dropdown options filtered by user permissions:

```json
{
  "teams": [{"value": "name", "label": "name"}],
  "allTeams": [{"value": "name", "label": "name", "memberCount": 5}],
  "regions": [{"value": "name", "label": "name", "bridgeCount": 3}],
  "bridgesByRegion": [{
    "regionName": "region",
    "bridges": [{"value": "name", "label": "name", "machineCount": 2}]
  }],
  "machinesByTeam": [{
    "teamName": "team",
    "machines": [{
      "value": "name",
      "label": "name",
      "bridgeName": "bridge",
      "regionName": "region"
    }]
  }],
  "users": [{"value": "email", "label": "email", "status": "active"}],
  "permissionGroups": [{
    "value": "name",
    "label": "name",
    "userCount": 10,
    "permissionCount": 5
  }],
  "queueFunctions": [{
    "category": "Repository Functions",
    "functions": [{
      "value": "repo_new",
      "label": "Create Repository",
      "description": "Create new repository"
    }]
  }],
  "subscriptionPlans": [{
    "value": "ELITE",
    "label": "Elite",
    "description": "Enterprise tier with unlimited access"
  }],
  "requestContext": "optional_context",
  "currentUser": "user@example.com",
  "userRole": "admin|user"
}
```

## 12. API Integration Guidelines

### 12.1 Axios Configuration

Central Axios instance with:
- Base URL configuration
- Request interceptor for auth headers
- Response interceptor for token rotation
- Error interceptor for consistent handling

### 12.2 React Query Patterns

Consistent query/mutation patterns:
- Query key factories for resources
- Mutation with optimistic updates
- Error boundary integration
- Invalidation strategies

### 12.3 Type Safety

Full TypeScript coverage:
- API response types generated from docs
- Zod schemas for runtime validation
- Type-safe React Query hooks
- Strict mode enabled

## 13. Development Guidelines

### 13.1 Component Structure

Follow consistent patterns:
- Functional components only
- Custom hooks for business logic
- Ant Design components for all UI
- CSS modules only when necessary

### 13.2 File Organization

```
src/
├── api/
│   ├── client.ts
│   ├── queries/
│   └── mutations/
├── components/
│   ├── common/
│   ├── forms/
│   └── layouts/
├── features/
│   ├── auth/
│   ├── resources/
│   └── queue/
├── hooks/
├── pages/
├── store/
├── types/
└── utils/
```

### 13.3 Best Practices

1. **No Custom UI Components**: Use Ant Design exclusively
2. **Consistent State Management**: Redux for client state, React Query for server state
3. **Type Safety**: Full TypeScript coverage with strict mode
4. **Form Handling**: Always use React Hook Form + Zod
5. **API Calls**: Always through Axios instance
6. **Error Handling**: Consistent patterns across the app
7. **Performance**: Lazy load routes, memoize expensive computations

### 13.4 Performance Guidelines

- Use React.lazy for route-based code splitting
- Implement virtual scrolling for large lists (Ant Design Table virtual)
- Memoize expensive computations with useMemo
- Optimize re-renders with React.memo
- Use React Query's stale-while-revalidate pattern

## 14. Testing Strategy

While not adding testing libraries to the package list, the architecture supports testing:
- Components designed for testability
- Pure functions in utils
- Centralized API layer
- Predictable state management

## 15. Deployment Considerations

Build configuration with Vite:
- Environment variables for API endpoints
- Production optimizations enabled
- Source maps for error tracking
- Asset optimization
- Proper CSP headers

---

This plan represents the complete technical specification for the Rediacc web application. Developers must adhere strictly to the specified technology stack and patterns outlined in this document. Any deviations or additional packages require explicit approval and documentation updates.