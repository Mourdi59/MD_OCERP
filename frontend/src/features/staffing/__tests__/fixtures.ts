// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Builders for the staffing tests. Each returns a complete object of the API
// shape with neutral defaults, so a test states only what it is about.

import type {
  Can,
  Compliance,
  FileDocument,
  Fill,
  Handover,
  PersonnelFile,
  PersonnelFileRow,
  Position,
  StaffingCatalogue,
  StaffingPlan,
  Upcoming,
} from '../api';

/** A capability the server allows. */
export const yes: Can = { allowed: true, reason: null };

/** A capability the server refuses, with its reason code. */
export function no(reason: string): Can {
  return { allowed: false, reason };
}

export function catalogue(over: Partial<StaffingCatalogue> = {}): StaffingCatalogue {
  return {
    id: 'neutral',
    version: 1,
    name_key: 'staffing.catalogue.neutral.name',
    labels: null,
    review_status: 'unconfirmed',
    organisations: [
      { code: 'owner_project_lead', name_key: 'staffing.organisation.owner_project_lead', labels: null },
      { code: 'operator', name_key: 'staffing.organisation.operator', labels: null },
    ],
    roles: [
      {
        code: 'project_manager',
        name_key: 'staffing.role.project_manager',
        labels: null,
        organisation: 'owner_project_lead',
        phases: ['development', 'execution'],
        default_fte: '1',
        key_role: true,
        required_before: 'construction_start',
        required_document_kinds: ['employment_contract'],
        handover_role: true,
      },
      {
        code: 'site_manager',
        name_key: 'staffing.role.site_manager',
        labels: null,
        organisation: 'owner_project_lead',
        phases: ['execution'],
        default_fte: '1',
        key_role: true,
        required_before: null,
        required_document_kinds: ['employment_contract', 'safety_training'],
        handover_role: false,
      },
      {
        code: 'operator_plant_manager',
        name_key: 'staffing.role.operator_plant_manager',
        labels: null,
        organisation: 'operator',
        phases: ['operation'],
        default_fte: '1',
        key_role: true,
        required_before: null,
        required_document_kinds: [],
        handover_role: false,
      },
    ],
    document_kinds: [
      {
        code: 'employment_contract',
        name_key: 'staffing.document_kind.employment_contract',
        labels: null,
        credential_type: 'employment_contract',
        special_category: false,
        store_number: false,
        retention_rule: 'neutral_assignment_24m',
      },
      {
        code: 'work_permit',
        name_key: 'staffing.document_kind.work_permit',
        labels: null,
        credential_type: 'work_permit',
        special_category: false,
        store_number: true,
        retention_rule: 'neutral_assignment_24m',
      },
      {
        code: 'safety_training',
        name_key: 'staffing.document_kind.safety_training',
        labels: null,
        credential_type: 'training',
        special_category: false,
        store_number: false,
        retention_rule: 'neutral_assignment_24m',
      },
      {
        code: 'health_certificate',
        name_key: 'staffing.document_kind.health_certificate',
        labels: { en: 'Health certificate' },
        credential_type: 'occupational_health',
        special_category: true,
        store_number: false,
        retention_rule: 'neutral_assignment_24m',
      },
    ],
    leave_types: [{ code: 'annual', name_key: 'staffing.leave_type.annual', labels: null }],
    ...over,
  };
}

export function plan(over: Partial<StaffingPlan> = {}): StaffingPlan {
  return {
    id: 'plan-1',
    project_id: 'p1',
    catalogue_source: 'shipped',
    catalogue_id: 'neutral',
    catalogue_version: 1,
    status: 'draft',
    requires_accommodation: false,
    commissioning_date: '2027-12-01',
    governance_document_id: null,
    submitted_by: null,
    submitted_at: null,
    approved_by: null,
    approved_at: null,
    approval_source: null,
    has_bound_snapshot: false,
    can: { manage: yes, assign_owner: yes },
    ...over,
  };
}

export function fill(over: Partial<Fill> = {}): Fill {
  return {
    id: 'fill-1',
    position_id: 'pos-1',
    roster_member_id: 'rm-1',
    name: 'Dana Weber',
    fte_share: '1.00',
    from_date: '2026-09-01',
    to_date: null,
    status: 'confirmed',
    cleared_to_work: true,
    ...over,
  };
}

export function position(over: Partial<Position> = {}): Position {
  return {
    id: 'pos-1',
    role_code: 'project_manager',
    custom_label: null,
    organisation: 'owner_project_lead',
    phase: 'execution',
    title: null,
    fte: '1.00',
    headcount: 1,
    entry_date: '2026-09-01',
    exit_date: null,
    required_before: null,
    key_role: true,
    handover_role: true,
    status: 'open',
    stored_status: 'open',
    recruiting_channel: null,
    owner_user_id: null,
    resource_request_id: null,
    notes: null,
    covered_fte: '0',
    fills: [],
    can: { gate_fields: yes },
    ...over,
  };
}

export function handover(over: Partial<Handover> = {}): Handover {
  return {
    id: 'ho-1',
    from_fill_id: 'fill-1',
    to_position_id: 'pos-2',
    overlap_days: 30,
    scope: 'Open punch items and the commissioning sequence.',
    status: 'planned',
    ...over,
  };
}

export function fileRow(over: Partial<PersonnelFileRow> = {}): PersonnelFileRow {
  return {
    id: 'file-1',
    roster_member_id: 'rm-1',
    name: 'Dana Weber',
    roles: ['project_manager'],
    start: '2026-09-01',
    end: null,
    cleared_to_work: true,
    status: 'active',
    can: { open: yes },
    ...over,
  };
}

export function fileDocument(over: Partial<FileDocument> = {}): FileDocument {
  return {
    id: 'doc-1',
    document_kind: 'employment_contract',
    required: true,
    status: 'active',
    issued_at: '2026-08-01',
    valid_until: null,
    number_last4: null,
    recorded_by: null,
    verified_by: null,
    verified_at: null,
    waived: false,
    waiver_rationale: '',
    fit_for_role: null,
    special_category: false,
    can: { verify: yes },
    ...over,
  };
}

/** The flags of an active file as its line manager gets them. */
export function fileCan(over: Partial<PersonnelFile['can']> = {}): PersonnelFile['can'] {
  return {
    edit: yes,
    end: yes,
    hold: no('file_not_ended'),
    release: no('file_not_held'),
    erase: yes,
    export: no('own_file_only'),
    ...over,
  };
}

/** The flags of a file the caller may read and nothing else. */
export function fileCanNothing(reason: string): PersonnelFile['can'] {
  const refused = no(reason);
  return { edit: refused, end: refused, hold: refused, release: refused, erase: refused, export: no('own_file_only') };
}

export function personnelFile(over: Partial<PersonnelFile> = {}): PersonnelFile {
  return {
    id: 'file-1',
    roster_member_id: 'rm-1',
    name: 'Dana Weber',
    employer_organisation: 'Owner organisation',
    employment_basis: 'employee',
    nationality_required: false,
    lawful_basis: 'contract',
    status: 'active',
    ended_on: null,
    retention_due_at: null,
    hold_rationale: null,
    anonymised_at: null,
    roles: ['project_manager'],
    start: '2026-09-01',
    end: null,
    cleared_to_work: true,
    missing: [],
    expired: [],
    documents: [fileDocument()],
    accommodation: [],
    travel: [],
    leave: [],
    warnings: [],
    can: fileCan(),
    ...over,
  };
}

export function compliance(over: Partial<Compliance> = {}): Compliance {
  return {
    document_kinds: ['employment_contract', 'work_permit'],
    items: [
      {
        roster_member_id: 'rm-1',
        name: 'Dana Weber',
        roles: ['project_manager'],
        file_id: 'file-1',
        cleared_to_work: true,
        cells: { employment_contract: { state: 'valid' }, work_permit: { state: 'not_required' } },
      },
      {
        roster_member_id: 'rm-2',
        name: 'Ilya Novak',
        roles: ['site_manager'],
        file_id: 'file-2',
        cleared_to_work: false,
        cells: { employment_contract: { state: 'missing' }, work_permit: { state: 'expiring', days: 20 } },
      },
    ],
    total: 2,
    ...over,
  };
}

export function upcoming(over: Partial<Upcoming> = {}): Upcoming {
  return {
    expiring: [
      {
        file_id: 'file-2',
        name: 'Ilya Novak',
        document_kind: 'work_permit',
        valid_until: '2026-11-01',
        days: 20,
        status: 'expiring_soon',
        bucket: 30,
      },
    ],
    mobilisations: [],
    leave: [],
    ...over,
  };
}
