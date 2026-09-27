# UI kit

Shared presentation components. **Reuse these before writing a new one**, so light and dark mode, spacing and focus styles stay consistent. The colour and surface utilities they use (`text-ink`, `surface-2`, `tone-*`, `glass`, `field`, `label`...) are defined in [`src/index.css`](../../index.css).

```jsx
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
```

| Component | Props | Notes |
|---|---|---|
| `Button` | `variant`, `size`, `loading`, `as`, plus any button/link prop | `variant`: primary, secondary, success, danger, warning, ghost, indigo. `size`: sm, md, lg. `loading` shows a spinner and disables the button. `as={Link}` renders a router link |
| `Card` | `children`, `className`, `padded`, `interactive` | Glass panel used for page sections. `interactive` adds a hover lift |
| `Badge` | `variant`, `children`, `className` | `variant` is usually a status string from the API, e.g. `completed`, `failed`, `running`. Unknown values fall back to a neutral grey |
| `Toast` | `tone`, `children`, `onClose`, `className` | `tone`: success, warning, danger, info, neutral. Errors and warnings are announced by screen readers. `onClose` adds a dismiss button |
| `EmptyState` | `title`, `description`, `icon`, `children` | Shown when a list has no rows. `children` usually holds a Button |
| `PageHeader` | `title`, `description`, `eyebrow`, `actions` | Top of every page. `actions` holds buttons aligned to the right |
| `Skeleton` | `className` | Grey shimmer placeholder while data loads. Set the size with the class name, e.g. `h-4 w-32` |
| `Table` | `columns`, `children`, `className` | `columns` is an array of header labels; `children` are the `<tr>` rows |
| `ThemeToggle` | `className` | Light/dark switch, already placed in the navbar |

## Example

```jsx
<Card>
  <PageHeader title="Campaigns" description="Create focused outreach campaigns." />
  {isLoading ? <Skeleton className="h-24 w-full" /> : <CampaignList />}
  <Button variant="primary" loading={isSaving}>Save</Button>
</Card>
```

## Adding a component

Keep it presentational: no API calls and no page state. Use the utilities from `index.css` instead of fixed colours, so it works in both themes, and add a row to the table above.
