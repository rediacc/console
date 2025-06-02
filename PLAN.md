# Rediacc Web Application Design Plan

## 1. Application Overview

### Purpose
Transform the Rediacc CLI into a web-based graphical interface that maintains all functionality while providing an intuitive user experience through visual menus, forms, and interactive components.

### Core Principles
- **Feature Parity**: Every CLI command must have a corresponding web interface
- **Progressive Disclosure**: Complex operations revealed through logical navigation
- **Context Awareness**: Interface adapts based on user permissions and resource state
- **Visual Feedback**: Clear indication of operations, progress, and results

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

## 3. Navigation Structure

### 3.1 Primary Navigation Menu

#### **Dashboard**
- Overview statistics
- Recent activities
- Quick actions

#### **Resources**
- **Teams**
  - List Teams
  - Create Team
  - Team Details (inspect/update/delete)
  - Team Members Management
- **Regions & Infrastructure**
  - **Regions**
    - List Regions
    - Create Region
    - Region Management
  - **Bridges**
    - List Bridges (filtered by region)
    - Create Bridge
    - Bridge Management
  - **Machines**
    - List Machines (filtered by team)
    - Create Machine
    - Machine Details
    - Machine Vault Configuration
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
  - Active Queue Items
  - Queue Statistics
- **Queue Operations**
  - Add Function to Queue
    - Select machine first to auto-populate bridge
    - Bridge is required but determined by machine assignment
  - Available Functions Browser
  - Queue Item Details
- **Machine Queues**
  - View by Machine
  - Batch Operations

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

**Dropdown Population:**
All dropdowns in forms are populated using the `GetDropdownValues` endpoint, which returns permission-aware options for the current user. This single API call provides all necessary dropdown data, improving performance and consistency.

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

### 6.1 Application State Structure

```
AppState
├── Authentication
│   ├── isAuthenticated
│   ├── user
│   ├── token
│   └── company
├── Resources
│   ├── teams[]
│   ├── regions[]
│   ├── bridges[]
│   ├── machines[]
│   ├── repositories[]
│   ├── storage[]
│   └── schedules[]
├── Queue
│   ├── items[]
│   ├── functions[]
│   └── activeOperations[]
├── UI
│   ├── activeView
│   ├── selectedResource
│   ├── filters
│   ├── modals
│   └── dropdownData
│       ├── teams[]
│       ├── regions[]
│       ├── bridgesByRegion{}
│       ├── machinesByTeam{}
│       ├── users[]
│       ├── permissionGroups[]
│       └── queueFunctions[]
└── Notifications[]
```

### 6.2 Data Flow Patterns

#### **Initial App Load**
1. User authenticates
2. Load company information
3. Fetch dropdown values
4. Cache dropdown data in state
5. Navigate to dashboard

#### **List Views**
1. Component mounts → Request data
2. Display loading state
3. Receive data → Update state
4. Render list with data
5. Handle user interactions

#### **Form Submissions**
1. User fills form → Local validation
2. Show validation errors if any
3. Submit to backend
4. Show progress indicator
5. Handle response (success/error)
6. Update relevant lists/views
7. Refresh dropdown data if needed

#### **Dropdown Data Management**
1. Fetch on app initialization
2. Cache in application state
3. Refresh on resource creation/deletion
4. Use cached data for all forms
5. Provide context-specific filtering

## 7. Advanced Features

### 7.1 Bulk Operations

- Multi-select in list views
- Batch actions dropdown
- Progress tracking for bulk operations
- Rollback capabilities

### 7.2 Real-time Updates

- Queue status updates
- Machine status monitoring
- Active session tracking
- Resource change notifications

### 7.3 Search and Filtering

- Global search across resources
- Advanced filters per resource type
- Saved filter presets
- Quick filters in navigation

### 7.4 Keyboard Navigation

- Hotkeys for common actions
- Tab navigation through forms
- Escape to close modals
- Enter to submit forms

### 7.5 Smart Dropdowns

- Type-ahead search in dropdowns
- Hierarchical display (bridges by region, machines by team)
- Permission-aware filtering
- Recently used items at top
- Metadata display (counts, status)

## 8. Error Handling and Feedback

### 8.1 Error States

- **Form Validation**: Inline field errors
- **API Errors**: Toast notifications
- **Network Errors**: Retry mechanisms
- **Permission Errors**: Clear messaging

### 8.2 Success Feedback

- **Creation Success**: Toast + redirect
- **Update Success**: Inline confirmation
- **Deletion Success**: List update animation
- **Queue Success**: Status indicator

## 9. Responsive Design Considerations

### 9.1 Layout Adaptations

- **Desktop**: Full sidebar + content
- **Tablet**: Collapsible sidebar
- **Mobile**: Bottom navigation + stacked layout

### 9.2 Component Adaptations

- Tables → Cards on mobile
- Multi-column forms → Single column
- Modals → Full-screen sheets
- Hover actions → Touch-friendly buttons

## 10. Security and Permissions

### 10.1 UI Adaptations

- Hide/disable unauthorized actions
- Role-based menu items
- Permission-aware forms
- Contextual help for permissions

### 10.2 Session Management

- Auto-logout on inactivity
- Session expiry warnings
- Token refresh handling
- Multi-session awareness

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