// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Every word the economics screens show, as a message key and the English it
// stands for. Keys are written out in full so the locale gates can see them.

import type { FlowKind, PlanStatus, SourceKind } from './api';

/** A message key and the English it stands for, handed to `t` as `defaultValue`. */
export type KeyText = readonly [key: string, english: string];

export const PLAN_STATUS: Record<PlanStatus, KeyText> = {
  draft: ['economics.status.draft', 'Draft'],
  proposed: ['economics.status.proposed', 'Proposed, waiting for the gate'],
  approved: ['economics.status.approved', 'Approved'],
  reopened: ['economics.status.reopened', 'Reopened for a change'],
};

export const FLOW_KIND: Record<FlowKind, KeyText> = {
  investment: ['economics.flow.investment', 'Investment'],
  revenue: ['economics.flow.revenue', 'Revenue or benefit'],
  operating_cost: ['economics.flow.operating_cost', 'Operating cost'],
  residual: ['economics.flow.residual', 'Residual value'],
};

export const SOURCE_KIND: Record<SourceKind, KeyText> = {
  equity: ['economics.source.equity', 'Equity'],
  shareholder_loan: ['economics.source.shareholder_loan', 'Shareholder loan'],
  bank_loan: ['economics.source.bank_loan', 'Bank loan'],
  bond: ['economics.source.bond', 'Bond'],
  grant: ['economics.source.grant', 'Grant'],
  subsidy: ['economics.source.subsidy', 'Subsidy'],
  sale_proceeds: ['economics.source.sale_proceeds', 'Sale proceeds'],
  other: ['economics.source.other', 'Other'],
};

export const FINDING: Record<string, KeyText> = {
  discount_rate_missing: ['economics.finding.discount_rate_missing', 'No discount rate is set, so the net present value cannot be computed.'],
  no_investment: ['economics.finding.no_investment', 'The business case has no investment line.'],
  no_benefit: ['economics.finding.no_benefit', 'The business case states no revenue or benefit.'],
  cash_flow_years_invalid: ['economics.finding.cash_flow_years_invalid', 'A line ends before it starts: {{ref}}.'],
  cash_flow_outside_horizon: ['economics.finding.cash_flow_outside_horizon', 'A line runs beyond the horizon, and the money after it is ignored: {{ref}}.'],
  frame_empty: ['economics.finding.frame_empty', 'The cost frame has no lines.'],
  frame_lines_overlap: ['economics.finding.frame_lines_overlap', 'Two frame lines overlap, so a cost would be counted twice: {{ref}}.'],
  frame_zero_amount: ['economics.finding.frame_zero_amount', 'A frame line has no budget: {{ref}}.'],
  estimate_over_frame: ['economics.finding.estimate_over_frame', 'The estimate is above the frame for {{ref}}.'],
  estimate_unassigned: ['economics.finding.estimate_unassigned', 'Part of the estimate sits under no frame line.'],
  markups_over_allowance: ['economics.finding.markups_over_allowance', 'The markups of the estimate exceed the allowance of the frame.'],
  no_bill: ['economics.finding.no_bill', 'The project has no bill of quantities to compare with.'],
  several_bills: ['economics.finding.several_bills', 'The project has several bills; choose the one the frame is compared with.'],
  currency_mismatch: ['economics.finding.currency_mismatch', 'The bill is in another currency than the plan.'],
  committed_over_frame: ['economics.finding.committed_over_frame', 'Commitments exceed the frame for {{ref}}.'],
  committed_unassigned: ['economics.finding.committed_unassigned', 'Part of the commitments sits under no frame line.'],
  committed_unknown: ['economics.finding.committed_unknown', 'The project has no cost lines, so commitments are not known.'],
  financing_shortfall: ['economics.finding.financing_shortfall', 'The sources of finance do not cover the investment.'],
  no_sources: ['economics.finding.no_sources', 'No source of finance is entered.'],
  tranches_differ_from_source: ['economics.finding.tranches_differ_from_source', 'The tranches of a source do not add up to its amount: {{ref}}.'],
  source_without_tranches: ['economics.finding.source_without_tranches', 'A source has no tranches: {{ref}}.'],
  grant_over_award: ['economics.finding.grant_over_award', 'A grant is entered above what its application was awarded: {{ref}}.'],
  grant_without_application: ['economics.finding.grant_without_application', 'A grant is not linked to a funding application: {{ref}}.'],
  investment_below_frame: ['economics.finding.investment_below_frame', 'The investment in the business case is below the cost frame.'],
};

export const BLOCK: Record<string, KeyText> = {
  invalid_transition: ['economics.block.invalid_transition', 'The plan is not in a state that allows this.'],
  plan_has_errors: ['economics.block.plan_has_errors', 'Fix the open errors first.'],
  approved_by_gate_decision: ['economics.block.approved_by_gate_decision', 'This project uses gates: the gate decision approves the plan.'],
  four_eyes_proposer_is_approver: ['economics.block.four_eyes_proposer_is_approver', 'Four-eyes: the person who proposed the plan cannot approve it.'],
  carrier_missing: ['economics.block.carrier_missing', 'No frame document of the governance model carries the economics.'],
};
