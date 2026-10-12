// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// React Query hooks for the logistics plan, the words context every panel
// needs, and the one write helper the list panels share.

import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { fmtList } from '@/shared/lib/formatters';
import { useToastStore } from '@/stores/useToastStore';

import {
  createItem,
  deleteItem,
  getBalance,
  getCatalogue,
  getConcept,
  getNeighbourhood,
  getReadiness,
  listAreas,
  listCatalogueChoices,
  listComplaints,
  listCoordination,
  listCustoms,
  listDemands,
  listDocuments,
  listLines,
  listMedia,
  listPermits,
  listStages,
  listTransports,
  planKeys,
  planProblem,
  transitionItem,
  updateItem,
  type Body,
  type PlanCatalogue,
  type PlanPage,
  type ResourceKind,
} from './api';
import { findingText, type Words } from './rules';
import type { TFn } from './texts';

function items<T>(page: PlanPage<T>): T[] {
  return page.items;
}

function usePlanList<T>(projectId: string, name: string, fetcher: () => Promise<PlanPage<T>>, enabled = true) {
  return useQuery({
    queryKey: planKeys.of(projectId, name),
    queryFn: () => fetcher().then(items),
    enabled: !!projectId && enabled,
  });
}

export const useCatalogue = (projectId: string) =>
  useQuery({
    queryKey: planKeys.of(projectId, 'catalogue'),
    queryFn: () => getCatalogue(projectId),
    enabled: !!projectId,
    staleTime: 60_000,
  });
export const useStages = (projectId: string) => usePlanList(projectId, 'stages', () => listStages(projectId));
export const useAreas = (projectId: string) => usePlanList(projectId, 'areas', () => listAreas(projectId));
export const useBalance = (projectId: string) => usePlanList(projectId, 'balance', () => getBalance(projectId));
export const useMedia = (projectId: string) => usePlanList(projectId, 'media', () => listMedia(projectId));
export const useDemands = (projectId: string, mediaId: string) =>
  usePlanList(projectId, `demands:${mediaId}`, () => listDemands(projectId, mediaId));
export const useTransports = (projectId: string) =>
  usePlanList(projectId, 'transports', () => listTransports(projectId));
export const usePermits = (projectId: string) => usePlanList(projectId, 'permits', () => listPermits(projectId));
export const useCustoms = (projectId: string) => usePlanList(projectId, 'customs', () => listCustoms(projectId));
export const useLines = (projectId: string, caseId: string) =>
  usePlanList(projectId, `lines:${caseId}`, () => listLines(projectId, caseId));
export const useDocuments = (projectId: string, caseId: string) =>
  usePlanList(projectId, `documents:${caseId}`, () => listDocuments(projectId, caseId));
export const useComplaints = (projectId: string) =>
  usePlanList(projectId, 'complaints', () => listComplaints(projectId));
export const useCoordination = (projectId: string) =>
  usePlanList(projectId, 'coordination', () => listCoordination(projectId));
export const useCatalogueChoices = (projectId: string, enabled: boolean) =>
  usePlanList(projectId, 'catalogue-choices', () => listCatalogueChoices(), enabled);

export const useConcept = (projectId: string) =>
  useQuery({ queryKey: planKeys.of(projectId, 'concept'), queryFn: () => getConcept(projectId), enabled: !!projectId });
export const useNeighbourhood = (projectId: string) =>
  useQuery({
    queryKey: planKeys.of(projectId, 'neighbourhood'),
    queryFn: () => getNeighbourhood(projectId),
    enabled: !!projectId,
  });
export const useReadiness = (projectId: string) =>
  useQuery({
    queryKey: planKeys.of(projectId, 'readiness'),
    queryFn: () => getReadiness(projectId),
    enabled: !!projectId,
  });

/** Refetch the whole plan after a write: one changed transport moves the balance, the findings and the readiness. */
export function useInvalidatePlan(projectId: string) {
  const qc = useQueryClient();
  return useCallback(async () => {
    await qc.invalidateQueries({ queryKey: planKeys.project(projectId) });
    // Complaints also feed the issue hub, and transports the gate timeline.
    void qc.invalidateQueries({ queryKey: ['issues-hub', 'neighbour', projectId] });
  }, [qc, projectId]);
}

export function useWords(): Words {
  const { t, i18n } = useTranslation();
  return useMemo(() => ({ t: t as TFn, language: i18n.language || 'en' }), [t, i18n.language]);
}

/** Show a refused write as a toast: the server's sentence, and every blocker it listed. */
export function useReportProblem(catalogue?: PlanCatalogue | null) {
  const addToast = useToastStore((s) => s.addToast);
  const words = useWords();
  return useCallback(
    (err: unknown) => {
      const problem = planProblem(err);
      const blockers = problem.violations.map((v) => findingText(words, v, catalogue));
      addToast({ type: 'error', title: problem.message, message: blockers.length ? fmtList(blockers) : undefined });
    },
    [addToast, words, catalogue],
  );
}

export interface Identified {
  id: string;
}

/**
 * The writes of one list: the record open in the dialog, save (create or
 * change), move to another status and delete. A refusal is shown with the
 * server's reason; nothing here decides whether the reader may act.
 */
export function useResource<T extends Identified>(
  projectId: string,
  kind: ResourceKind,
  options: { parentId?: string; catalogue?: PlanCatalogue | null; moveByPatch?: boolean } = {},
) {
  const { parentId, catalogue, moveByPatch } = options;
  const invalidate = useInvalidatePlan(projectId);
  const report = useReportProblem(catalogue);
  const [editing, setEditing] = useState<{ record: T | null } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const act = useCallback(
    async (id: string, fn: () => Promise<unknown>) => {
      setBusyId(id);
      try {
        await fn();
        await invalidate();
      } catch (err) {
        report(err);
      } finally {
        setBusyId(null);
      }
    },
    [invalidate, report],
  );

  return {
    editing,
    busyId,
    open: (record: T | null = null) => setEditing({ record }),
    close: () => setEditing(null),
    save: (body: Body) =>
      editing?.record
        ? updateItem(projectId, kind, editing.record.id, body)
        : createItem(projectId, kind, body, parentId),
    saved: invalidate,
    move: (id: string, target: string) =>
      act(id, () =>
        moveByPatch ? updateItem(projectId, kind, id, { state: target }) : transitionItem(projectId, kind, id, target),
      ),
    remove: (id: string) => act(id, () => deleteItem(projectId, kind, id)),
  };
}

export type Resource<T extends Identified> = ReturnType<typeof useResource<T>>;
