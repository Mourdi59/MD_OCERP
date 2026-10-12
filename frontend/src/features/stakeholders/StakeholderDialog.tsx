// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Adding a stakeholder to the register, or editing one. A stakeholder is
// either a contact from the address book or a named group (the neighbours of
// a street, a works council); the category comes from the pinned framework.

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/shared/ui/Button';
import { ContactSearchInput } from '@/shared/ui/ContactSearchInput';
import { ProjectPeopleSelect } from '@/shared/ui/ProjectPeopleSelect';
import { WideModal, WideModalField, WideModalSection } from '@/shared/ui/WideModal';

import { createStakeholder, updateStakeholder, type Stakeholder, type StakeholderInput } from './api';
import { FIELD_CLASS, RefusalBox, useWrite } from './StakeholderBits';
import { STAKEHOLDER_STATUS, itemName, vocab } from './labels';
import type { Screen } from './screen';

export interface StakeholderDialogProps {
  screen: Screen;
  /** The stakeholder to edit, or null to add one. */
  stakeholder: Stakeholder | null;
  onClose: () => void;
  onSaved: (saved: Stakeholder) => void;
}

export function StakeholderDialog({ screen, stakeholder, onClose, onSaved }: StakeholderDialogProps) {
  const { t } = useTranslation();
  const { projectId, settings, labels, personName } = screen;
  const fw = settings.framework;
  const [draft, setDraft] = useState({
    display_name: stakeholder?.display_name ?? '',
    category: stakeholder?.category ?? '',
    contact_id: stakeholder?.contact_id ?? '',
    is_group: stakeholder?.is_group ?? false,
    group_size: stakeholder?.group_size_estimate != null ? String(stakeholder.group_size_estimate) : '',
    interests: stakeholder?.interests ?? '',
    expectations: stakeholder?.expectations ?? '',
    concerns: stakeholder?.concerns ?? '',
    owner: stakeholder?.relationship_owner_user_id ?? '',
    is_confidential: stakeholder?.is_confidential ?? false,
    status: stakeholder?.status ?? 'active',
  });
  const [confidentialTouched, setConfidentialTouched] = useState(false);
  const set = <K extends keyof typeof draft>(key: K, value: (typeof draft)[K]) => setDraft((d) => ({ ...d, [key]: value }));

  const write = useWrite((body: StakeholderInput) => {
    return stakeholder ? updateStakeholder(projectId, stakeholder.id, body) : createStakeholder(projectId, body);
  }, onSaved);

  const nameMissing = !draft.display_name.trim() && !draft.contact_id;
  const ready = !!draft.category && !nameMissing;

  const submit = () => {
    const body: StakeholderInput = {
      display_name: draft.display_name.trim(),
      category: draft.category,
      contact_id: draft.contact_id || null,
      is_group: draft.is_group,
      group_size_estimate: draft.is_group && draft.group_size ? Number(draft.group_size) : null,
      interests: draft.interests.trim(),
      expectations: draft.expectations.trim(),
      concerns: draft.concerns.trim(),
      relationship_owner_user_id: draft.owner || null,
    };
    // Left alone, the server marks private persons confidential by their category.
    if (stakeholder || confidentialTouched) body.is_confidential = draft.is_confidential;
    if (stakeholder) body.status = draft.status;
    write.run(body);
  };

  return (
    <WideModal
      open
      onClose={onClose}
      busy={write.busy}
      size="lg"
      testId="stakeholder-dialog"
      title={
        stakeholder
          ? t('stakeholders.ui.stakeholder.edit_title', { defaultValue: 'Edit stakeholder' })
          : t('stakeholders.ui.stakeholder.add_title', { defaultValue: 'Add stakeholder' })
      }
      subtitle={t('stakeholders.ui.stakeholder.dialog_subtitle', {
        defaultValue: 'Anyone who is affected by the project or can affect it: a person, an organisation or a group.',
      })}
      footer={
        <div className="flex w-full items-center justify-end gap-3">
          <Button variant="ghost" onClick={onClose} disabled={write.busy}>
            {t('stakeholders.ui.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button loading={write.busy} disabled={!ready} onClick={submit} data-testid="stakeholder-save">
            {t('stakeholders.ui.save', { defaultValue: 'Save' })}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <RefusalBox refusal={write.refusal} />
        <WideModalSection columns={2}>
          <WideModalField
            label={t('stakeholders.ui.stakeholder.name', { defaultValue: 'Name' })}
            hint={t('stakeholders.ui.stakeholder.name_hint', {
              defaultValue: 'Required unless you pick a contact below.',
            })}
            htmlFor="stakeholder-name"
          >
            <input
              id="stakeholder-name"
              className={FIELD_CLASS}
              value={draft.display_name}
              maxLength={255}
              onChange={(e) => set('display_name', e.target.value)}
            />
          </WideModalField>
          <WideModalField
            label={t('stakeholders.ui.stakeholder.category', { defaultValue: 'Category' })}
            required
            htmlFor="stakeholder-category"
          >
            <select
              id="stakeholder-category"
              className={FIELD_CLASS}
              value={draft.category}
              onChange={(e) => set('category', e.target.value)}
            >
              <option value="">{t('stakeholders.ui.choose', { defaultValue: 'Choose' })}</option>
              {fw.stakeholder_categories.map((c) => (
                <option key={c.code} value={c.code}>
                  {itemName(labels, c)}
                </option>
              ))}
            </select>
          </WideModalField>
          <WideModalField
            label={t('stakeholders.ui.stakeholder.contact', { defaultValue: 'Contact from the address book' })}
            hint={t('stakeholders.ui.stakeholder.contact_hint', {
              defaultValue: 'Optional. The name then follows the contact.',
            })}
          >
            <ContactSearchInput
              value={draft.contact_id}
              displayValue={stakeholder?.contact_id ? (stakeholder.name ?? '') : ''}
              onChange={(id) => set('contact_id', id)}
              showBrowse={false}
            />
          </WideModalField>
          <WideModalField
            label={t('stakeholders.ui.stakeholder.owner', { defaultValue: 'Who keeps the relationship' })}
            hint={t('stakeholders.ui.stakeholder.owner_hint', {
              defaultValue: 'The person on the project team this stakeholder talks to.',
            })}
          >
            <ProjectPeopleSelect
              projectId={projectId}
              value={draft.owner}
              displayValue={personName(draft.owner) ?? ''}
              onChange={(id) => set('owner', id)}
            />
          </WideModalField>
        </WideModalSection>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <label className="flex items-center gap-2 text-sm text-content-primary">
            <input type="checkbox" checked={draft.is_group} onChange={(e) => set('is_group', e.target.checked)} />
            {t('stakeholders.ui.stakeholder.is_group', { defaultValue: 'This is a group of people' })}
          </label>
          {draft.is_group && (
            <label className="flex items-center gap-2 text-sm text-content-secondary">
              {t('stakeholders.ui.stakeholder.group_size', { defaultValue: 'About how many' })}
              <input
                type="number"
                min={0}
                className={`${FIELD_CLASS} w-24`}
                value={draft.group_size}
                onChange={(e) => set('group_size', e.target.value)}
              />
            </label>
          )}
          <label className="flex items-center gap-2 text-sm text-content-primary">
            <input
              type="checkbox"
              checked={draft.is_confidential}
              onChange={(e) => {
                setConfidentialTouched(true);
                set('is_confidential', e.target.checked);
              }}
            />
            {t('stakeholders.ui.stakeholder.confidential', {
              defaultValue: 'Private person: show the name only to people allowed to see personal data',
            })}
          </label>
        </div>

        <WideModalSection columns={1}>
          <WideModalField label={t('stakeholders.ui.stakeholder.interests', { defaultValue: 'What they care about' })}>
            <textarea
              rows={2}
              className={FIELD_CLASS}
              value={draft.interests}
              onChange={(e) => set('interests', e.target.value)}
            />
          </WideModalField>
          <WideModalField
            label={t('stakeholders.ui.stakeholder.expectations', { defaultValue: 'What they expect from the project' })}
          >
            <textarea
              rows={2}
              className={FIELD_CLASS}
              value={draft.expectations}
              onChange={(e) => set('expectations', e.target.value)}
            />
          </WideModalField>
          <WideModalField label={t('stakeholders.ui.stakeholder.concerns', { defaultValue: 'What worries them' })}>
            <textarea
              rows={2}
              className={FIELD_CLASS}
              value={draft.concerns}
              onChange={(e) => set('concerns', e.target.value)}
            />
          </WideModalField>
          {stakeholder && (
            <WideModalField
              label={t('stakeholders.ui.stakeholder.status', { defaultValue: 'Status' })}
              htmlFor="stakeholder-status"
            >
              <select
                id="stakeholder-status"
                className={FIELD_CLASS}
                value={draft.status}
                onChange={(e) => set('status', e.target.value as typeof draft.status)}
              >
                {(Object.keys(STAKEHOLDER_STATUS) as Array<keyof typeof STAKEHOLDER_STATUS>).map((s) => (
                  <option key={s} value={s}>
                    {vocab(t, STAKEHOLDER_STATUS, s)}
                  </option>
                ))}
              </select>
            </WideModalField>
          )}
        </WideModalSection>
      </div>
    </WideModal>
  );
}
