# UI/UX Design Specifications

Design guidelines and component specifications for the Task Management SaaS application.

## Design System

### Colors

**Primary Palette:**
- Primary: `#3B82F6` (blue-500)
- Primary Dark: `#2563EB` (blue-600)
- Primary Light: `#60A5FA` (blue-400)

**Semantic Colors:**
- Success: `#10B981` (green-500)
- Warning: `#F59E0B` (amber-500)
- Error: `#EF4444` (red-500)
- Info: `#06B6D4` (cyan-500)

**Neutrals:**
- Background: `#F9FAFB` (gray-50)
- Surface: `#FFFFFF` (white)
- Border: `#E5E7EB` (gray-200)
- Text Primary: `#111827` (gray-900)
- Text Secondary: `#6B7280` (gray-500)

### Typography

**Font Family:**
- Primary: `Inter` (sans-serif)
- Monospace: `JetBrains Mono` (code)

**Type Scale:**
```css
.text-xs    { font-size: 0.75rem; }  /* 12px */
.text-sm    { font-size: 0.875rem; } /* 14px */
.text-base  { font-size: 1rem; }     /* 16px */
.text-lg    { font-size: 1.125rem; } /* 18px */
.text-xl    { font-size: 1.25rem; }  /* 20px */
.text-2xl   { font-size: 1.5rem; }   /* 24px */
.text-3xl   { font-size: 1.875rem; } /* 30px */
```

**Font Weights:**
- Regular: 400
- Medium: 500
- Semibold: 600
- Bold: 700

### Spacing

Use 4px base unit (Tailwind's spacing scale):
- 1 unit = 4px
- 2 units = 8px
- 3 units = 12px
- 4 units = 16px
- 6 units = 24px
- 8 units = 32px

## Layout Structure

### Navigation

**Top Navigation Bar:**
- Height: 64px (h-16)
- Background: White with bottom border
- Contents:
  - Logo (left)
  - Workspace selector (dropdown)
  - Search bar (center)
  - User menu (right)

**Sidebar Navigation:**
- Width: 256px (w-64)
- Background: Gray-50
- Collapsible on mobile
- Contents:
  - Workspace info
  - Navigation links
  - Project list
  - Settings link (bottom)

### Page Layout

```
┌─────────────────────────────────────────┐
│ Top Nav (64px)                          │
├───────────┬─────────────────────────────┤
│           │                             │
│  Sidebar  │  Main Content Area         │
│  (256px)  │                             │
│           │                             │
│           │                             │
└───────────┴─────────────────────────────┘
```

### Responsive Breakpoints

```
sm:  640px   (Mobile landscape)
md:  768px   (Tablet)
lg:  1024px  (Desktop)
xl:  1280px  (Large desktop)
2xl: 1536px  (Extra large)
```

**Mobile (<768px):**
- Sidebar collapses to hamburger menu
- Single column layouts
- Full-width cards

**Tablet (768px-1024px):**
- Sidebar shows/hides with toggle
- Two-column layouts where appropriate

**Desktop (>1024px):**
- Sidebar always visible
- Multi-column layouts
- Expanded spacing

## Core Components

### Button Variants

**Primary Button:**
```tsx
<button className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors">
  Create Task
</button>
```

**Secondary Button:**
```tsx
<button className="px-4 py-2 bg-gray-100 text-gray-900 rounded-lg hover:bg-gray-200 transition-colors">
  Cancel
</button>
```

**Danger Button:**
```tsx
<button className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors">
  Delete
</button>
```

### Form Inputs

**Text Input:**
```tsx
<input
  type="text"
  className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
  placeholder="Enter task title..."
/>
```

**Textarea:**
```tsx
<textarea
  className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
  rows={4}
  placeholder="Task description..."
/>
```

**Select Dropdown:**
```tsx
<select className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
  <option>Todo</option>
  <option>In Progress</option>
  <option>Done</option>
</select>
```

### Cards

**Standard Card:**
```tsx
<div className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm hover:shadow-md transition-shadow">
  {/* Card content */}
</div>
```

**Task Card:**
```tsx
<div className="bg-white border border-gray-200 rounded-lg p-4 hover:border-blue-300 cursor-pointer">
  <h3 className="font-semibold text-gray-900">Task Title</h3>
  <p className="text-sm text-gray-500 mt-1">Task description...</p>
  <div className="flex items-center justify-between mt-3">
    <div className="flex gap-2">
      <span className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded">Design</span>
    </div>
    <div className="flex items-center gap-2">
      <img src="avatar.jpg" className="w-6 h-6 rounded-full" />
    </div>
  </div>
</div>
```

### Modals

**Modal Structure:**
```tsx
<div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
  <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
    {/* Header */}
    <div className="flex items-center justify-between p-6 border-b border-gray-200">
      <h2 className="text-xl font-semibold">Modal Title</h2>
      <button className="text-gray-400 hover:text-gray-600">✕</button>
    </div>

    {/* Body */}
    <div className="p-6">
      {/* Modal content */}
    </div>

    {/* Footer */}
    <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-200">
      <button className="px-4 py-2 bg-gray-100 rounded-lg">Cancel</button>
      <button className="px-4 py-2 bg-blue-500 text-white rounded-lg">Save</button>
    </div>
  </div>
</div>
```

### Status Badges

**Task Status:**
```tsx
// Todo
<span className="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-700 rounded-full">
  Todo
</span>

// In Progress
<span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-700 rounded-full">
  In Progress
</span>

// Done
<span className="px-2 py-1 text-xs font-medium bg-green-100 text-green-700 rounded-full">
  Done
</span>
```

**Priority Badges:**
```tsx
// Low
<span className="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-600 rounded">
  Low
</span>

// Medium
<span className="px-2 py-1 text-xs font-medium bg-yellow-100 text-yellow-700 rounded">
  Medium
</span>

// High
<span className="px-2 py-1 text-xs font-medium bg-orange-100 text-orange-700 rounded">
  High
</span>

// Urgent
<span className="px-2 py-1 text-xs font-medium bg-red-100 text-red-700 rounded">
  Urgent
</span>
```

## Page Layouts

### Dashboard/Home

**Layout:**
- Workspace overview stats (cards grid)
- Recent activity feed
- Quick actions bar
- Active projects list

### Project View

**Kanban Board Layout:**
```
┌──────────┬──────────┬──────────┬──────────┐
│  Todo    │  In Prog │  Review  │  Done    │
├──────────┼──────────┼──────────┼──────────┤
│ [Task]   │ [Task]   │ [Task]   │ [Task]   │
│ [Task]   │ [Task]   │          │ [Task]   │
│ [Task]   │          │          │ [Task]   │
└──────────┴──────────┴──────────┴──────────┘
```

**List View Layout:**
- Filters and search bar (top)
- Table with columns: Title, Assignee, Status, Priority, Due Date
- Sortable columns
- Pagination (bottom)

### Task Detail

**Layout:**
- Title and description (top)
- Status, priority, assignee, due date (metadata row)
- Labels (tags)
- Comments section
- Attachments section
- Activity log (right sidebar)

## Interactive States

### Hover States
- Buttons: Darken background by 1 shade
- Cards: Add subtle shadow, change border color
- Links: Underline or color change

### Focus States
- All interactive elements: Blue ring (ring-2 ring-blue-500)
- Maintain high contrast for accessibility

### Loading States
- Skeleton screens for data loading
- Spinner for button actions
- Progress bar for file uploads

### Empty States
- Centered icon + message
- Primary action button
- Helpful tips or getting started guide

## Accessibility

**Requirements:**
- WCAG 2.1 AA compliance
- Keyboard navigation support (Tab, Enter, Escape)
- ARIA labels on all interactive elements
- Sufficient color contrast (4.5:1 for text)
- Focus indicators visible
- Error messages associated with form fields

**Example:**
```tsx
<button
  className="..."
  aria-label="Create new task"
  onClick={handleCreate}
>
  <PlusIcon aria-hidden="true" />
  <span>Create Task</span>
</button>
```

## Animation & Transitions

**Subtle Animations:**
- Transitions: `transition-colors`, `transition-shadow`, `transition-all`
- Duration: 150-300ms
- Easing: `ease-in-out`

**Examples:**
```css
.button {
  @apply transition-colors duration-200;
}

.card {
  @apply transition-shadow duration-300;
}

.modal {
  @apply transition-opacity duration-200;
}
```

**Avoid:**
- Overly long animations (>500ms)
- Animations on critical path
- Motion without purpose

## Dark Mode (Future Enhancement)

Not required for v1.0, but design with dark mode in mind:
- Use Tailwind's `dark:` variant classes
- Test color contrast in both modes
- Store user preference in database

---

**Implementation Notes:**
- Use Tailwind CSS for all styling
- Component library: Build custom components (no external UI library required)
- Icons: Use Heroicons (MIT license, React components)
- Responsive: Mobile-first approach
- Testing: Visual regression tests with Percy or Chromatic
