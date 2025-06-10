# Functions Structure Documentation

## Overview
Queue functions in the console app follow a centralized, translation-aware structure to avoid duplication and support internationalization.

## File Structure

### 1. Function Definitions (`functions.json`)
Contains the base structure and metadata for all functions without any translatable text:
- Function names and categories
- Parameter types, defaults, and validation rules
- No descriptions or help text (these are in translations)

### 2. Translation Service (`services/functionsService.ts`)
Provides hooks and utilities to merge function definitions with translations:
- `useLocalizedFunctions()` - React hook that returns localized function data
- `getFunctionsWithTranslations()` - Function for non-hook contexts

### 3. Translation Files (`i18n/locales/*/functions.json`)
Contains all translatable text for functions:
- Category names and descriptions
- Function descriptions
- Parameter labels and help text

## Usage Example

```typescript
import { useLocalizedFunctions } from '@/services/functionsService';

function MyComponent() {
  const { functions, categories, getFunction, getFunctionsByCategory } = useLocalizedFunctions();
  
  // Get all functions with translations
  const allFunctions = functions;
  
  // Get a specific function
  const osSetup = getFunction('os_setup');
  
  // Get functions by category
  const machineFunctions = getFunctionsByCategory('machine');
}
```

## Adding New Functions

1. Add the function definition to `functions.json`:
```json
{
  "my_function": {
    "name": "my_function",
    "category": "machine",
    "params": {
      "param1": {
        "type": "string",
        "required": true
      }
    }
  }
}
```

2. Add translations to `i18n/locales/en/functions.json`:
```json
{
  "functions": {
    "my_function": {
      "description": "Description of my function",
      "params": {
        "param1": {
          "label": "Parameter 1",
          "help": "Enter the first parameter"
        }
      }
    }
  }
}
```

3. Add translations to other language files as needed.

## Benefits
- Single source of truth for function structure
- Easy internationalization support
- Type-safe function definitions
- No duplication between data and translations
- Clear separation of concerns