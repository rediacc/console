# @rediacc/formatters

Shared formatting utilities for Rediacc Console.

## Overview

This package provides platform-agnostic formatting functions that work across web (React) and CLI (Node.js) environments. Currently focused on time formatting, it serves as the foundation for future shared formatting utilities.

## Features

- Platform-agnostic time formatting
- TypeScript support with full type definitions
- Dual build (CommonJS + ESM)
- Zero dependencies

## Installation

```bash
npm install @rediacc/formatters
```

## Usage

### Format Age

Convert minutes to human-readable time format:

```typescript
import { formatAge } from '@rediacc/formatters'

// Less than an hour
console.log(formatAge(45))
// Output: "45m"

// Hours and minutes
console.log(formatAge(150))
// Output: "2h 30m"

// Days and hours
console.log(formatAge(1500))
// Output: "1d 1h"
```

### Format Rules

- **Less than 60 minutes**: Shows minutes only (e.g., "45m")
- **Less than 24 hours (1440 minutes)**: Shows hours and minutes (e.g., "2h 30m")
- **24 hours or more**: Shows days and hours (e.g., "1d 5h")

## API Reference

### `formatAge(minutes: number): string`

Formats a time duration in minutes to a human-readable string.

**Parameters:**
- `minutes` (number): The duration in minutes to format

**Returns:**
- `string`: Formatted time string

**Examples:**
```typescript
formatAge(30)    // "30m"
formatAge(90)    // "1h 30m"
formatAge(1440)  // "1d 0h"
formatAge(1500)  // "1d 1h"
```

## Use Cases

This package is used throughout the Rediacc Console for:
- Queue item age display
- Task duration formatting
- Time-since-last-update indicators

## Future Additions

This package will serve as the home for additional shared formatters:
- File size formatting
- Number formatting with localization
- Date/time formatting
- Currency formatting

## License

MIT
