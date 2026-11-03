# Expense Claim status meanings

Four native values answer different questions:

| Field | Meaning |
|---|---|
| `docstatus` | Draft (0), Submitted (1), or Cancelled (2). |
| Workflow state | The currently configured custom workflow stage, when a workflow is active. |
| `approval_status` | The HRMS approval decision. |
| `status` | HRMS's derived claim/accounting status, such as Paid, Unpaid, Rejected, or Cancelled. |

Submitted does not automatically mean approved or paid. A payment mode or `is_paid` value on an unsubmitted draft is not proof of a posted payment. A rejected claim with a zero net amount is not thereby paid.

## Placement in My Work

| Condition | Placement |
|---|---|
| Owned claim or readable claim for the Employee linked to the User | My Requests and its status category. |
| Actionable configured workflow step with a real pending action | My Approvals, subject to native transition checks. |
| Directly designated approver with a permitted native draft submission | Actionable native approval work. |
| Approved, Submitted, and Unpaid | Waiting on Others. |
| Paid with no required workflow action remaining | Completed. |
| Paid and fully adjusted against an advance | Completed; settlement reflects the advance. |
| Native rejection decision/status | Rejected. |
| Cancelled | Cancelled, separately from rejection. |
| Draft / Submitted | Separate submission-stage views, independent of payment. |

Counts and discovery are limited by the selected date and record-loading scope. All Work includes related readable history within that scope; approver roles alone do not expose every claim.

The main list shows a current system state and available actions. Review provides the separate recorded values, financial totals and conflict details when relevant. Claim Amount comes from `total_claimed_amount`; `grand_total` is the net sanctioned/taxed amount after advance allocation.

## Conflicts and changes

Contradictory workflow/native decisions are reported rather than silently repaired. A no-op transition is not presented as a fresh Expense Claim approval unless its configured task or effective update makes it meaningful. Native workflow services, conditions, self-approval rules and validations remain authoritative.

Without a custom workflow, an authorized editor saves the native approval decision before Submit; HRMS requires Approved or Rejected. With a workflow that manages the decision, use the configured actions. Cancellation and accounting/advance reversals remain native operations.
