# Unit-Scoped Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce that every user sees only data belonging to their associated units/levels/classes across announcements, broadcasts, and user management pages.

**Architecture:** Two-layer approach — API endpoints enforce session-based scoping server-side (security boundary); frontend components derive dropdown options from session associations already on the client (no extra API calls needed for dropdowns).

**Tech Stack:** Next.js App Router, next-auth (getServerSession / useSession), MySQL (connection.execute), React, Flowbite UI

---

## File Map

| File | Change Type | Responsibility |
|------|-------------|----------------|
| `src/app/api/announcement/route.ts` | Modify | Remove admin bypass in GET; add scope validation in POST |
| `src/app/api/broadcast/route.ts` | Modify | Remove admin bypass in GET; add scope validation in POST |
| `src/app/api/users/route.ts` | Modify | Add session scope enforcement to all queries |
| `src/app/api/parents/search/route.ts` | Modify | Add session scope enforcement |
| `src/app/components/apps/announcement/Add-announcement/index.tsx` | Modify | Replace API fetches with session association dropdowns |
| `src/app/components/apps/announcement/Announcement-list/index.tsx` | Modify | Replace context unit/level/class options with session association options |
| `src/app/components/apps/broadcast/Add-broadcast/index.tsx` | Modify | Replace API fetches with session association dropdowns |
| `src/app/components/apps/broadcast/Broadcast-list/index.tsx` | Modify | Replace context unit/level/class options with session association options |
| `src/app/components/ui-components/Table/StaffTable.tsx` | Modify | Replace fetchUnitsLevelsClasses with session associations; add auto-filter on mount |
| `src/app/components/ui-components/Table/ParentTable.tsx` | Modify | Replace fetchUnitsLevelsClasses with session associations; add auto-filter on mount |

---

## Task 1: Fix `GET /api/announcement` — Remove Admin Bypass

**Files:**
- Modify: `src/app/api/announcement/route.ts:21-23` and `:76-118`

- [ ] **Step 1: Remove `roleData` / `isAdmin` declarations**

In `src/app/api/announcement/route.ts`, delete lines 21–23:

```ts
// DELETE these 3 lines:
const roleData = session?.user?.users?.[0]?.roleData;
// Only super-admins (can_manage_user) see all announcements regardless of scope
const isAdmin = Boolean(roleData?.can_manage_user);
```

- [ ] **Step 2: Remove the `if (!isAdmin)` wrapper, keep the scope body**

Change lines 76–118. Before:

```ts
    // Non-admin users (including teachers) only see announcements scoped to their assigned units/levels/classes
    if (!isAdmin) {
      const [unitRows] = await connection.execute(
        "SELECT unit_id FROM user_unit WHERE usr_id = ?",
        [userId]
      );
      const [levelRows] = await connection.execute(
        "SELECT lvl_id FROM user_level WHERE usr_id = ?",
        [userId]
      );
      const [classRows] = await connection.execute(
        "SELECT cls_id FROM user_class WHERE usr_id = ?",
        [userId]
      );

      const userUnitIds = (unitRows as any[]).map((r) => r.unit_id);
      const userLevelIds = (levelRows as any[]).map((r) => r.lvl_id);
      const userClassIds = (classRows as any[]).map((r) => r.cls_id);

      const scopeConditions: string[] = [
        "(a.unit_id IS NULL AND a.level_id IS NULL AND a.class_id IS NULL)",
        "a.created_by = ?",
      ];
      const scopeParams: any[] = [userId];

      if (userUnitIds.length > 0) {
        const ph = userUnitIds.map(() => "?").join(", ");
        scopeConditions.push(`(a.unit_id IN (${ph}) AND a.level_id IS NULL AND a.class_id IS NULL)`);
        scopeParams.push(...userUnitIds);
      }
      if (userLevelIds.length > 0) {
        const ph = userLevelIds.map(() => "?").join(", ");
        scopeConditions.push(`(a.level_id IN (${ph}) AND a.class_id IS NULL)`);
        scopeParams.push(...userLevelIds);
      }
      if (userClassIds.length > 0) {
        const ph = userClassIds.map(() => "?").join(", ");
        scopeConditions.push(`a.class_id IN (${ph})`);
        scopeParams.push(...userClassIds);
      }

      query += ` AND (${scopeConditions.join(" OR ")})`;
      params.push(...scopeParams);
    }
```

After (remove `if (!isAdmin) {` and its closing `}`):

```ts
    // All users see only announcements scoped to their assigned units/levels/classes
    const [unitRows] = await connection.execute(
      "SELECT unit_id FROM user_unit WHERE usr_id = ?",
      [userId]
    );
    const [levelRows] = await connection.execute(
      "SELECT lvl_id FROM user_level WHERE usr_id = ?",
      [userId]
    );
    const [classRows] = await connection.execute(
      "SELECT cls_id FROM user_class WHERE usr_id = ?",
      [userId]
    );

    const userUnitIds = (unitRows as any[]).map((r) => r.unit_id);
    const userLevelIds = (levelRows as any[]).map((r) => r.lvl_id);
    const userClassIds = (classRows as any[]).map((r) => r.cls_id);

    const scopeConditions: string[] = [
      "(a.unit_id IS NULL AND a.level_id IS NULL AND a.class_id IS NULL)",
      "a.created_by = ?",
    ];
    const scopeParams: any[] = [userId];

    if (userUnitIds.length > 0) {
      const ph = userUnitIds.map(() => "?").join(", ");
      scopeConditions.push(`(a.unit_id IN (${ph}) AND a.level_id IS NULL AND a.class_id IS NULL)`);
      scopeParams.push(...userUnitIds);
    }
    if (userLevelIds.length > 0) {
      const ph = userLevelIds.map(() => "?").join(", ");
      scopeConditions.push(`(a.level_id IN (${ph}) AND a.class_id IS NULL)`);
      scopeParams.push(...userLevelIds);
    }
    if (userClassIds.length > 0) {
      const ph = userClassIds.map(() => "?").join(", ");
      scopeConditions.push(`a.class_id IN (${ph})`);
      scopeParams.push(...userClassIds);
    }

    query += ` AND (${scopeConditions.join(" OR ")})`;
    params.push(...scopeParams);
```

- [ ] **Step 3: Verify manually**

Log in as a user with `can_manage_user=true` who is associated with only Unit A.
Hit `GET /api/announcement` — should return only announcements for Unit A, not all units.

- [ ] **Step 4: Commit**

```bash
git add src/app/api/announcement/route.ts
git commit -m "fix(api): scope announcement GET to all users' assigned units"
```

---

## Task 2: Fix `POST /api/announcement` — Validate Unit Ownership

**Files:**
- Modify: `src/app/api/announcement/route.ts:152-283`

- [ ] **Step 1: Add scope check after user validation**

After the existing `userCheck` block (after line 177 `}`), insert:

```ts
    // Verify submitted unit_id belongs to the user's associated units
    const body = await request.json();
    const { 
      title, 
      unit: _unit, // Legacy field
      unit_id,
      level_id, 
      class_id,
      content, 
      contentFormat = 'plain',
      action = 0,
      url, 
      document, 
      mediaFiles
    } = body;

    if (unit_id) {
      const [scopeUnitRows] = await connection.execute(
        "SELECT unit_id FROM user_unit WHERE usr_id = ? AND unit_id = ?",
        [userId, unit_id]
      );
      if ((scopeUnitRows as any[]).length === 0) {
        return NextResponse.json(
          { error: "You are not authorized to create content for this unit" },
          { status: 403 }
        );
      }
    }
```

> **Important:** Because `body` is now parsed above, remove the existing `const body = await request.json();` and destructuring on the original lines 180–193. The entire body parse and destructure now happens in the block above.

The final POST handler structure after this change:

```ts
export async function POST(request: Request) {
  try {
    const session = await getServerSession(authOptions);
    const userId = session?.user?.id;
    
    if (!userId) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 }
      );
    }
    
    const [userCheck] = await connection.execute(
      "SELECT usr_id FROM user WHERE usr_id = ?",
      [userId]
    );
    
    if (!Array.isArray(userCheck) || userCheck.length === 0) {
      return NextResponse.json(
        { error: "User not found in database" },
        { status: 404 }
      );
    }

    const body = await request.json();
    const { 
      title, 
      unit: _unit,
      unit_id,
      level_id, 
      class_id,
      content, 
      contentFormat = 'plain',
      action = 0,
      url, 
      document, 
      mediaFiles
    } = body;

    if (unit_id) {
      const [scopeUnitRows] = await connection.execute(
        "SELECT unit_id FROM user_unit WHERE usr_id = ? AND unit_id = ?",
        [userId, unit_id]
      );
      if ((scopeUnitRows as any[]).length === 0) {
        return NextResponse.json(
          { error: "You are not authorized to create content for this unit" },
          { status: 403 }
        );
      }
    }

    // ... rest of POST (INSERT, media, notifications) unchanged
```

- [ ] **Step 2: Verify manually**

POST to `/api/announcement` with a `unit_id` that is NOT in the logged-in user's associations.
Expected: `403 { error: "You are not authorized to create content for this unit" }`

- [ ] **Step 3: Commit**

```bash
git add src/app/api/announcement/route.ts
git commit -m "fix(api): return 403 when creating announcement for unauthorized unit"
```

---

## Task 3: Fix `GET /api/broadcast` — Remove Admin Bypass

**Files:**
- Modify: `src/app/api/broadcast/route.ts:21-23` and `:76-118`

- [ ] **Step 1: Remove `roleData` / `isAdmin` declarations**

In `src/app/api/broadcast/route.ts`, delete lines 21–23:

```ts
// DELETE these 3 lines:
const roleData = session?.user?.users?.[0]?.roleData;
// Only super-admins (can_manage_user) see all broadcasts regardless of scope
const isAdmin = Boolean(roleData?.can_manage_user);
```

- [ ] **Step 2: Remove the `if (!isAdmin)` wrapper, keep the scope body**

Same transformation as Task 1 but for the `broadcasts` table (alias `b`):

```ts
    // All users see only broadcasts scoped to their assigned units/levels/classes
    const [unitRows] = await connection.execute(
      "SELECT unit_id FROM user_unit WHERE usr_id = ?",
      [userId]
    );
    const [levelRows] = await connection.execute(
      "SELECT lvl_id FROM user_level WHERE usr_id = ?",
      [userId]
    );
    const [classRows] = await connection.execute(
      "SELECT cls_id FROM user_class WHERE usr_id = ?",
      [userId]
    );

    const userUnitIds = (unitRows as any[]).map((r) => r.unit_id);
    const userLevelIds = (levelRows as any[]).map((r) => r.lvl_id);
    const userClassIds = (classRows as any[]).map((r) => r.cls_id);

    const scopeConditions: string[] = [
      "(b.unit_id IS NULL AND b.level_id IS NULL AND b.class_id IS NULL)",
      "b.created_by = ?",
    ];
    const scopeParams: any[] = [userId];

    if (userUnitIds.length > 0) {
      const ph = userUnitIds.map(() => "?").join(", ");
      scopeConditions.push(`(b.unit_id IN (${ph}) AND b.level_id IS NULL AND b.class_id IS NULL)`);
      scopeParams.push(...userUnitIds);
    }
    if (userLevelIds.length > 0) {
      const ph = userLevelIds.map(() => "?").join(", ");
      scopeConditions.push(`(b.level_id IN (${ph}) AND b.class_id IS NULL)`);
      scopeParams.push(...userLevelIds);
    }
    if (userClassIds.length > 0) {
      const ph = userClassIds.map(() => "?").join(", ");
      scopeConditions.push(`b.class_id IN (${ph})`);
      scopeParams.push(...userClassIds);
    }

    query += ` AND (${scopeConditions.join(" OR ")})`;
    params.push(...scopeParams);
```

- [ ] **Step 3: Verify manually**

Same check as Task 1 but for broadcasts.

- [ ] **Step 4: Commit**

```bash
git add src/app/api/broadcast/route.ts
git commit -m "fix(api): scope broadcast GET to all users' assigned units"
```

---

## Task 4: Fix `POST /api/broadcast` — Validate Unit Ownership

**Files:**
- Modify: `src/app/api/broadcast/route.ts:140-246`

- [ ] **Step 1: Add scope check after userId validation**

After the existing `if (!userId)` block (after line 151 `}`), before the body parse on line 153, insert:

```ts
    const body = await request.json();
    const { 
      title, 
      unit,
      unit_id,
      level_id,
      class_id,
      content, 
      contentFormat = 'rich',
      url, 
      document, 
      action,
      mediaFiles = []
    } = body;

    // Validate input
    if (!title || !unit_id || !content) {
      return NextResponse.json(
        { error: "Title, unit, and content are required" },
        { status: 400 }
      );
    }

    // Verify submitted unit_id belongs to the user's associated units
    const [scopeUnitRows] = await connection.execute(
      "SELECT unit_id FROM user_unit WHERE usr_id = ? AND unit_id = ?",
      [userId, unit_id]
    );
    if ((scopeUnitRows as any[]).length === 0) {
      return NextResponse.json(
        { error: "You are not authorized to create content for this unit" },
        { status: 403 }
      );
    }
```

> **Important:** Remove the original body parse (line 153), destructure (lines 154–165), and validation block (lines 167–173) since they are now above.

- [ ] **Step 2: Also remove `isAdmin` line**

Line 144 in broadcast POST: `const isAdmin = session?.user?.users?.[0]?.role === 1;` — delete it (unused after this change).

- [ ] **Step 3: Verify manually**

POST to `/api/broadcast` with unauthorized `unit_id`.
Expected: `403 { error: "You are not authorized to create content for this unit" }`

- [ ] **Step 4: Commit**

```bash
git add src/app/api/broadcast/route.ts
git commit -m "fix(api): return 403 when creating broadcast for unauthorized unit"
```

---

## Task 5: Fix `GET /api/users` — Add Session Scope Enforcement

**Files:**
- Modify: `src/app/api/users/route.ts:1-292`

- [ ] **Step 1: Add imports at top of file**

```ts
import { NextResponse } from "next/server";
import { connection } from "@/lib/db";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/app/api/auth/[...nextauth]/route";
```

- [ ] **Step 2: Add session scope check at start of GET handler**

After `const offset = (page - 1) * limit;` (line 14), insert:

```ts
  // Enforce session-based scope — every user sees only people in their associated units
  const session = await getServerSession(authOptions);
  const sessionUserId = session?.user?.id;
  if (!sessionUserId) {
    return NextResponse.json({ error: "Authentication required" }, { status: 401 });
  }

  const [sessionUnitRows] = await connection.execute(
    "SELECT unit_id FROM user_unit WHERE usr_id = ?",
    [sessionUserId]
  );
  const sessionUnitIds = (sessionUnitRows as any[]).map((r) => r.unit_id);

  // If user has no unit associations, return empty results
  if (sessionUnitIds.length === 0) {
    return NextResponse.json({
      staffUsers: [],
      parentUsers: [],
      pagination: {
        page, limit,
        totalStaff: 0, totalParents: 0,
        totalStaffPages: 0, totalParentPages: 0,
        hasMoreStaff: false, hasMoreParents: false
      }
    });
  }

  const sessionUnitPh = sessionUnitIds.map(() => "?").join(", ");
```

- [ ] **Step 3: Inject scope filter into all 4 queries**

In each of the 4 query blocks (`staffCountQuery`, `staffQuery`, `parentCountQuery`, `parentQuery`), add the scope filter immediately after the `WHERE u.is_deleted = FALSE AND ...` base condition:

For staff count query (after `WHERE u.is_deleted = FALSE AND u.staff_data IS NOT NULL`):
```ts
      staffCountQuery += ` AND u.usr_id IN (SELECT usr_id FROM user_unit WHERE unit_id IN (${sessionUnitPh}))`;
      staffCountParams.push(...sessionUnitIds);
```

For staff query (after `WHERE u.is_deleted = FALSE AND u.staff_data IS NOT NULL`):
```ts
      staffQuery += ` AND u.usr_id IN (SELECT usr_id FROM user_unit WHERE unit_id IN (${sessionUnitPh}))`;
      staffParams.push(...sessionUnitIds);
```

For parent count query (after `WHERE u.is_deleted = FALSE AND u.role = 4`):
```ts
      parentCountQuery += ` AND u.usr_id IN (SELECT usr_id FROM user_unit WHERE unit_id IN (${sessionUnitPh}))`;
      parentCountParams.push(...sessionUnitIds);
```

For parent query (after `WHERE u.is_deleted = FALSE AND u.role = 4`):
```ts
      parentQuery += ` AND u.usr_id IN (SELECT usr_id FROM user_unit WHERE unit_id IN (${sessionUnitPh}))`;
      parentParams.push(...sessionUnitIds);
```

Each injection goes BEFORE the existing `if (search)` / `if (unitFilter)` / etc. blocks, so optional filters narrow within the scoped set.

- [ ] **Step 4: Verify manually**

Call `GET /api/users?type=staff` as a user associated with Unit A only.
Expected: only staff members who also have Unit A in their associations.

- [ ] **Step 5: Commit**

```bash
git add src/app/api/users/route.ts
git commit -m "fix(api): scope /api/users results to logged-in user's associated units"
```

---

## Task 6: Fix `GET /api/parents/search` — Add Session Scope

**Files:**
- Modify: `src/app/api/parents/search/route.ts:1-34`

- [ ] **Step 1: Add imports**

```ts
import { NextResponse } from "next/server";
import { connection } from "@/lib/db";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/app/api/auth/[...nextauth]/route";
```

- [ ] **Step 2: Add session scope at start of GET handler**

After the `parentFields` array declaration, insert:

```ts
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Authentication required" }, { status: 401 });
    }

    const [sessionUnitRows] = await connection.execute(
      "SELECT unit_id FROM user_unit WHERE usr_id = ?",
      [session.user.id]
    );
    const sessionUnitIds = (sessionUnitRows as any[]).map((r) => r.unit_id);
```

- [ ] **Step 3: Add scope condition to SQL**

Replace the SQL base string:

```ts
    let sql = `SELECT c.cda_id, c.father_name, c.mother_name, c.father_email, c.mother_email, c.father_phone, c.mother_phone
      FROM children_data c
      WHERE c.is_deleted = FALSE`;
```

With:

```ts
    const unitPh = sessionUnitIds.length > 0 ? sessionUnitIds.map(() => "?").join(", ") : "NULL";
    let sql = `SELECT c.cda_id, c.father_name, c.mother_name, c.father_email, c.mother_email, c.father_phone, c.mother_phone
      FROM children_data c
      WHERE c.is_deleted = FALSE
      AND (
        EXISTS (
          SELECT 1 FROM user u
          JOIN user_unit uu ON u.usr_id = uu.usr_id
          WHERE u.parent_data = c.cda_id AND uu.unit_id IN (${unitPh})
          AND u.is_deleted = FALSE
        )
        OR NOT EXISTS (
          SELECT 1 FROM user u WHERE u.parent_data = c.cda_id AND u.is_deleted = FALSE
        )
      )`;
    params.push(...sessionUnitIds);
```

- [ ] **Step 4: Verify manually**

Search parents as a Unit A user. Should only return parent records linked to Unit A users, plus unlinked parent records.

- [ ] **Step 5: Commit**

```bash
git add src/app/api/parents/search/route.ts
git commit -m "fix(api): scope parent search to logged-in user's associated units"
```

---

## Task 7: Fix `Add-announcement` — Dropdowns from Session Associations

**Files:**
- Modify: `src/app/components/apps/announcement/Add-announcement/index.tsx`

- [ ] **Step 1: Replace imports and add useSession**

Remove:
```ts
import { useUnitContext } from "@/app/context/UnitContext";
import { useLevelContext } from "@/app/context/LevelContext";
import { useClassContext } from "@/app/context/ClassContext";
import { Level } from "@/app/(DashboardLayout)/types/apps/level";
import { Class } from "@/app/(DashboardLayout)/types/apps/class";
```

Add:
```ts
import { useSession } from "next-auth/react";
```

- [ ] **Step 2: Replace context hooks with session**

Remove:
```ts
  const { units, loading: unitsLoading } = useUnitContext();
  const { getLevelsByUnit } = useLevelContext();
  const { getClassesByLevel } = useClassContext();
```

And remove these state variables (no longer needed):
```ts
  const [levels, setLevels] = useState<Level[]>([]);
  const [classes, setClasses] = useState<Class[]>([]);
  const [loadingLevels, setLoadingLevels] = useState(false);
  const [loadingClasses, setLoadingClasses] = useState(false);
```

Add after `const router = useRouter();`:
```ts
  const { data: session } = useSession();
  const associations = (session?.user as any)?.users?.[0]?.associations;
  const scopedUnits = associations?.units ?? [];
  const scopedLevels: any[] = formData.unit_id
    ? (associations?.levels ?? []).filter((l: any) => l.unit_id === formData.unit_id)
    : (associations?.levels ?? []);
  const scopedClasses: any[] = formData.level_id
    ? (associations?.classes ?? []).filter((c: any) => c.lvl_id === formData.level_id)
    : (associations?.classes ?? []);
```

- [ ] **Step 3: Remove the two useEffect blocks that fetched levels/classes**

Delete the `useEffect` at lines 49–65 (fetches levels when unit_id changes) and lines 67–82 (fetches classes when level_id changes) entirely.

- [ ] **Step 4: Add auto-select useEffect for single unit**

```ts
  useEffect(() => {
    if (scopedUnits.length === 1 && formData.unit_id === 0) {
      setFormData(prev => ({ ...prev, unit_id: scopedUnits[0].unit_id }));
    }
  }, [scopedUnits]);
```

- [ ] **Step 5: Update loading guard**

Change:
```ts
  if (unitsLoading) {
    return <div className="flex justify-center py-10"><Spinner size="xl" /></div>;
  }
```

To:
```ts
  if (!session) {
    return <div className="flex justify-center py-10"><Spinner size="xl" /></div>;
  }
```

- [ ] **Step 6: Update unit select in JSX**

Change the unit `<Select>` options from `{units.map(...)}` to `{scopedUnits.map(...)}`:

```tsx
              <Select
                id="unit_id"
                name="unit_id"
                value={formData.unit_id || ""}
                onChange={handleChange}
                required
              >
                <option value="">Select Unit</option>
                {scopedUnits.length === 0 && (
                  <option disabled value="">No units assigned</option>
                )}
                {scopedUnits.map((unit: any) => (
                  <option key={unit.unit_id} value={unit.unit_id}>{unit.unit_name}</option>
                ))}
              </Select>
```

- [ ] **Step 7: Update level select in JSX**

Change level `<Select>` — remove `loadingLevels` references, use `scopedLevels`:

```tsx
              <Select
                id="level_id"
                name="level_id"
                value={formData.level_id || ""}
                onChange={handleChange}
                disabled={!formData.unit_id}
              >
                <option value="">
                  {!formData.unit_id
                    ? "Select a unit first"
                    : scopedLevels.length === 0
                      ? "No levels available for this unit"
                      : "Select a level (optional)"}
                </option>
                <option value="0">All Levels</option>
                {scopedLevels.map((level: any) => (
                  <option key={level.lvl_id} value={level.lvl_id}>{level.lvl_name}</option>
                ))}
              </Select>
```

- [ ] **Step 8: Update class select in JSX**

```tsx
              <Select
                id="class_id"
                name="class_id"
                value={formData.class_id || ""}
                onChange={handleChange}
                disabled={!formData.level_id}
              >
                <option value="">
                  {!formData.level_id
                    ? "Select a level first"
                    : scopedClasses.length === 0
                      ? "No classes available for this level"
                      : "Select a class (optional)"}
                </option>
                <option value="0">All Classes</option>
                {scopedClasses.map((cls: any) => (
                  <option key={cls.cls_id} value={cls.cls_id}>{cls.class_name}</option>
                ))}
              </Select>
```

- [ ] **Step 9: Update error handling in handleSubmit to surface 403 errors**

Change the catch block:

```ts
    } catch (error: any) {
      console.error("Error creating announcement:", error);
      const errorMessage = error?.response?.data?.error || 'Failed to create announcement';
      setShowAlert({
        show: true,
        message: errorMessage,
        type: 'error'
      });
      setIsSubmitting(false);
    }
```

- [ ] **Step 10: Verify manually**

Open Create Announcement page as a unit-specific staff user. Unit dropdown should only show their assigned units. Level/class dropdowns should cascade from session data (no API calls for dropdown options in network tab).

- [ ] **Step 11: Commit**

```bash
git add src/app/components/apps/announcement/Add-announcement/index.tsx
git commit -m "fix(ui): scope announcement create form dropdowns to session associations"
```

---

## Task 8: Fix `Announcement-list` — Filter Dropdowns from Session

**Files:**
- Modify: `src/app/components/apps/announcement/Announcement-list/index.tsx`

- [ ] **Step 1: Add useSession import**

Add after existing imports:
```ts
import { useSession } from "next-auth/react";
```

- [ ] **Step 2: Add session hook and derived options**

After the existing context hooks (after line 36), add:
```ts
  const { data: session } = useSession();
  const associations = (session?.user as any)?.users?.[0]?.associations;
  const scopedUnits: any[] = associations?.units ?? [];
  const scopedLevels: any[] = selectedUnitFilter
    ? (associations?.levels ?? []).filter((l: any) => l.unit_id === parseInt(selectedUnitFilter))
    : (associations?.levels ?? []);
  const scopedClasses: any[] = selectedLevelFilter
    ? (associations?.classes ?? []).filter((c: any) => c.lvl_id === parseInt(selectedLevelFilter))
    : (associations?.classes ?? []);
```

- [ ] **Step 3: Remove API calls from handleUnitChange**

In `handleUnitChange`, remove:
```ts
    if (unitId) {
      setLoadingLevels(true);
      await getLevelsByUnit(parseInt(unitId));
      setLoadingLevels(false);
    }
```

Also remove the `loadingLevels` / `loadingClasses` state variables and the `isUnitChanging` / `isLevelChanging` ref usage around level fetching (keep the filter timer logic).

`handleUnitChange` after the change:
```ts
  const handleUnitChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const unitId = e.target.value;
    setSelectedUnitFilter(unitId);
    setSelectedLevelFilter("");
    setSelectedClassFilter("");
    if (filterTimer.current) clearTimeout(filterTimer.current);
    filterTimer.current = setTimeout(() => {
      applyFilters({ unitValue: unitId, levelValue: "", classValue: "", actionValue: selectedActionFilter, searchValue: searchTerm });
    }, 300);
  };
```

Make `handleLevelChange` synchronous too:
```ts
  const handleLevelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const levelId = e.target.value;
    setSelectedLevelFilter(levelId);
    setSelectedClassFilter("");
    if (filterTimer.current) clearTimeout(filterTimer.current);
    filterTimer.current = setTimeout(() => {
      applyFilters({ unitValue: selectedUnitFilter, levelValue: levelId, classValue: "", actionValue: selectedActionFilter, searchValue: searchTerm });
    }, 300);
  };
```

- [ ] **Step 4: Remove the `isUnitChanging` / `isLevelChanging` refs (no longer needed)**

Remove:
```ts
  const isUnitChanging = useRef(false);
  const isLevelChanging = useRef(false);
```

And remove the guard in `applyFilters`:
```ts
    if (isUnitChanging.current || isLevelChanging.current) return;
```

- [ ] **Step 5: Update the unit filter Select in JSX**

Change from `{units.map(...)}` to `{scopedUnits.map(...)}`:

```tsx
            <Select
              id="unitFilter"
              value={selectedUnitFilter}
              onChange={handleUnitChange}
              className="w-full"
              style={{ minWidth: '140px' }}
            >
              <option value="">All Units</option>
              {scopedUnits.map((unit: any) => (
                <option key={unit.unit_id} value={unit.unit_id}>{unit.unit_name}</option>
              ))}
            </Select>
```

- [ ] **Step 6: Update level filter Select in JSX**

Change from `{levels.filter(...).map(...)}` to `{scopedLevels.map(...)}`:

```tsx
            <Select
              id="levelFilter"
              value={selectedLevelFilter}
              onChange={handleLevelChange}
              className="w-full"
              style={{ minWidth: '140px' }}
              disabled={!selectedUnitFilter}
            >
              <option value="">All Levels</option>
              {scopedLevels.map((level: any) => (
                <option key={level.lvl_id} value={level.lvl_id}>{level.lvl_name}</option>
              ))}
            </Select>
```

- [ ] **Step 7: Update class filter Select in JSX**

```tsx
            <Select
              id="classFilter"
              value={selectedClassFilter}
              onChange={handleClassChange}
              className="w-full"
              style={{ minWidth: '140px' }}
              disabled={!selectedLevelFilter}
            >
              <option value="">All Classes</option>
              {scopedClasses.map((cls: any) => (
                <option key={cls.cls_id} value={cls.cls_id}>{cls.class_name}</option>
              ))}
            </Select>
```

- [ ] **Step 8: Remove unused context imports**

Remove these imports (no longer used for dropdown population):
```ts
import { useUnitContext } from "@/app/context/UnitContext";
import { useLevelContext } from "@/app/context/LevelContext";
import { useClassContext } from "@/app/context/ClassContext";
```

> **Note:** `getLevelAndClass()` at line 279 uses `levels` and `classes` from context for table cell display. Since we're removing those contexts, either: (a) keep `useLevelContext`/`useClassContext` imports but only for `getLevelAndClass`, OR (b) look up from `associations` instead. Use option (b): change `getLevelAndClass` to use `associations`:

```ts
  const getLevelAndClass = (announcement: any) => {
    const levelName = (associations?.levels ?? []).find(
      (level: any) => level.lvl_id === announcement.level_id
    )?.lvl_name;
    const className = (associations?.classes ?? []).find(
      (cls: any) => cls.cls_id === announcement.class_id
    )?.class_name;
    return { levelName, className };
  };
```

> This means level/class names only show for levels/classes the logged-in user is associated with — which is correct since they can only see announcements scoped to their associations anyway.

- [ ] **Step 9: Update loading guard**

Change:
```ts
  if (loading || unitsLoading) {
```
To:
```ts
  if (loading) {
```

- [ ] **Step 10: Verify manually**

Open Announcement List page. Unit filter dropdown should only show the logged-in user's associated units. Selecting a unit should cascade levels from session associations (no API call in network tab).

- [ ] **Step 11: Commit**

```bash
git add src/app/components/apps/announcement/Announcement-list/index.tsx
git commit -m "fix(ui): scope announcement list filter dropdowns to session associations"
```

---

## Task 9: Fix `Add-broadcast` — Dropdowns from Session Associations

**Files:**
- Modify: `src/app/components/apps/broadcast/Add-broadcast/index.tsx`

This is structurally identical to Task 7 (`Add-announcement`). Apply the same changes:

- [ ] **Step 1: Replace imports**

Remove:
```ts
import { useUnitContext } from "@/app/context/UnitContext";
import { useLevelContext } from "@/app/context/LevelContext";
import { useClassContext } from "@/app/context/ClassContext";
import { Level } from "@/app/(DashboardLayout)/types/apps/level";
import { Class } from "@/app/(DashboardLayout)/types/apps/class";
```
Add:
```ts
import { useSession } from "next-auth/react";
```

- [ ] **Step 2: Replace context hooks with session + derived associations**

Remove:
```ts
  const { units, loading: unitsLoading } = useUnitContext();
  const { getLevelsByUnit } = useLevelContext();
  const { getClassesByLevel } = useClassContext();
  const [levels, setLevels] = useState<Level[]>([]);
  const [classes, setClasses] = useState<Class[]>([]);
  const [loadingLevels, setLoadingLevels] = useState(false);
  const [loadingClasses, setLoadingClasses] = useState(false);
```

Add after `const router = useRouter();`:
```ts
  const { data: session } = useSession();
  const associations = (session?.user as any)?.users?.[0]?.associations;
  const scopedUnits: any[] = associations?.units ?? [];
  const scopedLevels: any[] = formData.unit_id
    ? (associations?.levels ?? []).filter((l: any) => l.unit_id === formData.unit_id)
    : (associations?.levels ?? []);
  const scopedClasses: any[] = formData.level_id
    ? (associations?.classes ?? []).filter((c: any) => c.lvl_id === formData.level_id)
    : (associations?.classes ?? []);
```

- [ ] **Step 3: Remove both useEffect blocks for levels/classes**

Delete the `useEffect` at lines 54–74 (fetches levels when unit_id changes) and lines 76–93 (fetches classes when level_id changes) entirely.

- [ ] **Step 4: Add auto-select useEffect for single unit**

```ts
  useEffect(() => {
    if (scopedUnits.length === 1 && formData.unit_id === 0) {
      setFormData(prev => ({ ...prev, unit_id: scopedUnits[0].unit_id }));
    }
  }, [scopedUnits]);
```

- [ ] **Step 5: Update unit Select in JSX**

```tsx
              <Select
                id="unit_id"
                name="unit_id"
                value={formData.unit_id || ""}
                onChange={handleChange}
                required
              >
                <option value="">Select Unit</option>
                {scopedUnits.length === 0 && (
                  <option disabled value="">No units assigned</option>
                )}
                {scopedUnits.map((unit: any) => (
                  <option key={unit.unit_id} value={unit.unit_id}>{unit.unit_name}</option>
                ))}
              </Select>
```

- [ ] **Step 6: Update level Select in JSX**

```tsx
              <Select
                id="level_id"
                name="level_id"
                value={formData.level_id || ""}
                onChange={handleChange}
                disabled={!formData.unit_id}
              >
                <option value="">
                  {!formData.unit_id
                    ? "Select a unit first"
                    : scopedLevels.length === 0
                      ? "No levels available for this unit"
                      : "Select a level (optional)"}
                </option>
                <option value="0">All Levels</option>
                {scopedLevels.map((level: any) => (
                  <option key={level.lvl_id} value={level.lvl_id}>{level.lvl_name}</option>
                ))}
              </Select>
```

- [ ] **Step 7: Update class Select in JSX**

```tsx
              <Select
                id="class_id"
                name="class_id"
                value={formData.class_id || ""}
                onChange={handleChange}
                disabled={!formData.level_id}
              >
                <option value="">
                  {!formData.level_id
                    ? "Select a level first"
                    : scopedClasses.length === 0
                      ? "No classes available for this level"
                      : "Select a class (optional)"}
                </option>
                <option value="0">All Classes</option>
                {scopedClasses.map((cls: any) => (
                  <option key={cls.cls_id} value={cls.cls_id}>{cls.class_name}</option>
                ))}
              </Select>
```

- [ ] **Step 8: Update error handling in handleSubmit**

```ts
    } catch (error: any) {
      console.error("Error creating broadcast:", error);
      const errorMessage = error?.response?.data?.error || 'Failed to create broadcast';
      setShowAlert({ show: true, message: errorMessage, type: 'error' });
      setIsSubmitting(false);
    }
```

- [ ] **Step 9: Verify manually**

Open Create Broadcast page. Same checks as Task 7 but for broadcast.

- [ ] **Step 10: Commit**

```bash
git add src/app/components/apps/broadcast/Add-broadcast/index.tsx
git commit -m "fix(ui): scope broadcast create form dropdowns to session associations"
```

---

## Task 10: Fix `Broadcast-list` — Filter Dropdowns from Session

**Files:**
- Modify: `src/app/components/apps/broadcast/Broadcast-list/index.tsx`

Apply the same pattern as Task 8 (`Announcement-list`):

- [ ] **Step 1: Add useSession import**

```ts
import { useSession } from "next-auth/react";
```

- [ ] **Step 2: Add session + derived associations after context hooks**

```ts
  const { data: session } = useSession();
  const associations = (session?.user as any)?.users?.[0]?.associations;
  const scopedUnits: any[] = associations?.units ?? [];
  const scopedLevels: any[] = selectedUnitFilter
    ? (associations?.levels ?? []).filter((l: any) => l.unit_id === parseInt(selectedUnitFilter))
    : (associations?.levels ?? []);
  const scopedClasses: any[] = selectedLevelFilter
    ? (associations?.classes ?? []).filter((c: any) => c.lvl_id === parseInt(selectedLevelFilter))
    : (associations?.classes ?? []);
```

- [ ] **Step 3: Make handleUnitChange and handleLevelChange synchronous (remove API calls)**

```ts
  const handleUnitChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const unitId = e.target.value;
    setSelectedUnitFilter(unitId);
    setSelectedLevelFilter("");
    setSelectedClassFilter("");
    if (filterTimer.current) clearTimeout(filterTimer.current);
    filterTimer.current = setTimeout(() => {
      applyFilters({ unitValue: unitId, levelValue: "", classValue: "", actionValue: selectedActionFilter, searchValue: searchTerm });
    }, 300);
  };

  const handleLevelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const levelId = e.target.value;
    setSelectedLevelFilter(levelId);
    setSelectedClassFilter("");
    if (filterTimer.current) clearTimeout(filterTimer.current);
    filterTimer.current = setTimeout(() => {
      applyFilters({ unitValue: selectedUnitFilter, levelValue: levelId, classValue: "", actionValue: selectedActionFilter, searchValue: searchTerm });
    }, 300);
  };
```

- [ ] **Step 4: Remove `isUnitChanging`, `isLevelChanging` refs and their guards**

Remove refs and remove the guard `if (isUnitChanging.current || isLevelChanging.current) return;` from `applyFilters`.

- [ ] **Step 5: Update unit/level/class Select options in JSX**

Unit select:
```tsx
              <option value="">All Units</option>
              {scopedUnits.map((unit: any) => (
                <option key={unit.unit_id} value={unit.unit_id}>{unit.unit_name}</option>
              ))}
```

Level select (replace the `.filter(...).map(...)` block):
```tsx
              <option value="">All Levels</option>
              {scopedLevels.map((level: any) => (
                <option key={level.lvl_id} value={level.lvl_id}>{level.lvl_name}</option>
              ))}
```

Class select:
```tsx
              <option value="">All Classes</option>
              {scopedClasses.map((cls: any) => (
                <option key={cls.cls_id} value={cls.cls_id}>{cls.class_name}</option>
              ))}
```

- [ ] **Step 6: Remove unused context imports**

Remove `useUnitContext`, `useLevelContext`, `useClassContext` imports if `levels` and `classes` are no longer used elsewhere in the file. Check for any `getLevelAndClass` equivalent (there may be level/class name display in the table — handle same way as Task 8 step 8, using `associations` for lookups).

- [ ] **Step 7: Verify manually**

Open Broadcast List page. Same checks as Task 8 but for broadcasts.

- [ ] **Step 8: Commit**

```bash
git add src/app/components/apps/broadcast/Broadcast-list/index.tsx
git commit -m "fix(ui): scope broadcast list filter dropdowns to session associations"
```

---

## Task 11: Fix `StaffTable` — Session-Scoped Filter Dropdowns

**Files:**
- Modify: `src/app/components/ui-components/Table/StaffTable.tsx`

- [ ] **Step 1: Add useSession import**

```ts
import { useSession } from "next-auth/react";
```

- [ ] **Step 2: Replace `fetchUnitsLevelsClasses` with session data**

Add after the existing hooks at the top of the `StaffTable` component:

```ts
  const { data: session } = useSession();
  const sessionAssociations = (session?.user as any)?.users?.[0]?.associations;
```

Change `availableUnits`, `availableLevels`, `availableClasses` initial state to be derived from session. Since these are used in both filter dropdowns AND in the add/edit form, replace the state + `fetchUnitsLevelsClasses` with session data.

Replace:
```ts
  const [availableUnits, setAvailableUnits] = useState<{unit_id: number, unit_name: string}[]>([]);
  const [availableLevels, setAvailableLevels] = useState<{lvl_id: number, lvl_name: string, unit_id: number}[]>([]);
  const [availableClasses, setAvailableClasses] = useState<{cls_id: number, class_name: string, unit_id: number, lvl_id: number}[]>([]);
```

With:
```ts
  const availableUnits: {unit_id: number, unit_name: string}[] = sessionAssociations?.units ?? [];
  const availableLevels: {lvl_id: number, lvl_name: string, unit_id: number}[] = sessionAssociations?.levels ?? [];
  const availableClasses: {cls_id: number, class_name: string, unit_id: number, lvl_id: number}[] = sessionAssociations?.classes ?? [];
```

- [ ] **Step 3: Remove `fetchUnitsLevelsClasses` function and its `useEffect`**

Delete the `fetchUnitsLevelsClasses` function (lines 182–198) and the `useEffect` that calls it (lines 165–168).

- [ ] **Step 4: Add auto-apply unit filter on mount**

Add a new `useEffect` after the existing debounce effect:

```ts
  useEffect(() => {
    if (availableUnits.length === 1 && !unitFilter) {
      setUnitFilter(String(availableUnits[0].unit_id));
    }
  }, [availableUnits]);
```

> This auto-applies the single unit as a filter on mount, so the table loads pre-scoped for unit-specific staff.

- [ ] **Step 5: Verify manually**

Open the user management page as a unit-specific staff user. Staff table should only show staff from their associated unit(s). Unit filter dropdown should only show their units.

- [ ] **Step 6: Commit**

```bash
git add src/app/components/ui-components/Table/StaffTable.tsx
git commit -m "fix(ui): scope staff table filter dropdowns to session associations"
```

---

## Task 12: Fix `ParentTable` — Session-Scoped Filter Dropdowns

**Files:**
- Modify: `src/app/components/ui-components/Table/ParentTable.tsx`

- [ ] **Step 1: Add useSession import**

```ts
import { useSession } from "next-auth/react";
```

- [ ] **Step 2: Replace `fetchUnitsLevelsClasses` with session data**

Same pattern as Task 11:

Add after existing hooks:
```ts
  const { data: session } = useSession();
  const sessionAssociations = (session?.user as any)?.users?.[0]?.associations;
```

Replace state declarations:
```ts
  const availableUnits: {unit_id: number, unit_name: string}[] = sessionAssociations?.units ?? [];
  const availableLevels: {lvl_id: number, lvl_name: string, unit_id: number}[] = sessionAssociations?.levels ?? [];
  const availableClasses: {cls_id: number, class_name: string, unit_id: number, lvl_id: number}[] = sessionAssociations?.classes ?? [];
```

- [ ] **Step 3: Remove `fetchUnitsLevelsClasses` function and its `useEffect`**

Delete the `fetchUnitsLevelsClasses` function (lines 274–290) and the `useEffect` on line 252–254 that calls it.

- [ ] **Step 4: Add auto-apply unit filter on mount**

```ts
  useEffect(() => {
    if (availableUnits.length === 1 && !unitFilter) {
      setUnitFilter(String(availableUnits[0].unit_id));
    }
  }, [availableUnits]);
```

- [ ] **Step 5: Verify manually**

Open the user management page. Parent table should only show parents associated with the logged-in user's units. Parent search autocomplete (in add form) should only return parent records linked to units in the user's scope, or unlinked parent records.

- [ ] **Step 6: Commit**

```bash
git add src/app/components/ui-components/Table/ParentTable.tsx
git commit -m "fix(ui): scope parent table filter dropdowns to session associations"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| Announcement list: show only user's scope | Task 1 (API GET) + Task 8 (filter dropdowns) |
| Announcement create: restrict unit/level/class selects | Task 2 (API POST 403) + Task 7 (form dropdowns) |
| Broadcast list: show only user's scope | Task 3 (API GET) + Task 10 (filter dropdowns) |
| Broadcast create: restrict unit/level/class selects | Task 4 (API POST 403) + Task 9 (form dropdowns) |
| Staff table: only same-scope users | Task 5 (/api/users) + Task 11 (filter dropdowns) |
| Parent table: only same-scope users | Task 5 (/api/users) + Task 12 (filter dropdowns) |
| 403 on unit mismatch, show error in UI | Task 2/4 (API) + Task 7/9 step 9/8 (error handling) |
| Auto-select when single unit association | Task 7 step 4, Task 9 step 4, Task 11 step 4, Task 12 step 4 |
| Empty state when no associations | Task 5 (early return), Task 7/9 (no units msg) |
| Remove admin bypass | Task 1 (announcement), Task 3 (broadcast) |
