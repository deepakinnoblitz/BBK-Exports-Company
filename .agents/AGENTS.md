# Innoblitz HRMS & CRM — Project Context

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React 18 + Vite, TypeScript, MUI v5 |
| Backend | Frappe Framework (Python), ERPNext-style doctypes |
| Dev Server | `npm run dev` in `apps/company/company/frontend` |
| App Server | `bench start` in `com-bench` |

---

## Senior React Developer Standards

When coding the frontend, you must act as a Senior React Developer and follow these guidelines:
1. **Performance First**: Prefer memoized callbacks (`useCallback`) and calculations (`useMemo`) for expensive tasks. Maintain clean state declarations to avoid extra renders.
2. **Strict Typing**: Write detailed TypeScript interfaces for all components and API responses. Avoid using `any` unless absolutely necessary (like dynamically parsing JSON structures).
3. **MUI Styling**: Use the `sx` prop for customized designs, referencing theme tokens (`theme.palette.divider`, `theme.palette.background.neutral`, `theme.customShadows.z20`) rather than static CSS values. Keep typography levels aligned (`variant="h4"`, `variant="subtitle2"`, `variant="caption"`).
4. **Defensive Programming**: Ensure robust null/undefined handling (e.g. checking values with optional chaining `?.`, fallback defaults `|| '—'`).
5. **Component Organization**: Separate clean business logic (Vite/API fetches) from presentational items. Keep code structures highly readable, structured, and modular.

---

## Workspace Paths

```
com-bench/apps/company/company/
  frontend/src/
    api/           # All API modules (one file per feature)
    sections/      # React page sections (one dir per feature)
    utils/         # Shared utilities
    components/    # Shared UI components
    routes/        # React Router config
    layouts/       # Layout wrappers (DashboardContent)
  company/
    doctype/       # Frappe Python doctypes
    frontend_api.py  # Custom whitelisted API endpoints
```

---

## API Patterns

Every API file in `src/api/*.ts` follows this pattern:

```ts
import { frappeRequest } from 'src/utils/csrf';

export interface MyDoc { name: string; field: string; modified: string; }

export async function fetchMyDocs(params) {
    const query = new URLSearchParams({
        doctype: 'Doctype Name',
        fields: JSON.stringify(['name', 'field', 'modified']),
        filters: JSON.stringify(filters),
        or_filters: JSON.stringify(or_filters),
        limit_start: String((params.page - 1) * params.page_size),
        limit_page_length: String(params.page_size),
        order_by: 'creation desc',
    });
    const [res, countRes] = await Promise.all([
        frappeRequest(`/api/method/frappe.client.get_list?${query}`),
        frappeRequest(`/api/method/company.company.frontend_api.get_permitted_count?doctype=...`),
    ]);
    return { data: data.message || [], total: countData.message || 0 };
}
```

**Key rules:**
- `modified` and `creation` are standard Frappe fields — always available, no backend changes needed
- Add `'modified'` to the `fields` array and `modified: string` to the TypeScript interface

---

## Date / Time Utilities (`src/utils/format-time.ts`)

| Function | Output | Use Case |
|----------|--------|----------|
| `fTimeDist(date)` | `"2 hours ago"` | Compact relative time in action cells |
| `fDate(date)` | `"17 Apr 2022"` | Short date |
| `fDateTime(date)` | `"17 Apr 2022 12:00 am"` | Full datetime |

Local fallback used in some list views:
```ts
function formatDatetime(val?: string) {
    if (!val) return '—';
    return new Date(val).toLocaleString();
}
```

---

## List View Pattern

All list views follow this structure:

```
TABLE_HEAD = [{ id, label, width?, align? }]
SORT_OPTIONS = [{ value: 'field_asc', label: '' }]

fetchData() → calls API, sets data[], total, loading
useEffect(() => fetchData(), [page, rowsPerPage, filterName, sortBy])

<DashboardContent>
  <Card>
    <Toolbar> Search + Sort </Toolbar>
    <Scrollbar>
      <Table>
        <ProposalTableHead headLabel={TABLE_HEAD} />
        <TableBody>
          {data.map(row => <TableRow> ... </TableRow>)}
        </TableBody>
      </Table>
    </Scrollbar>
    <TablePagination />
  </Card>
</DashboardContent>
```

**Reused shared components:**
- `TableNoData` from `src/sections/proposal/table-no-data`
- `Scrollbar`, `EmptyContent`, `Iconify` from `src/components/`
- `DashboardContent` from `src/layouts/dashboard`

---

## Filtering Pattern

### Standard Filters (From Date, To Date, Client/Vendor, Company/Account)
List views implement filter states using MUI components, mapping them to API requests:

```tsx
// State Hooks in Section Component
const [fromDate, setFromDate] = useState<dayjs.Dayjs | null>(null);
const [toDate, setToDate] = useState<dayjs.Dayjs | null>(null);
const [client, setClient] = useState<{ name: string; first_name: string } | null>(null);
const [account, setAccount] = useState<{ name: string; account_name: string } | null>(null);
```

### Owner Scoping Pattern (`has_crm_permission`)
For security and visibility control, reports must scope the records by user permissions if the user doesn't have CRM Manager roles:

```python
# Backend Python (crm_api.py / report.py)
has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
owner_val = filters.get("owner")

if has_permission:
    owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
    conditions.append("doc.owner = %(owner)s")
    params["owner"] = owner_filter
elif owner_val and owner_val != "all":
    conditions.append("doc.owner = %(owner)s")
    params["owner"] = owner_val
```

---

## Sorting Pattern

### Standard Sort Options
Sort states are managed using a shared `SORT_OPTIONS` constant:

```ts
const SORT_OPTIONS = [
    { value: 'creation_desc', label: 'Created (Latest)' },
    { value: 'creation_asc', label: 'Created (Oldest)' },
    { value: 'modified_desc', label: 'Modified (Latest)' },
    { value: 'modified_asc', label: 'Modified (Oldest)' },
    { value: 'date_desc', label: 'Date (Latest)' },
    { value: 'date_asc', label: 'Date (Oldest)' },
];
```

### Client / Server-side Handling
In client-side sorting:
```tsx
const dataFiltered = applyFilter({
    inputData: reportData,
    comparator: getComparator(order, orderBy),
    filterName,
});
```

---

## Pagination Pattern

Manage list pagination using standard MUI `TablePagination` hooks and configurations:

```tsx
const [page, setPage] = useState(0);
const [rowsPerPage, setRowsPerPage] = useState(10);

const onChangePage = useCallback((event: unknown, newPage: number) => {
    setPage(newPage);
}, []);

const onChangeRowsPerPage = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
}, []);

// Render Component
<TablePagination
    rowsPerPageOptions={[5, 10, 25]}
    component="div"
    count={totalRows}
    rowsPerPage={rowsPerPage}
    page={page}
    onPageChange={onChangePage}
    onRowsPerPageChange={onChangeRowsPerPage}
/>
```

---

## List / Table Rendering Pattern

### Checkbox Selection
```tsx
const [selected, setSelected] = useState<string[]>([]);

const handleSelectAllClick = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.checked) {
        const newSelected = reportData.map((n) => n.name);
        setSelected(newSelected);
        return;
    }
    setSelected([]);
};

const handleClick = (event: React.MouseEvent<unknown>, name: string) => {
    const selectedIndex = selected.indexOf(name);
    let newSelected: string[] = [];

    if (selectedIndex === -1) {
        newSelected = newSelected.concat(selected, name);
    } else if (selectedIndex === 0) {
        newSelected = newSelected.concat(selected.slice(1));
    } else if (selectedIndex === selected.length - 1) {
        newSelected = newSelected.concat(selected.slice(0, -1));
    } else if (selectedIndex > 0) {
        newSelected = newSelected.concat(
            selected.slice(0, selectedIndex),
            selected.slice(selectedIndex + 1)
        );
    }
    setSelected(newSelected);
};
```

### Table Layout & Sticky Styling
Ensure table layouts keep important fields contextually anchored:

```tsx
<TableContainer sx={{ overflow: 'unset' }}>
    <Table sx={{ minWidth: 800 }}>
        {/* Sticky Headers */}
        <TableHead sx={{ position: 'sticky', top: 0, zIndex: 2 }} />
        <TableBody>
            {/* Sticky Actions column */}
            <TableCell 
                align="right" 
                sx={{ 
                    position: 'sticky', 
                    right: 0, 
                    bgcolor: 'background.paper', 
                    boxShadow: (theme) => `-4px 0 8px ${theme.palette.divider}` 
                }}
            >
                {/* Actions */}
            </TableCell>
        </TableBody>
    </Table>
</TableContainer>
```

---

## Excel Export Pattern (ExcelJS)

All detailed reports use a unified ExcelJS generation structure:
1. **Grouped Rows**: Rows grouped by Document ID, displaying line items sequentially.
2. **Merged Column Blocks**: Vertically merge repeating parent-level fields (ID, Dates, Client, Totals, Bank details, Attachments, Owner) across the group's rows.
3. **Borders**: Dark black thin borders (`#000000`) applied to *every* coordinate inside merged cell groups to avoid gaps.
4. **Colors**: Uniform white background fill (`#FFFFFF`) on all data rows, with headers styled in bold white text over a solid blue/teal background (`#0ea5e9`).
5. **No Separator Rows**: Use a `medium` black bottom border on the last row of each document group to separate records instead of empty blank rows.
6. **Attachments Hyperlink**: Point to a signed whitelisted backend download URL (e.g. `download_estimation_attachment`), displaying the exact filename as link text.
7. **Column Auto-fit**: Loop over all columns to adjust width according to content length, applying explicit minimum widths to key text areas (e.g., Description: 25, Attachments: 15, Owner: 20).

```typescript
const workbook = new ExcelJS.Workbook();
const sheet = workbook.addWorksheet('Report');

// Row Grouping, Cell Merging, and Separator Borders
invoiceIdsOrdered.forEach((id) => {
    const items = groups[id];
    const startRow = currentRow;
    const endRow = startRow + items.length - 1;
    groupEndRows.push(endRow);

    items.forEach((item, itemIdx) => {
        const rowData = { ...item };
        // Populate parent fields on first row (itemIdx === 0) only to prevent Excel merge conflicts
        if (itemIdx > 0) {
            rowData.invoice_id = '';
            rowData.grand_total = '';
            // ...
        }
        sheet.addRow(rowData);
    });

    if (items.length > 1) {
        columnsToMerge.forEach((colIndex) => {
            sheet.mergeCells(startRow, colIndex, endRow, colIndex);
        });
    }
});

// Row styling loop applying thin borders, and medium separator borders at group ends
for (let r = 1; r <= sheet.rowCount; r++) {
    const isGroupEnd = groupEndRows.includes(r);
    for (let c = 1; c <= colCount; c++) {
        const cell = sheet.getRow(r).getCell(c);
        cell.border = {
            top: { style: 'thin', color: { argb: 'FF000000' } },
            bottom: { style: isGroupEnd ? 'medium' : 'thin', color: { argb: 'FF000000' } },
            left: { style: 'thin', color: { argb: 'FF000000' } },
            right: { style: 'thin', color: { argb: 'FF000000' } }
        };
    }
}
```

---

## PDF Export Pattern

### Hook Usage
We use a custom `usePdfExport` hook to handle PDF exports with loading and status indicators:

```tsx
const { exportingPdf, handleExportPdf } = usePdfExport();

// Call hook inside report view:
handleExportPdf(async () => {
    await generateInvoicePdf({
        data: reportData,
        filters: { fromDate, toDate, client },
    });
});
```

### Generator Alignment Rule
The fields and columns displayed in the generated PDF must **exactly match** the column configuration defined in the Excel export layout for uniformity.

---

## Export Field API Pattern

### Whitelisted Metadata Retrival
Dynamically retrieve DocType fields for column construction on the frontend while excluding hidden and layout elements. **Do not exclude read_only fields** as they contain calculated metrics (e.g. Total Tax, Amount to Pay, Amount Pending):

```python
# Backend Python (crm_api.py)
@frappe.whitelist()
def get_doctype_export_fields():
    meta = frappe.get_meta("My DocType")
    valid_fields = []

    valid_fields.append({
        "fieldname": "name",
        "label": "ID"
    })

    for field in meta.fields:
        is_allowed = field.fieldname in ("owner",)
        # Exclude only hidden and structural layout fields
        if is_allowed or (not field.hidden and field.fieldtype not in ("Table", "HTML", "Section Break", "Column Break", "Button", "Tab Break")):
            valid_fields.append({
                "fieldname": field.fieldname,
                "label": field.label
            })
    return valid_fields
```

---

## Summary Cards Pattern

### Summary Cards Grid
Rendered directly above the data tables, summary cards represent key metrics in real-time.

```tsx
// Grid Layout
<Grid container spacing={3} sx={{ mb: 3 }}>
    {summaryData.map((item) => (
        <Grid item xs={12} sm={6} md={3} key={item.label}>
            <SummaryCard 
                title={item.label} 
                value={item.value} 
                icon={item.icon} 
                color={item.color} 
            />
        </Grid>
    ))}
</Grid>
```

### Summary Response Shape
The `report_summary` Python API response is represented as a structured dictionary matching:

```json
[
  {
    "label": "Total Amount",
    "value": 150000.0,
    "datatype": "Currency"
  },
  {
    "label": "Total Invoices",
    "value": 24,
    "datatype": "Int"
  }
]
```

### Icons and Colors Map
Client-side mapping parses metric labels to choose representative Iconify symbols and themed MUI accent colors:

```typescript
const getIcon = (label: string) => {
    const l = label.toLowerCase();
    if (l.includes('total') || l.includes('amount')) return 'solar:wad-of-money-bold';
    if (l.includes('pending') || l.includes('balance')) return 'solar:clock-circle-bold';
    if (l.includes('collected') || l.includes('paid')) return 'solar:check-circle-bold';
    return 'solar:document-bold';
};
```

---

## Meta Integration Module

| Doctype | Section | API |
|---------|---------|-----|
| CRM Meta App | `sections/meta-app` | `api/meta-app.ts` |
| CRM Meta Page | `sections/meta-page` | `api/meta-page.ts` |
| CRM Meta Form | `sections/meta-form` | `api/meta-form.ts` |
| CRM Meta Lead | `sections/meta-lead` | `api/meta-lead.ts` |
| CRM Meta Queue | `sections/meta-queue` | `api/meta-queue.ts` |
| CRM Meta Webhook Log | `sections/meta-webhook-log` | `api/meta-webhook-log.ts` |

### Meta Lead Fields
`name, meta_lead_id, meta_app, meta_page, meta_form, campaign_name, ad_set_name, ad_name, webhook_payload, lead_json, received_time, processed_time, processing_status, retry_count, error_message, created_lead, creation, modified`

### Meta Queue Fields
`name, meta_lead, job_id, status, attempts, started, completed, last_error, creation, modified`

### Meta Webhook Log Fields
`name, headers, payload, response, http_status, execution_time, retry_count, status, creation, modified`

### Status Badge Pattern
```ts
const STATUS_COLORS: Record<string, { bg: string; border: string; color: string }> = {
    Success:  { bg: 'rgba(34,197,94,0.15)',  border: 'rgba(34,197,94,0.35)',  color: '#15803d' },
    Failed:   { bg: 'rgba(239,68,68,0.15)',  border: 'rgba(239,68,68,0.35)',  color: '#b91c1c' },
    Pending:  { bg: 'rgba(245,158,11,0.15)', border: 'rgba(245,158,11,0.35)', color: '#92400e' },
    Queued:   { bg: 'rgba(156,163,175,0.15)',border: 'rgba(156,163,175,0.35)',color: '#374151' },
};
// Cell:
<Box sx={{ bgcolor: sc.bg, border: `1px solid ${sc.border}`, color: sc.color, fontWeight: 700, fontSize: 11, textTransform: 'uppercase', borderRadius: '6px', padding: '4px 10px', display: 'inline-flex', alignItems: 'center' }}>
    {row.status}
</Box>
```

### Modified Time Display Convention
Show as compact relative time next to the action icon (not as a separate column):
```tsx
import { fTimeDist } from 'src/utils/format-time';

// Inside Actions TableCell, before the IconButton:
<Box sx={{ typography: 'body2', color: 'text.secondary', fontWeight: 700, mr: 1, fontSize: 12, whiteSpace: 'nowrap', pt: 1 }}>
    {fTimeDist(row.modified)}
</Box>
```

---

## KeyValueTable (meta-lead-details-view.tsx)

Parses JSON payloads into table or raw view toggle.
- Handles `"prefix message: {...}"` — splits into Response Message row + parsed JSON rows
- Facebook `field_data` arrays extracted as flat key-value rows
- Toggle: pill-style `ToggleButtonGroup` with `bgcolor: '#00a5d1'` for active state

---

## Common Commands

> [!IMPORTANT]
> **Git Command Consent Policy**: Always explicitly ask the user for permission before running any `git` commands (e.g. `git add`, `git commit`, `git push`, `git pull`). Do not run them automatically.

```bash
# Frontend
cd apps/company/company/frontend && npm run dev
npx tsc --noEmit   # type check

# Backend
cd com-bench && bench start
```

---

## Coding Conventions

- MUI `sx` prop for all styling — no CSS files in sections
- `alpha(theme.palette.primary.main, 0.08)` for soft backgrounds
- `borderRadius: 1.5` for cards, `borderRadius: '6px'` for status badges
- Index circle: 28×28px, `borderRadius: '50%'`, primary color at 8% opacity
- Empty value fallback: `'—'` (em-dash, not dash or N/A)
- Icons: `solar:` prefix from Iconify (e.g. `solar:eye-bold`, `solar:code-bold`)
- Meta brand icon: `logos:meta-icon` width=22
- Brand color: `#08a3cd` (used for icon accents and active toggles `#00a5d1`)

---

## Backend API Reference

### Table of Contents
- [company/api.py](#companyapipy)
- [company/crm_api.py](#companycrm_apipy)
- [company/crm_meta_api.py](#companycrm_meta_apipy)
- [company/crm_whatsapp_api.py](#companycrm_whatsapp_apipy)
- [company/crm_whatsapp_webhook.py](#companycrm_whatsapp_webhookpy)
- [company/employee_remainder_api.py](#companyemployee_remainder_apipy)
- [company/evaluation_automation.py](#companyevaluation_automationpy)
- [company/frontend_api.py](#companyfrontend_apipy)
- [company/presence_api.py](#companypresence_apipy)
- [company/reminders.py](#companyreminderspy)
- [company/workflow_utils.py](#companyworkflow_utilspy)

---

### company/api.py
- **Purpose**: General HRMS & CRM utility APIs (FCM push notifications, leave validations, holiday populating, leave checks, dashboard stats).
- **Key Whitelisted Endpoints**:
  - `get_next_estimation_preview()`: returns next estimation reference ID preview.
  - `get_next_invoice_preview()`: returns next invoice reference ID preview.
  - `check_leave_balance(employee, leave_type, from_date, to_date, permission_hours, half_day)`: checks leaf balance validations.
  - `auto_allocate_monthly_leaves(year, month)`: allocates monthly leaves.
  - `save_fcm_token(token)`: saves FCM token on the logged-in User.
- **Helper/Internal Functions**:
  - `update_invoice_received_balance(doc, method)`: Invoice hook.
  - `update_purchase_paid_balance(doc, method)`: Purchase hook.
  - `validate_leave_balance(doc, method)`: Leave validation hook.
  - `_send_v1_message_to_token(token, title, body, data)`: FCM HTTP v1 push notifier.
- **DocTypes Touched**: `Estimation`, `Invoice`, `Purchase`, `Leave Application`, `Leave Allocation`, `Holiday List`, `User`.
- **Patterns**: DocType hook triggers for computing outstanding balances; push notification tokens storing on User.
- **Dependencies**: Imports from `presence_api` and `employee_remainder_api`.

### company/crm_api.py
- **Purpose**: Core CRM export APIs (Leads, Contacts, Accounts, Proposals, Estimations, Invoices, Purchases), cell merging, attachments token validation.
- **Key Whitelisted Endpoints**:
  - `get_estimation_export_data(filters)`: returns estimation line-item rows with signed attachment tokens.
  - `download_estimation_attachment(file_path, token)`: downloads estimation attachment via guest URL validation.
  - `get_invoice_export_data(filters)`: returns invoice line-item rows.
  - `get_purchase_export_data(filters)`: returns purchase line-item rows.
  - `download_invoice_attachment(file_path, token)` / `download_purchase_attachment(file_path, token)`: secure downloads.
- **Helper/Internal Functions**:
  - `_make_file_token(file_id)`: MD5 hash generator for file authorization.
  - `sync_event_to_call(doc, method)` / `sync_event_to_meeting(doc, method)`: calendar sync hooks.
- **DocTypes Touched**: `Lead`, `Contacts`, `Accounts`, `Meeting`, `Calls`, `ToDo`, `Proposal`, `Deal`, `Estimation`, `Invoice`, `Purchase`.
- **Patterns**: Signed-token whitelisting signature check for secure file serving to local Excel clients.

### company/crm_meta_api.py
- **Purpose**: Facebook Lead Ads Webhook integration to parse received payload and auto-create leads.
- **Key Whitelisted Endpoints**:
  - `webhook()`: unified meta webhook verification and payload receiver.
- **Helper/Internal Functions**:
  - `enqueue_webhook_lead_processing(payload_data, webhook_log_name)`: enqueues Meta Lead payload parser.
  - `process_meta_lead_job(meta_lead_name, queue_job_name)`: background Meta API crawler.
- **DocTypes Touched**: `CRM Meta Webhook Log`, `CRM Meta Lead`, `CRM Meta Queue`, `Lead`.
- **Patterns**: Background job enqueueing (`frappe.enqueue`); Meta HMAC signature payload validation.

### company/crm_whatsapp_api.py
- **Purpose**: WhatsApp Messaging APIs (connection test, message sending, message count, file download).
- **Key Whitelisted Endpoints**:
  - `send_whatsapp(phone, message, attachment)`: sends a WhatsApp message via integration.
  - `get_whatsapp_messages(phone, start, limit)`: fetches conversation history.
  - `get_monthly_message_count()`: retrieves WhatsApp usage stats.
- **Helper/Internal Functions**:
  - `get_temporary_file_url(file_doc)`: resolves actual file path url.
- **DocTypes Touched**: `CRM Whatsapp Message`, `CRM Whatsapp Conversation`, `File`.
- **Patterns**: Third-party API payload posting with token authentication.

### company/crm_whatsapp_webhook.py
- **Purpose**: Meta WhatsApp incoming message webhooks mapping payload to CRM.
- **Key Whitelisted Endpoints**:
  - `webhook()`: incoming webhook listener.
- **Helper/Internal Functions**:
  - `get_or_create_conversation(phone)`: fetches active chat.
  - `create_message(...)`: maps payload to CRM Whatsapp Message.
  - `update_message_status(...)`: message state updater.
- **DocTypes Touched**: `CRM Whatsapp Conversation`, `CRM Whatsapp Message`.
- **Patterns**: Request verification checks; realtime database upserts from public webhook.

### company/employee_remainder_api.py
- **Purpose**: Reminder schedule and trigger API (manual + HR configured reminders, notifications trigger, recurring reminder checks).
- **Key Whitelisted Endpoints**:
  - `get_my_reminders()`: retrieves manual reminders.
  - `save_remainder(data)`: creates/saves reminder.
  - `get_hr_reminders_paginated(params)`: paginated HR reminder configs.
- **Helper/Internal Functions**:
  - `check_and_enqueue_reminders(hr_reminder_name)`: recurring cron scheduler.
  - `process_remainder_queue()`: dequeues and fires due alerts.
  - `send_remainder_notification(queue_name)`: triggers chat message.
- **DocTypes Touched**: `Remainder Queue`, `HR Remainder Configuration`, `Employee`.
- **Patterns**: Recurring cron-based background queue processor checking schedules.
- **Dependencies**: Imports from `presence_api` and `api`.

### company/evaluation_automation.py
- **Purpose**: Automation rules for Employee Evaluation (Late Login, Early Exit, Task Automation, daily logs, leave automation).
- **Key Whitelisted Endpoints**: None (Triggered via DocType hook listeners).
- **Helper/Internal Functions**:
  - `trigger_evaluation_automation(...)`: matches automation rules and creates evaluations.
  - `_create_automated_evaluation(...)`: creates Employee Evaluation.
  - `handle_attendance_automation(doc, method)`: maps in/out times to late/early rules.
- **DocTypes Touched**: `Employee Evaluation`, `Employee Attendance`, `Task`, `Employee Session`.
- **Patterns**: Evaluation metrics auto-generation via automated HR rules on check-in/out updates.

### company/frontend_api.py
- **Purpose**: Frontend UI helpers (permitted document count, mobile logins, user permissions, CRM & Sales dashboard stats, workflow actions).
- **Key Whitelisted Endpoints**:
  - `get_permitted_count(doctype, filters, or_filters)`: returns count of readable records.
  - `update_doc_status(doctype, name, workflow_state, update_data)`: modifies document workflow state.
  - `get_dashboard_stats(start_date, end_date)`: returns CRM statistics.
  - `get_financial_totals(start_date, end_date)`: returns financial summaries.
- **DocTypes Touched**: All major Transactional DocTypes (`Lead`, `Deal`, `Proposal`, `Estimation`, `Invoice`, `Purchase`).
- **Patterns**: Permitted document checking via standard SQL count and SQL aggregation for financial cards.

### company/presence_api.py
- **Purpose**: Real-time session presence tracking (login/logout, idle ping, breaks, detailed session interval mapping, geotagging).
- **Key Whitelisted Endpoints**:
  - `update_presence(status, employee, status_message, source, start_time)`: transitions state.
  - `ping_presence(employee)`: heartbeat mechanism.
  - `log_location(latitude, longitude, ...)`: geotagging log.
  - `force_offline_all()`: sets all active sessions to Offline.
- **Helper/Internal Functions**:
  - `create_session(employee, now, status)`: creates Employee Session.
  - `close_session(session, now)`: closes session.
  - `process_auto_breaks()`: background job migrating idle users to Break state.
- **DocTypes Touched**: `Employee Session`, `Employee Session Interval`, `Employee Session Break`, `Location Log`.
- **Patterns**: Real-time websocket notifications; heartbeat pinging intervals (usually 60s).
- **Dependencies**: Imports from `employee_remainder_api` and `api`.

### company/reminders.py
- **Purpose**: Call and Meeting reminder email queues and schedulers.
- **Key Whitelisted Endpoints**:
  - `force_send_call_queue(queue_name)`: forces immediate reminder execution.
  - `delete_call_reminder_queue(call_name)`: drops call alerts.
- **Helper/Internal Functions**:
  - `create_or_update_call_queue(call)`: syncs queue.
  - `run_email_reminders()`: scheduled job processing due reminders.
- **DocTypes Touched**: `Reminder Queue`, `Calls`, `Meeting`.
- **Patterns**: Auto-cleanup of queues on document deletion (`delete_reminders_and_linked_events`).

### company/workflow_utils.py
- **Purpose**: Programmatic creation and updating of workflows (Lead Workflow, Leave Application Workflow, WFH Attendance, Reimbursement, Request).
- **Key Whitelisted Endpoints**:
  - `update_lead_workflow()`: populates state transitions.
  - `create_reimbursement_workflow()`: bootstraps reimbursement rules.
  - `create_leave_application_workflow()`: bootstraps leave rules.
- **DocTypes Touched**: `Workflow`, `Workflow State`, `Workflow Transition`.
- **Patterns**: Programmatic bootstrapping of ERPNext workflow engines.


---

## HRMS Module

### Workspace Paths

```
com-bench/apps/company/
  company/doctype/                # HR DocTypes (Employee, Attendance, Leave, Session, etc.)
  frontend/src/
    api/
      employees.ts                # Employee management API calls
      attendance.ts               # Attendance check-in / timesheets APIs
      leaves.ts                   # Leave Application & Allocation APIs
      employee-evaluation.ts      # Automated rule-based evaluations
      reimbursement-claims.ts     # Claims & reimbursement workflow APIs
      holiday-lists.ts            # Holiday calendars management
    sections/
      employee/                   # Directory for Employee lists, profiles & details
      attendance/                 # Monthly attendance grids & check-in timeline maps
      leaves/                     # Leave requests, carry-forward, and allocations
      employee-evaluation/        # Late login / early exit evaluations dashboards
      reimbursement-claims/       # Claim approvals and attachment lists
      wfh-attendance/             # Work From Home check-in maps & location grids
      requests/                   # Custom general requests submissions
```

---

### Key Doctypes

#### 1. Employee
- **Key Fields**: `name` (ID), `first_name`, `last_name`, `date_of_birth`, `date_of_joining`, `status` (Active, Left, Suspended), `gender`, `department`, `designation`, `probation_period`, `user_id`.

#### 2. Attendance
- **Key Fields**: `name`, `employee`, `date`, `status` (Present, Absent, Half Day), `in_time`, `out_time`, `working_hours`, `late_entry` (Check), `early_exit` (Check).

#### 3. Leave Application
- **Key Fields**: `name`, `employee`, `leave_type`, `from_date`, `to_date`, `half_day`, `reason`, `workflow_state` (Draft, Approved, Rejected, Pending Approval).

#### 4. Leave Allocation
- **Key Fields**: `name`, `employee`, `leave_type`, `from_date`, `to_date`, `total_allocated_leaves`, `carry_forward` (Check).

#### 5. Employee Session
- **Key Fields**: `name`, `employee`, `login_time`, `logout_time`, `status` (Active, Idle, Away, Offline), `working_hours`, `break_hours`, `intervals` (Child Table), `breaks` (Child Table).

#### 6. Employee Evaluation
- **Key Fields**: `name`, `employee`, `evaluation_date`, `rating`, `feedback`, `rule_name` (Late Login, Early Exit, etc.), `status` (Draft, Submitted).

#### 7. Reimbursement Claim
- **Key Fields**: `name`, `employee`, `claim_date`, `amount`, `expense_type`, `receipt` (Attach), `workflow_state`.

#### 8. Holiday List
- **Key Fields**: `name`, `holiday_list_name`, `from_date`, `to_date`, `holidays` (Child Table: `holiday_date`, `description`, `weekly_off`).

#### 9. HR Remainder Configuration
- **Key Fields**: `name`, `remainder_name`, `reminder_type` (Timesheet, Daily Log), `frequency`, `scheduled_time`, `message_content`.

---

### List View & Report Patterns Specific to HR

#### Monthly Overview Grid
Attendance uses a specialized Monthly calendar grid showing color-coded daily check-in nodes:
- Uses the `/api/method/company.company.api.get_month_calendar_data` API.
- Each date cell displays actual `in_time` / `out_time`, total working duration, and leave overlays.

#### WFH Check-in Map Layout
WFH Attendance and Location Logs render custom OpenStreetMap/Leaflet components:
- Grabs latitude/longitude logs from location API.
- Pinpoints check-in coordinates on maps, keeping filters bounded by `employee` and `date`.

#### Shared Export / Table Rendering
All HR tables (Leaves list, Employee grid, Reimbursement lists) leverage the standard MUI `TablePagination`, `SORT_OPTIONS`, and dynamic `get_doctype_export_fields` patterns.

---

### Automation & Background Jobs

#### Presence Ping (Heartbeat)
- **Presence Heartbeat**: Ping request sent every 60s via `/api/method/company.company.presence_api.ping_presence`.
- **Idle Migration**: Schedulers analyze user idle time, triggering `process_auto_breaks()` background job to move inactive users to Away or Break states.

#### Scheduled Reminders
- **Cron Jobs**: `daily` scheduled check `send_daily_timesheet_reminders()` inside `reminders.py`.
- **Queueing**: Reminders are calculated and appended to `Remainder Queue` using `check_and_enqueue_reminders()`, checking against `is_already_enqueued_today()`.

#### Evaluation Rules
Evaluations are auto-generated on DocType event hooks using `evaluation_automation.py`:
- `Attendance` updates hook into `handle_attendance_automation(...)` to check for `_check_late_login()` or `_check_early_exit()`.
- `Leave Application` submission hooks into `handle_leave_automation(...)` to log evaluation rules.

---

### Workflow Integration

#### Bootstrapping Transitions
All HR workflows (Leave Application, WFH Attendance, Reimbursement Claims) are programmatically registered via `workflow_utils.py`:
- E.g., `create_leave_application_workflow()` sets transition permissions from `Pending HR Approval` -> `Approved` or `Rejected` for users with `HR Manager` roles.

#### Frontend Actions Rendering
- **Actions Bar**: The frontend queries `get_workflow_states(doctype, current_state)` to fetch transition buttons.
- **State Change**: Clicking triggers `/api/method/company.company.frontend_api.apply_workflow_action` passing `doctype`, `name`, `action`, and optional comments.

---

### HR-Specific UI Conventions

#### Status Badge Color Rules
```ts
const ATTENDANCE_STATUS_COLORS: Record<string, string> = {
    Present: '#22c55e',   // Green
    Absent: '#ef4444',    // Red
    'Half Day': '#eab308', // Yellow
    Leave: '#3b82f6',     // Blue
    Holiday: '#9ca3af',   // Grey
};
```

#### Progress Circular Gauges
Leave views utilize custom circular SVGs indicating `Leaves Taken` / `Total Leaves` with colored progress thresholds (red on near-limit).

