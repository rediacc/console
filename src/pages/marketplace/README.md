# Marketplace Feature

## Overview

The Marketplace feature provides an advanced template browsing and deployment experience for Rediacc users. It enhances the existing template system with better discovery, filtering, and deployment workflows.

## Features

### 1. Template Discovery
- **Grid and List Views**: Toggle between visual grid layout and detailed list view
- **Rich Template Cards**: Display template information with icons, tags, difficulty levels, and popularity
- **Featured and New Badges**: Highlight important or recently added templates
- **Search Functionality**: Full-text search across template names, descriptions, and tags

### 2. Advanced Filtering
- **Category Filter**: Filter by template categories (Databases, Web Apps, Monitoring, etc.)
- **Difficulty Level**: Filter by beginner, intermediate, or advanced templates
- **Tags**: Multi-select tag filtering for technologies and features
- **Popular Filters**: Quick toggles for common filters like "Production Ready" and "High Availability"

### 3. Team and Machine Selection
- **Pre-deployment Selection**: Choose team and machine before deploying templates
- **Smart Validation**: Deploy button is disabled until both team and machine are selected
- **Context Preservation**: Selected team/machine carries through to deployment

### 4. Template Preview
- **Detailed Modal**: View comprehensive template information before deployment
- **Multiple Tabs**:
  - Overview: Description, requirements, and features
  - Files: Browse all template files with syntax highlighting
  - Security: Best practices and security considerations
- **Resource Requirements**: Display CPU, memory, and storage requirements

### 5. Seamless Deployment
- **One-Click Deploy**: Navigate directly to repository creation with pre-selected template
- **Integration with Resources Page**: Automatically opens repository creation modal
- **Pre-filled Context**: Team, machine, and template are pre-selected

## Architecture

### Components

1. **MarketplacePage.tsx**
   - Main page component
   - Handles state management, filtering, and navigation
   - Fetches and enhances template data with marketplace metadata

2. **MarketplaceCard.tsx**
   - Reusable card component for template display
   - Supports both grid and list view modes
   - Shows template icon, title, description, tags, and actions

3. **MarketplaceFilters.tsx**
   - Sidebar component for filtering options
   - Category, difficulty, and tag filters
   - Clear all functionality

4. **MarketplacePreview.tsx**
   - Modal component for detailed template preview
   - Multi-tab interface with markdown support
   - Syntax highlighting for code files

### Data Flow

1. Templates are fetched from `/config/templates.json`
2. Enhanced with marketplace metadata (category, tags, difficulty, etc.)
3. Filtered based on user selections
4. Deployment navigates to Resources page with state:
   ```typescript
   {
     createRepository: true,
     selectedTemplate: templateName,
     selectedTeam: teamName,
     selectedMachine: machineName
   }
   ```

### Integration Points

1. **Navigation**: Added to main menu with shopping cart icon
2. **Resources Page**: Modified to handle navigation state from marketplace
3. **UnifiedResourceModal**: Updated to accept and display pre-selected templates
4. **Translations**: Full i18n support with marketplace namespace

## Template Metadata

Templates are automatically categorized and tagged based on their names and content:

- **Categories**: databases, quickstart, monitoring, caching, messaging, etc.
- **Difficulty Levels**: Determined by template complexity
- **Tags**: Extracted from template name and README content
- **Prerequisites**: Resource requirements (CPU, memory, storage)

## Future Enhancements

1. **Template Statistics**: Track actual deployment counts and success rates
2. **User Ratings**: Allow users to rate and review templates
3. **Custom Templates**: Support for user-contributed templates
4. **Template Versioning**: Track and display template versions
5. **Deployment History**: Show previous deployments of each template
6. **Advanced Search**: Filter by resource requirements, dependencies, etc.