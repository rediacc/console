# Team Creation Test - Complete Selector Documentation

This document provides comprehensive documentation for all selectors and the complete team creation flow in the Rediacc console, based on thorough UI exploration.

## Test File Location
- **Main Test**: `/home/anl/monorepo/console/playwright/18_system_createteam.py`
- **Improved Version**: `/home/anl/monorepo/console/playwright/18_system_createteam_improved.py`

## Complete Flow Overview

The team creation process involves these main steps:
1. Login to the console
2. Navigate to System page
3. Switch to Teams tab
4. Open create team dialog
5. Fill team details
6. Generate SSH keys
7. Submit team creation
8. Verify success

## Detailed Selector Reference

### 1. Login Page Selectors

**Page Detection**:
- URL contains: `/login`, `signin`, or ends with `/console/`

**Input Fields**:
```python
# Email input - use placeholder selector (not type="email")
email_input = page.locator('input[placeholder*="email" i]').first
# Placeholder text: "Enter your work email address"

# Password input
password_input = page.locator('input[type="password"]').first
# Placeholder text: "Enter your password"

# Submit button
submit_button = page.locator('button[type="submit"]').first
# Button text: "Sign In"
```

**Success Indicator**:
- Redirects to: `**/console/dashboard`

### 2. System Page Navigation

**System Navigation Link**:
```python
system_nav = page.get_by_test_id("main-nav-system")
```
- Located in left sidebar
- Text content: "System"

### 3. Teams Tab

**Teams Tab Selector**:
```python
teams_tab = page.get_by_test_id("system-tab-teams")
```
- Located within the "Users, Teams & Permissions" section
- Tab text: "Teams"
- Active state indicated by Ant Design tab styling

### 4. Create Team Button

**Create Team Button**:
```python
create_team_button = page.get_by_test_id("system-create-team-button")
```
- Green circular button with "+" icon
- Located in top-right of teams section
- Opens team creation modal dialog

### 5. Team Creation Dialog

**Dialog Title**: "teams.createTeam in Private Team"

**Team Name Input**:
```python
team_name_input = page.get_by_test_id("resource-modal-field-teamName-input")
```
- Required field with red asterisk
- Placeholder: "Enter team name"
- Input type: text
- Form field name: "teamName"

### 6. Vault Configuration Section

**Section Title**: "Vault Configuration"
**Description**: "Team configuration for organizational structure"

**SSH Key Fields**:

**SSH Private Key Field**:
```python
ssh_private_key_input = page.get_by_test_id("vault-editor-field-SSH_PRIVATE_KEY")
```
- Input type: password
- Placeholder: "Base64 encoded private key. Example: LS0tLS1CRUdJTi0tLS0t"
- Required field (marked with red asterisk)

**SSH Public Key Field**:
```python
ssh_public_key_input = page.get_by_test_id("vault-editor-field-SSH_PUBLIC_KEY")
```
- Input type: text
- Placeholder: "Public SSH key. Example: ssh-rsa AAAAB3NzaC1yc2E... mykey"
- Required field (marked with red asterisk)

### 7. SSH Key Generation

**Generate SSH Private Key Button**:
```python
generate_ssh_button = page.get_by_test_id("vault-editor-generate-SSH_PRIVATE_KEY")
```
- Small icon button next to SSH Private Key field
- Opens SSH key generation dialog

**SSH Key Generation Dialog**:

**Generate Button in Dialog**:
```python
generate_button = page.locator('button:has-text("Generate")').first
```
- Green button with "Generate" text
- Generates both private and public key pair

**Key Generation Options**:
- **Key Type**: RSA (default), Ed25519 (coming soon)
- **Key Size**: 2048 bits (default), 4096 bits (more secure)

**Apply Generated Key**:
- Keys may be applied automatically after generation
- If manual apply needed:
```python
apply_button = page.locator('button:has-text("Generate value")').first
```

### 8. Dialog Actions

**Import/Export Buttons**:
```python
import_button = page.get_by_test_id("resource-modal-import-button")
export_button = page.get_by_test_id("resource-modal-export-button")
```
- Import: "Import JSON"
- Export: "Export JSON"

**Dialog Control Buttons**:
```python
cancel_button = page.get_by_test_id("resource-modal-cancel-button")
submit_button = page.get_by_test_id("resource-modal-ok-button")
```
- Cancel: "Cancel" (gray button)
- Submit: "Create" (green primary button)

### 9. Success Verification

**Team List Table**:
```python
team_rows = page.locator('.ant-table tbody tr')
```
- Teams appear in table format
- Columns: TEAM NAME, MEMB..., MACHI..., REPOSIT..., STORA..., SCHED..., ACTIONS

**Team Row Content Check**:
```python
for i in range(team_rows.count()):
    row = team_rows.nth(i)
    row_text = row.text_content()
    if team_name in row_text:
        # Team found in list
        break
```

**Success Messages** (if present):
```python
success_messages = page.locator('.ant-message-success, .ant-notification-notice-success')
```

## Complete Working Example

Here's the complete flow with all correct selectors:

```python
# 1. Login
email_input = page.locator('input[placeholder*="email" i]').first
email_input.fill("admin@rediacc.io")
password_input = page.locator('input[type="password"]').first
password_input.fill("admin")
submit_button = page.locator('button[type="submit"]').first
submit_button.click()

# 2. Navigate to System
page.wait_for_url("**/console/dashboard", timeout=15000)
system_nav = page.get_by_test_id("main-nav-system")
system_nav.click()

# 3. Switch to Teams tab
teams_tab = page.get_by_test_id("system-tab-teams")
teams_tab.click()

# 4. Open create team dialog
create_team_button = page.get_by_test_id("system-create-team-button")
create_team_button.click()

# 5. Fill team details
team_name_input = page.get_by_test_id("resource-modal-field-teamName-input")
team_name_input.fill("MyTestTeam")

# 6. Generate SSH key
generate_ssh_button = page.get_by_test_id("vault-editor-generate-SSH_PRIVATE_KEY")
generate_ssh_button.click()
generate_button = page.locator('button:has-text("Generate")').first
generate_button.click()

# 7. Submit
submit_button = page.get_by_test_id("resource-modal-ok-button")
submit_button.click()

# 8. Verify success
team_rows = page.locator('.ant-table tbody tr')
# Check if team appears in table...
```

## Key Findings from UI Exploration

1. **Login Form**: Uses placeholder-based selectors, not type-based
2. **Navigation**: All main navigation uses consistent `main-nav-*` test-ids
3. **Tabs**: System page tabs use `system-tab-*` pattern
4. **Buttons**: Action buttons use descriptive test-ids with resource type and action
5. **Form Fields**: Modal form fields use `resource-modal-field-*` pattern
6. **Vault Editor**: Vault-specific fields use `vault-editor-*` pattern
7. **SSH Generation**: Multi-step process with separate dialog
8. **Success Detection**: Team appears immediately in table after successful creation

## Error Indicators

**Required Field Validation**:
- Empty required fields show red border
- Warning messages appear below fields
- Submit button remains enabled but creation fails

**SSH Key Validation**:
- Both private and public keys are required
- Invalid key format shows error messages
- Generation process handles validation automatically

## Screenshots Captured During Testing

The test automatically captures screenshots at each step:
1. `01_initial_page.png` - Initial console page
2. `02_login_page.png` - Login form
3. `03_dashboard.png` - Dashboard after login
4. `04_system_page.png` - System page with Users tab active
5. `05_teams_tab.png` - Teams tab showing existing teams
6. `06_create_team_dialog.png` - Create team modal dialog
7. `07_team_name_filled.png` - Team name filled in
8. `08_ssh_generate_dialog.png` - SSH key generation options
9. `09_ssh_key_generated.png` - After key generation
10. `10_ready_to_submit.png` - Ready to submit form
11. `11_after_submission.png` - After clicking Create
12. `12_final_state.png` - Final teams list with new team

## Browser Configuration

**Optimal Settings**:
- Viewport: 1440x900 (desktop size)
- Slow motion: 500ms (for better visual verification)
- Headless: false (for debugging and verification)
- Default timeout: 30000ms

## Notes for Future Maintenance

1. **Test-ID Stability**: The application uses consistent test-id patterns that should remain stable
2. **Ant Design Components**: UI uses Ant Design, so fallback selectors can use `.ant-*` classes
3. **Form Validation**: The form provides good validation feedback for debugging
4. **SSH Key Generation**: The generation process is reliable and automatically fills both keys
5. **Success Verification**: Team creation success is best verified by checking the teams table

This documentation should provide everything needed to maintain and improve the team creation tests.