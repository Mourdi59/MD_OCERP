// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The project records a stakeholder event or a commitment can point at: the
// meetings and the letters of the same project. They are read from the
// modules that own them and offered as plain choices. When one of those
// modules is switched off the list is simply empty, and a link that is
// already stored stays as it is.

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { fetchCorrespondence } from '@/features/correspondence/api';
import { fetchMeetings } from '@/features/meetings/api';
import { fetchTasks } from '@/features/tasks/api';
import { fmtDate } from '@/shared/lib/formatters';

import { listProjectRisks, stakeholderKeys } from './api';
import type { TickOption } from './StakeholderBits';
import type { TFn } from './labels';

/** A record named by its title and, when it has one, its day. */
export function datedName(t: TFn, title: string, date: string | null | undefined): string {
  if (!date) return title;
  return t('stakeholders.ui.link.dated', { defaultValue: '{{title}} ({{date}})', title, date: fmtDate(date) });
}

export interface LinkOptions {
  options: TickOption[];
  loading: boolean;
}

/** The meetings of the project, newest first as the meetings module lists them. */
export function useMeetingOptions(projectId: string, t: TFn, enabled = true): LinkOptions {
  const query = useQuery({
    queryKey: [...stakeholderKeys.project(projectId), 'link-meetings'],
    queryFn: () => fetchMeetings({ project_id: projectId }),
    enabled: !!projectId && enabled,
    retry: false,
    staleTime: 60_000,
  });
  const options = useMemo(
    () => (query.data ?? []).map((m) => ({ id: m.id, label: datedName(t, m.title, m.date) })),
    [query.data, t],
  );
  return { options, loading: query.isLoading };
}

/** The letters of the project, incoming and outgoing. */
export function useCorrespondenceOptions(projectId: string, t: TFn, enabled = true): LinkOptions {
  const query = useQuery({
    queryKey: [...stakeholderKeys.project(projectId), 'link-correspondence'],
    queryFn: () => fetchCorrespondence({ project_id: projectId }).then((page) => page.items),
    enabled: !!projectId && enabled,
    retry: false,
    staleTime: 60_000,
  });
  const options = useMemo(
    () => (query.data ?? []).map((c) => ({ id: c.id, label: datedName(t, c.subject, c.date_received ?? c.date_sent) })),
    [query.data, t],
  );
  return { options, loading: query.isLoading };
}

/** The risk register of the project, each entry by its code and title. */
export function useRiskOptions(projectId: string, t: TFn, enabled = true): LinkOptions {
  const query = useQuery({
    queryKey: [...stakeholderKeys.project(projectId), 'link-risks'],
    queryFn: () => listProjectRisks(projectId).then((page) => page.items),
    enabled: !!projectId && enabled,
    retry: false,
    staleTime: 60_000,
  });
  const options = useMemo(
    () =>
      (query.data ?? []).map((r) => ({
        id: r.id,
        label: r.code
          ? t('stakeholders.ui.link.coded', { defaultValue: '{{code}}: {{title}}', code: r.code, title: r.title })
          : r.title,
      })),
    [query.data, t],
  );
  return { options, loading: query.isLoading };
}

/** The tasks of the project. */
export function useTaskOptions(projectId: string, t: TFn, enabled = true): LinkOptions {
  const query = useQuery({
    queryKey: [...stakeholderKeys.project(projectId), 'link-tasks'],
    queryFn: () => fetchTasks({ project_id: projectId }).then((page) => page.items),
    enabled: !!projectId && enabled,
    retry: false,
    staleTime: 60_000,
  });
  const options = useMemo(
    () => (query.data ?? []).map((task) => ({ id: task.id, label: datedName(t, task.title, task.due_date) })),
    [query.data, t],
  );
  return { options, loading: query.isLoading };
}

/** The choices of a single-record picker, keeping a stored link the list no longer offers. */
export function withStored(options: TickOption[], storedId: string, keptLabel: string): TickOption[] {
  if (!storedId || options.some((o) => o.id === storedId)) return options;
  return [{ id: storedId, label: keptLabel }, ...options];
}
