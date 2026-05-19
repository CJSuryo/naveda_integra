# Unit-Scoped Filtering Design

**Date:** 2026-05-19  
**Status:** Approved  
**Scope:** Announcement, Broadcast, User Management (Staff/Parent tables)

## Problem

All users — including admins — must only see and interact with data belonging to their associated units/levels/classes. Currently:

- `/api/announcement` and `/api/broadcast` bypass scoping for `can_manage_user=true` users (wrong)
- `/api/users` has zero session-based scoping (shows all staff/parents)
- `/api/parents/search` has zero session-based scoping
- Create form dropdowns for announcement/broadcast show ALL units/levels/classes
- List page filter dropdowns show ALL units/levels/classes
- Staff/Parent table filter dropdowns show ALL units/levels/classes

## Constraints

- Every user, regardless of role, is always scoped to their associated units/levels/classes
- No super-admin bypass exists
- Parents cannot log in to the web app
- Session already carries `user.users[0].associations.{units[], levels[], classes[]}` on the client

## Approach

**API layer** (security): Enforce session-based scoping server-side on all affected endpoints.  
**UI layer** (UX): Derive dropdown options from session associations already on the client — no extra API calls.

---

## API Changes

### `/api/announcement/route.ts` and `/api/broadcast/route.ts`

**Remove** the `can_manage_user` bypass entirely. Both now always scope:

1. Get session → `user.users[0]`
2. Query `user_unit` table for user's associated unit IDs
3. Filter results where:
   - `unit_id IN (user's unit IDs)` OR
   - `level_id IN (user's level IDs)` OR
   - `class_id IN (user's class IDs)` OR
   - scope is global (all three NULL) OR
   - `created_by = current user ID`
4. Optional `unit/level/class` query params narrow within this scoped set

**Authorization check on POST (create):**
- If submitted `unit_id` is not in user's associated unit IDs → return `403 Forbidden` with message: `"You are not authorized to create content for this unit"`
- Same check for `level_id` and `class_id`

### `/api/users/route.ts`

Add session enforcement at the top of the GET handler:

1. Get session → if no session, return `401`
2. Query `user_unit` table for logged-in user's associated unit IDs
3. Inject those unit IDs as a mandatory scope filter
4. Optional `unit/level/class` query params from UI narrow within the scoped set (cannot expand beyond it)
5. Applies to both `type=staff` and `type=parent` queries

### `/api/parents/search/route.ts`

Add session enforcement:

1. Get session → if no session, return `401`
2. Get logged-in user's associated unit IDs
3. Scope parent results to parents whose children are in the logged-in user's associated units/levels/classes (via student → class → unit join)

---

## UI Changes

### Session associations shape (reference)

```ts
session.user.users[0].associations = {
  units: [{ unit_id, unit_name, is_primary }],
  levels: [{ lvl_id, lvl_name, unit_id, unit_name, is_primary }],
  classes: [{ cls_id, class_name, lvl_id, unit_id, lvl_name, unit_name, is_primary }]
}
```

All dropdown option derivation below uses this shape directly from `useSession()`.

### Announcement List + Broadcast List — filter dropdowns

Both contexts (`AnnouncementContext`, `BroadcastContext`) already call `useSession()`.

- **Unit select options**: `associations.units`
- **Level select options**: `associations.levels` filtered by selected unit (all user's levels if no unit selected)
- **Class select options**: `associations.classes` filtered by selected level
- **Auto-select**: if `associations.units.length === 1`, auto-select that unit on mount and cascade

### Announcement Create + Broadcast Create — form dropdowns

Replace existing API fetches for unit/level/class options with session data:

- **Unit select**: `associations.units` — removes API call on mount
- **Level select**: `associations.levels.filter(l => l.unit_id === selectedUnitId)` — removes API call
- **Class select**: `associations.classes.filter(c => c.lvl_id === selectedLevelId)` — removes API call
- **Auto-select**: if only one unit, pre-select and cascade immediately
- Keep existing "All levels" / "All classes" null option for broadcasting to entire unit/level
- On `403` response from POST: display error toast/alert with the returned message

### StaffTable + ParentTable — filter dropdowns

Both are client components and can call `useSession()` directly.

- **Unit/level/class filter dropdowns**: derive options from `associations` (same pattern as above)
- **On mount**: if `associations.units.length === 1`, auto-apply that unit filter so table loads pre-scoped
- API already enforces scope (Section above), so UI reflects what the API will return

---

## Edge Cases

| Case | Behavior |
|------|----------|
| User has no associations | APIs return empty results; dropdowns show empty with "No units assigned" message; no 500 |
| User has multiple units | Dropdowns show all associated units/levels/classes; no auto-select; user picks manually; API returns union of all scopes |
| Association mismatch on create (direct API call) | API returns `403` with `"You are not authorized to create content for this unit"`; frontend displays error toast |
| Content created before scoping changes | Still visible to creator via `created_by = current user ID` clause |

---

## Files to Change

| File | Change |
|------|--------|
| `src/app/api/announcement/route.ts` | Remove `can_manage_user` bypass; always scope; add 403 on unit mismatch in POST |
| `src/app/api/broadcast/route.ts` | Same as announcement |
| `src/app/api/users/route.ts` | Add session scope enforcement to GET |
| `src/app/api/parents/search/route.ts` | Add session scope enforcement |
| `src/app/components/apps/announcement/Add-announcement/index.tsx` | Replace API fetches with session associations for dropdowns |
| `src/app/components/apps/broadcast/Add-broadcast/index.tsx` | Replace API fetches with session associations for dropdowns |
| `src/app/context/AnnouncementContext/index.tsx` | Derive filter dropdown options from session associations |
| `src/app/context/BroadcastContext/index.tsx` | Derive filter dropdown options from session associations |
| `src/app/components/ui-components/Table/StaffTable.tsx` | Derive filter dropdowns from session associations; auto-apply on mount |
| `src/app/components/ui-components/Table/ParentTable.tsx` | Derive filter dropdowns from session associations; auto-apply on mount |
