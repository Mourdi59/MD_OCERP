/**
 * BordereauDrawer — Bordereau de prix lateral drawer.
 *
 * Shows the deduplicated price schedule attached to the current BOQ:
 *  - Attach / detach a bordereau (or create a new one)
 *  - Edit unit prices — propagates to all attached BOQs
 *  - View occurrence count per line
 *  - For assembly lines: expand to edit component prices
 *
 * Pattern mirrors BOQCompareDrawer / VersionHistoryDrawer.
 */

import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  X,
  BookOpen,
  Plus,
  Pencil,
  Check,
  ChevronDown,
  ChevronRight,
  Link2,
  Link2Off,
  Trash2,
  Loader2,
  Package,
} from 'lucide-react';
import clsx from 'clsx';
import { Button, Badge } from '@/shared/ui';
import { useToastStore } from '@/stores/useToastStore';
import {
  bordereauApi,
  type Bordereau,
  type BordereauLine,
  type CreateLineData,
  type UpdateLineData,
  type CreateComponentData,
} from './bordereauApi';

export interface BordereauDrawerProps {
  boqId: string;
  projectId: string;
  /** The bordereau currently attached to the BOQ (null = none). */
  bordereauId: string | null;
  isOpen: boolean;
  onClose: () => void;
  /** Called after attach / detach so the parent can refetch the BOQ. */
  onBordereauChanged: (bordereauId: string | null) => void;
}

export function BordereauDrawer({
  boqId,
  projectId,
  bordereauId,
  isOpen,
  onClose,
  onBordereauChanged,
}: BordereauDrawerProps) {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.addToast);
  const qc = useQueryClient();

  // ── Close on Escape ──────────────────────────────────────────────────
  useEffect(() => {
    if (!isOpen) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    }
    document.addEventListener('keydown', handleKey, { capture: true });
    return () => document.removeEventListener('keydown', handleKey, { capture: true });
  }, [isOpen, onClose]);

  // ── Data fetching ────────────────────────────────────────────────────
  const { data: projectBordereaux = [], isLoading: loadingList } = useQuery({
    queryKey: ['project-bordereaux', projectId],
    queryFn: () => bordereauApi.list(projectId),
    enabled: isOpen && !!projectId,
  });

  const { data: bordereau, isLoading: loadingDetail } = useQuery({
    queryKey: ['bordereau', bordereauId],
    queryFn: () => bordereauApi.get(bordereauId!),
    enabled: isOpen && !!bordereauId,
  });

  const lines = bordereau?.lines ?? [];
  const isLoading = loadingList || loadingDetail;

  // ── Attach ───────────────────────────────────────────────────────────
  const [createName, setCreateName] = useState('');
  const [showCreate, setShowCreate] = useState(false);

  const createMutation = useMutation({
    mutationFn: (name: string) =>
      bordereauApi.create({ project_id: projectId, name }),
    onSuccess: async (newB) => {
      await attachMutation.mutateAsync(newB.id);
      qc.invalidateQueries({ queryKey: ['project-bordereaux', projectId] });
      setShowCreate(false);
      setCreateName('');
    },
    onError: () => toast({ type: 'error', title: t('bordereau.errors.createFailed') }),
  });

  const attachMutation = useMutation({
    mutationFn: (bid: string) => bordereauApi.attach(boqId, bid),
    onSuccess: (result, bid) => {
      qc.invalidateQueries({ queryKey: ['boq', boqId] });
      qc.invalidateQueries({ queryKey: ['bordereau', bid] });
      onBordereauChanged(bid);
      const msg = result.positions_linked > 0
        ? t('bordereau.attachedWithBackfill', { count: result.positions_linked })
        : t('bordereau.attached');
      toast({ type: 'success', title: msg });
    },
    onError: () => toast({ type: 'error', title: t('bordereau.errors.attachFailed') }),
  });

  const detachMutation = useMutation({
    mutationFn: () => bordereauApi.detach(boqId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['boq', boqId] });
      onBordereauChanged(null);
      toast({ type: 'info', title: t('bordereau.detached') });
    },
    onError: () => toast({ type: 'error', title: t('bordereau.errors.detachFailed') }),
  });

  // ── Line CRUD ────────────────────────────────────────────────────────
  const [newLine, setNewLine] = useState<Partial<CreateLineData>>({});
  const [showAddLine, setShowAddLine] = useState(false);
  const [editingLineId, setEditingLineId] = useState<string | null>(null);
  const [editRate, setEditRate] = useState<string>('');
  const [editDesignation, setEditDesignation] = useState<string>('');
  const [expandedLineId, setExpandedLineId] = useState<string | null>(null);

  const createLineMutation = useMutation({
    mutationFn: (data: CreateLineData) =>
      bordereauApi.createLine(bordereauId!, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bordereau', bordereauId] });
      setShowAddLine(false);
      setNewLine({});
    },
    onError: () => toast({ type: 'error', title: t('bordereau.errors.createLineFailed') }),
  });

  const updateLineMutation = useMutation({
    mutationFn: ({ lineId, data }: { lineId: string; data: UpdateLineData }) =>
      bordereauApi.updateLine(bordereauId!, lineId, data),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['bordereau', bordereauId] });
      for (const bid of result.affected_boq_ids) {
        qc.invalidateQueries({ queryKey: ['boq', bid] });
      }
      setEditingLineId(null);
      if (result.positions_updated > 0) {
        toast({
          type: 'success',
          title: t('bordereau.pricePropagated', { count: result.positions_updated }),
        });
      }
    },
    onError: (err: Error) => {
      if (err.message?.includes('409')) {
        toast({ type: 'error', title: t('bordereau.errors.staleVersion') });
      } else {
        toast({ type: 'error', title: t('bordereau.errors.updateLineFailed') });
      }
    },
  });

  const deleteLineMutation = useMutation({
    mutationFn: (lineId: string) =>
      bordereauApi.deleteLine(bordereauId!, lineId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bordereau', bordereauId] });
    },
    onError: () => toast({ type: 'error', title: t('bordereau.errors.deleteLineFailed') }),
  });

  // ── Component editor ─────────────────────────────────────────────────
  const [editingComponents, setEditingComponents] = useState<CreateComponentData[] | null>(null);

  const replaceComponentsMutation = useMutation({
    mutationFn: ({ lineId, comps }: { lineId: string; comps: CreateComponentData[] }) =>
      bordereauApi.replaceComponents(bordereauId!, lineId, comps),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['bordereau', bordereauId] });
      for (const bid of result.affected_boq_ids) {
        qc.invalidateQueries({ queryKey: ['boq', bid] });
      }
      setEditingComponents(null);
      if (result.positions_updated > 0) {
        toast({
          type: 'success',
          title: t('bordereau.pricePropagated', { count: result.positions_updated }),
        });
      }
    },
    onError: () => toast({ type: 'error', title: t('bordereau.errors.updateLineFailed') }),
  });

  const startEditRate = useCallback((line: BordereauLine) => {
    setEditingLineId(line.id);
    setEditRate(String(line.unit_rate));
    setEditDesignation(line.designation);
  }, []);

  const commitEdit = useCallback(
    (line: BordereauLine) => {
      const newRate = parseFloat(editRate);
      if (isNaN(newRate)) return;
      updateLineMutation.mutate({
        lineId: line.id,
        data: {
          unit_rate: newRate,
          designation: editDesignation || undefined,
          version: line.version,
        },
      });
    },
    [editRate, editDesignation, updateLineMutation],
  );

  // ── Render ───────────────────────────────────────────────────────────

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-40 flex pointer-events-none">
      {/* Backdrop (click-away) */}
      <div
        className="flex-1 pointer-events-auto"
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div className="w-[480px] max-w-full bg-white dark:bg-gray-900 border-l border-gray-200 dark:border-gray-700 shadow-2xl flex flex-col pointer-events-auto h-full overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-indigo-500" />
            <span className="font-semibold text-sm text-gray-900 dark:text-gray-100">
              {t('bordereau.title')}
            </span>
            {bordereau && (
              <Badge variant="outline" className="text-xs">
                {bordereau.name}
              </Badge>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800"
            aria-label={t('common.close')}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          {/* ── Attach section ── */}
          <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-800">
            {bordereauId ? (
              <div className="flex items-center justify-between">
                <div className="text-xs text-gray-500">
                  {t('bordereau.attached')} · {lines.length} {t('bordereau.lines')} ·{' '}
                  {bordereau?.attached_boq_count ?? 0} BOQ
                </div>
                <button
                  onClick={() => detachMutation.mutate()}
                  disabled={detachMutation.isPending}
                  className="flex items-center gap-1 text-xs text-red-500 hover:text-red-700"
                >
                  <Link2Off className="w-3.5 h-3.5" />
                  {t('bordereau.detach')}
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-gray-500">{t('bordereau.noAttached')}</p>

                {/* Pick an existing bordereau */}
                {projectBordereaux.length > 0 && (
                  <div className="flex gap-2">
                    <select
                      className="flex-1 text-xs border border-gray-300 rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600"
                      defaultValue=""
                      onChange={(e) => {
                        if (e.target.value) attachMutation.mutate(e.target.value);
                      }}
                    >
                      <option value="">{t('bordereau.pickExisting')}</option>
                      {projectBordereaux.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name} ({b.line_count} {t('bordereau.lines')})
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Create new */}
                {showCreate ? (
                  <div className="flex gap-2">
                    <input
                      type="text"
                      className="flex-1 text-xs border border-gray-300 rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600"
                      placeholder={t('bordereau.namePlaceholder')}
                      value={createName}
                      onChange={(e) => setCreateName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && createName.trim()) {
                          createMutation.mutate(createName.trim());
                        }
                      }}
                      autoFocus
                    />
                    <Button
                      size="sm"
                      onClick={() => createName.trim() && createMutation.mutate(createName.trim())}
                      disabled={createMutation.isPending}
                    >
                      {t('common.create')}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>
                      {t('common.cancel')}
                    </Button>
                  </div>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setShowCreate(true)}
                    className="text-xs"
                  >
                    <Plus className="w-3.5 h-3.5 mr-1" />
                    {t('bordereau.createNew')}
                  </Button>
                )}
              </div>
            )}
          </div>

          {/* ── Lines table ── */}
          {bordereauId && bordereau && (
            <div className="px-4 py-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                  {t('bordereau.priceLines')}
                </span>
                {!bordereau.is_locked && (
                  <button
                    onClick={() => setShowAddLine((v) => !v)}
                    className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    {t('bordereau.addLine')}
                  </button>
                )}
              </div>

              {/* Add line form */}
              {showAddLine && (
                <div className="mb-3 p-3 bg-indigo-50 dark:bg-indigo-900/20 rounded border border-indigo-200 dark:border-indigo-800 space-y-2">
                  <input
                    type="text"
                    placeholder={t('bordereau.designation')}
                    className="w-full text-xs border border-gray-300 rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600"
                    value={newLine.designation ?? ''}
                    onChange={(e) => setNewLine((l) => ({ ...l, designation: e.target.value }))}
                  />
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder={t('bordereau.unit')}
                      className="w-20 text-xs border border-gray-300 rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600"
                      value={newLine.unit ?? ''}
                      onChange={(e) => setNewLine((l) => ({ ...l, unit: e.target.value }))}
                    />
                    <input
                      type="number"
                      placeholder={t('bordereau.unitRate')}
                      className="flex-1 text-xs border border-gray-300 rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600"
                      value={newLine.unit_rate ?? ''}
                      onChange={(e) =>
                        setNewLine((l) => ({ ...l, unit_rate: parseFloat(e.target.value) || 0 }))
                      }
                    />
                    <input
                      type="text"
                      placeholder={t('bordereau.refCode')}
                      className="w-24 text-xs border border-gray-300 rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600"
                      value={newLine.reference_code ?? ''}
                      onChange={(e) => setNewLine((l) => ({ ...l, reference_code: e.target.value }))}
                    />
                  </div>
                  <div className="flex gap-2 justify-end">
                    <Button
                      size="sm"
                      onClick={() =>
                        createLineMutation.mutate({
                          designation: newLine.designation ?? '',
                          unit: newLine.unit ?? '',
                          unit_rate: newLine.unit_rate ?? 0,
                          reference_code: newLine.reference_code || undefined,
                        })
                      }
                      disabled={createLineMutation.isPending || !newLine.designation}
                    >
                      {t('common.add')}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setShowAddLine(false)}>
                      {t('common.cancel')}
                    </Button>
                  </div>
                </div>
              )}

              {/* Lines list */}
              <div className="space-y-1">
                {lines.length === 0 && (
                  <p className="text-xs text-gray-400 py-4 text-center">
                    {t('bordereau.noLines')}
                  </p>
                )}

                {lines.map((line) => {
                  const isEditing = editingLineId === line.id;
                  const isExpanded = expandedLineId === line.id;

                  return (
                    <div
                      key={line.id}
                      className="border border-gray-100 dark:border-gray-800 rounded overflow-hidden"
                    >
                      {/* Line row */}
                      <div className="flex items-center gap-2 px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800/50">
                        {/* Expand button (assemblies) */}
                        {line.is_assembly ? (
                          <button
                            onClick={() =>
                              setExpandedLineId(isExpanded ? null : line.id)
                            }
                            className="text-gray-400 hover:text-gray-600"
                          >
                            {isExpanded ? (
                              <ChevronDown className="w-3.5 h-3.5" />
                            ) : (
                              <ChevronRight className="w-3.5 h-3.5" />
                            )}
                          </button>
                        ) : (
                          <div className="w-3.5" />
                        )}

                        {/* Assembly badge */}
                        {line.is_assembly && (
                          <Package className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
                        )}

                        {/* Designation */}
                        <div className="flex-1 min-w-0">
                          {isEditing ? (
                            <input
                              type="text"
                              className="w-full text-xs border-b border-indigo-400 bg-transparent focus:outline-none"
                              value={editDesignation}
                              onChange={(e) => setEditDesignation(e.target.value)}
                            />
                          ) : (
                            <span className="text-xs text-gray-900 dark:text-gray-100 truncate block">
                              {line.designation || '—'}
                            </span>
                          )}
                          <span className="text-xs text-gray-400">
                            {line.unit}
                            {line.reference_code && (
                              <span className="ml-1 text-gray-300">· {line.reference_code}</span>
                            )}
                          </span>
                        </div>

                        {/* Unit rate (editable) */}
                        <div className="text-right flex-shrink-0">
                          {isEditing ? (
                            <input
                              type="number"
                              className="w-24 text-xs text-right border border-indigo-400 rounded px-1 py-0.5 bg-white dark:bg-gray-900 focus:outline-none"
                              value={editRate}
                              onChange={(e) => setEditRate(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') commitEdit(line);
                                if (e.key === 'Escape') setEditingLineId(null);
                              }}
                              autoFocus
                            />
                          ) : (
                            <span className="text-xs font-mono text-gray-900 dark:text-gray-100">
                              {line.unit_rate.toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 4,
                              })}
                            </span>
                          )}
                          {line.position_count > 0 && (
                            <div className="text-xs text-gray-400">
                              ×{line.position_count}
                            </div>
                          )}
                        </div>

                        {/* Action buttons */}
                        {!bordereau.is_locked && (
                          <div className="flex items-center gap-1 flex-shrink-0">
                            {isEditing ? (
                              <>
                                <button
                                  onClick={() => commitEdit(line)}
                                  disabled={updateLineMutation.isPending}
                                  className="p-1 text-green-600 hover:text-green-800"
                                  title={t('common.save')}
                                >
                                  {updateLineMutation.isPending ? (
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  ) : (
                                    <Check className="w-3.5 h-3.5" />
                                  )}
                                </button>
                                <button
                                  onClick={() => setEditingLineId(null)}
                                  className="p-1 text-gray-400 hover:text-gray-600"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </>
                            ) : (
                              <>
                                <button
                                  onClick={() => startEditRate(line)}
                                  className="p-1 text-gray-400 hover:text-indigo-600"
                                  title={t('bordereau.editPrice')}
                                >
                                  <Pencil className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={() => deleteLineMutation.mutate(line.id)}
                                  disabled={deleteLineMutation.isPending}
                                  className="p-1 text-gray-400 hover:text-red-500"
                                  title={t('bordereau.deleteLine')}
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Assembly component editor */}
                      {isExpanded && line.is_assembly && (
                        <ComponentEditor
                          line={line}
                          bordereauId={bordereauId}
                          isLocked={bordereau.is_locked}
                          onSave={(comps) => {
                            replaceComponentsMutation.mutate({ lineId: line.id, comps });
                          }}
                          isSaving={replaceComponentsMutation.isPending}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer info */}
        <div className="border-t border-gray-100 dark:border-gray-800 px-4 py-2">
          <p className="text-xs text-gray-400">
            {t('bordereau.footerInfo')}
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Assembly component editor sub-component ──────────────────────────────────

interface ComponentEditorProps {
  line: BordereauLine;
  bordereauId: string;
  isLocked: boolean;
  onSave: (comps: CreateComponentData[]) => void;
  isSaving: boolean;
}

function ComponentEditor({ line, isLocked, onSave, isSaving }: ComponentEditorProps) {
  const { t } = useTranslation();
  const [comps, setComps] = useState<CreateComponentData[]>(
    line.components.map((c) => ({
      description: c.description,
      unit: c.unit,
      unit_cost: c.unit_cost,
      factor: c.factor,
      quantity: c.quantity,
      resource_type: c.resource_type ?? undefined,
    })),
  );

  function updateComp(idx: number, field: keyof CreateComponentData, value: string | number) {
    setComps((prev) =>
      prev.map((c, i) => (i === idx ? { ...c, [field]: value } : c)),
    );
  }

  function addComp() {
    setComps((prev) => [
      ...prev,
      { description: '', unit: '', unit_cost: 0, factor: 1, quantity: 1 },
    ]);
  }

  return (
    <div className="bg-amber-50 dark:bg-amber-900/10 border-t border-amber-100 dark:border-amber-900/30 px-3 py-2">
      <div className="text-xs font-medium text-amber-700 dark:text-amber-400 mb-2">
        {t('bordereau.components')}
      </div>

      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500">
            <th className="text-left pb-1">{t('bordereau.component.description')}</th>
            <th className="w-12 text-right pb-1">{t('bordereau.component.unit')}</th>
            <th className="w-12 text-right pb-1">{t('bordereau.component.factor')}</th>
            <th className="w-16 text-right pb-1">{t('bordereau.component.unitCost')}</th>
            <th className="w-16 text-right pb-1">{t('bordereau.component.total')}</th>
          </tr>
        </thead>
        <tbody>
          {comps.map((comp, idx) => {
            const total = (comp.factor ?? 1) * (comp.quantity ?? 1) * (comp.unit_cost ?? 0);
            return (
              <tr key={idx} className="border-t border-amber-100 dark:border-amber-900/20">
                <td className="py-1 pr-1">
                  {isLocked ? (
                    <span>{comp.description}</span>
                  ) : (
                    <input
                      type="text"
                      className="w-full border-b border-gray-300 bg-transparent focus:outline-none focus:border-indigo-400"
                      value={comp.description}
                      onChange={(e) => updateComp(idx, 'description', e.target.value)}
                    />
                  )}
                </td>
                <td className="py-1 text-right">
                  {isLocked ? (
                    <span>{comp.unit}</span>
                  ) : (
                    <input
                      type="text"
                      className="w-full text-right border-b border-gray-300 bg-transparent focus:outline-none focus:border-indigo-400"
                      value={comp.unit}
                      onChange={(e) => updateComp(idx, 'unit', e.target.value)}
                    />
                  )}
                </td>
                <td className="py-1 text-right">
                  {isLocked ? (
                    <span>{comp.factor}</span>
                  ) : (
                    <input
                      type="number"
                      className="w-full text-right border-b border-gray-300 bg-transparent focus:outline-none focus:border-indigo-400"
                      value={comp.factor}
                      onChange={(e) => updateComp(idx, 'factor', parseFloat(e.target.value) || 1)}
                    />
                  )}
                </td>
                <td className="py-1 text-right">
                  {isLocked ? (
                    <span>{comp.unit_cost}</span>
                  ) : (
                    <input
                      type="number"
                      className="w-full text-right border-b border-gray-300 bg-transparent focus:outline-none focus:border-indigo-400"
                      value={comp.unit_cost}
                      onChange={(e) =>
                        updateComp(idx, 'unit_cost', parseFloat(e.target.value) || 0)
                      }
                    />
                  )}
                </td>
                <td className="py-1 text-right text-gray-600 font-mono">
                  {total.toFixed(2)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {!isLocked && (
        <div className="flex justify-between mt-2">
          <button
            onClick={addComp}
            className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
          >
            <Plus className="w-3 h-3" />
            {t('bordereau.addComponent')}
          </button>
          <Button size="sm" onClick={() => onSave(comps)} disabled={isSaving}>
            {isSaving ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              t('common.save')
            )}
          </Button>
        </div>
      )}
    </div>
  );
}
