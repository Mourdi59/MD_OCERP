/**
 * BordereauDrawer — Bordereau de prix lateral drawer.
 *
 * Shows the deduplicated price schedule attached to the current BOQ:
 *  - Attach / detach a bordereau (or create a new one)
 *  - Edit unit prices — propagates to all attached BOQs
 *  - View occurrence count per line
 *  - Assembly lines: full component decomposition editor + import from library
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
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
  Link2Off,
  Trash2,
  Loader2,
  Package,
  Download,
  Search,
} from 'lucide-react';
import { Button, Badge } from '@/shared/ui';
import { useToastStore } from '@/stores/useToastStore';
import { assembliesApi } from '@/features/assemblies/api';
import type { AssemblyWithComponents } from '@/features/assemblies/api';
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
  bordereauId: string | null;
  isOpen: boolean;
  onClose: () => void;
  onBordereauChanged: (bordereauId: string | null) => void;
}

const RESOURCE_TYPES = [
  'material',
  'labor',
  'equipment',
  'operator',
  'subcontractor',
  'overhead',
] as const;

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
      if (e.key === 'Escape') { e.preventDefault(); onClose(); }
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
    mutationFn: (name: string) => bordereauApi.create({ project_id: projectId, name }),
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
  const [newLine, setNewLine] = useState<Partial<CreateLineData> & { is_assembly?: boolean }>({});
  const [showAddLine, setShowAddLine] = useState(false);
  const [editingLineId, setEditingLineId] = useState<string | null>(null);
  const [editRate, setEditRate] = useState<string>('');
  const [editDesignation, setEditDesignation] = useState<string>('');
  const [expandedLineId, setExpandedLineId] = useState<string | null>(null);

  const createLineMutation = useMutation({
    mutationFn: (data: CreateLineData) => bordereauApi.createLine(bordereauId!, data),
    onSuccess: (createdLine) => {
      qc.invalidateQueries({ queryKey: ['bordereau', bordereauId] });
      setShowAddLine(false);
      setNewLine({});
      // Auto-expand assembly lines so user can add components right away
      if (createdLine.is_assembly) setExpandedLineId(createdLine.id);
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
    mutationFn: (lineId: string) => bordereauApi.deleteLine(bordereauId!, lineId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bordereau', bordereauId] });
    },
    onError: () => toast({ type: 'error', title: t('bordereau.errors.deleteLineFailed') }),
  });

  // ── Component editor ─────────────────────────────────────────────────
  const replaceComponentsMutation = useMutation({
    mutationFn: ({ lineId, comps }: { lineId: string; comps: CreateComponentData[] }) =>
      bordereauApi.replaceComponents(bordereauId!, lineId, comps),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['bordereau', bordereauId] });
      for (const bid of result.affected_boq_ids) {
        qc.invalidateQueries({ queryKey: ['boq', bid] });
      }
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
        data: { unit_rate: newRate, designation: editDesignation || undefined, version: line.version },
      });
    },
    [editRate, editDesignation, updateLineMutation],
  );

  // ── Render ───────────────────────────────────────────────────────────
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-40 flex pointer-events-none">
      <div className="flex-1 pointer-events-auto" onClick={onClose} />

      <div className="w-[520px] max-w-full bg-white dark:bg-gray-900 border-l border-gray-200 dark:border-gray-700 shadow-2xl flex flex-col pointer-events-auto h-full overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-indigo-500" />
            <span className="font-semibold text-sm text-gray-900 dark:text-gray-100">
              {t('bordereau.title')}
            </span>
            {bordereau && (
              <Badge variant="outline" className="text-xs">{bordereau.name}</Badge>
            )}
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800">
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
                {projectBordereaux.length > 0 && (
                  <select
                    className="w-full text-xs border border-gray-300 rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600"
                    defaultValue=""
                    onChange={(e) => { if (e.target.value) attachMutation.mutate(e.target.value); }}
                  >
                    <option value="">{t('bordereau.pickExisting')}</option>
                    {projectBordereaux.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name} ({b.line_count} {t('bordereau.lines')})
                      </option>
                    ))}
                  </select>
                )}
                {showCreate ? (
                  <div className="flex gap-2">
                    <input
                      type="text"
                      className="flex-1 text-xs border border-gray-300 rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600"
                      placeholder={t('bordereau.namePlaceholder')}
                      value={createName}
                      onChange={(e) => setCreateName(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter' && createName.trim()) createMutation.mutate(createName.trim()); }}
                      autoFocus
                    />
                    <Button size="sm" onClick={() => createName.trim() && createMutation.mutate(createName.trim())} disabled={createMutation.isPending}>
                      {t('common.create')}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>{t('common.cancel')}</Button>
                  </div>
                ) : (
                  <Button size="sm" variant="outline" onClick={() => setShowCreate(true)} className="text-xs">
                    <Plus className="w-3.5 h-3.5 mr-1" />
                    {t('bordereau.createNew')}
                  </Button>
                )}
              </div>
            )}
          </div>

          {/* ── Lines ── */}
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
                    autoFocus
                  />
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder={t('bordereau.unit')}
                      className="w-20 text-xs border border-gray-300 rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600"
                      value={newLine.unit ?? ''}
                      onChange={(e) => setNewLine((l) => ({ ...l, unit: e.target.value }))}
                    />
                    {!newLine.is_assembly && (
                      <input
                        type="number"
                        placeholder={t('bordereau.unitRate')}
                        className="flex-1 text-xs border border-gray-300 rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600"
                        value={newLine.unit_rate ?? ''}
                        onChange={(e) => setNewLine((l) => ({ ...l, unit_rate: parseFloat(e.target.value) || 0 }))}
                      />
                    )}
                    <input
                      type="text"
                      placeholder={t('bordereau.refCode')}
                      className="w-24 text-xs border border-gray-300 rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600"
                      value={newLine.reference_code ?? ''}
                      onChange={(e) => setNewLine((l) => ({ ...l, reference_code: e.target.value }))}
                    />
                  </div>
                  {/* Assembly toggle */}
                  <label className="flex items-center gap-2 cursor-pointer text-xs text-gray-600 dark:text-gray-400">
                    <input
                      type="checkbox"
                      checked={!!newLine.is_assembly}
                      onChange={(e) => setNewLine((l) => ({ ...l, is_assembly: e.target.checked }))}
                      className="rounded"
                    />
                    <Package className="w-3.5 h-3.5 text-amber-500" />
                    {t('bordereau.addAsAssembly')}
                  </label>
                  <div className="flex gap-2 justify-end">
                    <Button
                      size="sm"
                      onClick={() => createLineMutation.mutate({
                        designation: newLine.designation ?? '',
                        unit: newLine.unit ?? '',
                        unit_rate: newLine.is_assembly ? 0 : (newLine.unit_rate ?? 0),
                        reference_code: newLine.reference_code || undefined,
                        is_assembly: newLine.is_assembly ?? false,
                      })}
                      disabled={createLineMutation.isPending || !newLine.designation}
                    >
                      {createLineMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : t('common.add')}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => { setShowAddLine(false); setNewLine({}); }}>
                      {t('common.cancel')}
                    </Button>
                  </div>
                </div>
              )}

              {/* Lines list */}
              <div className="space-y-1">
                {lines.length === 0 && (
                  <p className="text-xs text-gray-400 py-4 text-center">{t('bordereau.noLines')}</p>
                )}

                {lines.map((line) => {
                  const isEditing = editingLineId === line.id;
                  const isExpanded = expandedLineId === line.id;

                  return (
                    <div key={line.id} className="border border-gray-100 dark:border-gray-800 rounded overflow-hidden">
                      {/* Line row */}
                      <div className="flex items-center gap-2 px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800/50">
                        {/* Expand (assembly) / spacer */}
                        {line.is_assembly ? (
                          <button
                            onClick={() => setExpandedLineId(isExpanded ? null : line.id)}
                            className="text-gray-400 hover:text-gray-600 flex-shrink-0"
                          >
                            {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                          </button>
                        ) : (
                          <div className="w-3.5 flex-shrink-0" />
                        )}

                        {line.is_assembly && <Package className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />}

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
                            {line.reference_code && <span className="ml-1 text-gray-300">· {line.reference_code}</span>}
                          </span>
                        </div>

                        {/* Unit rate */}
                        <div className="text-right flex-shrink-0 min-w-[80px]">
                          {isEditing && !line.is_assembly ? (
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
                              {line.unit_rate.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                            </span>
                          )}
                          {line.position_count > 0 && (
                            <div className="text-xs text-gray-400">×{line.position_count}</div>
                          )}
                        </div>

                        {/* Actions */}
                        {!bordereau.is_locked && (
                          <div className="flex items-center gap-1 flex-shrink-0">
                            {isEditing ? (
                              <>
                                <button
                                  onClick={() => commitEdit(line)}
                                  disabled={updateLineMutation.isPending}
                                  className="p-1 text-green-600 hover:text-green-800"
                                >
                                  {updateLineMutation.isPending
                                    ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    : <Check className="w-3.5 h-3.5" />}
                                </button>
                                <button onClick={() => setEditingLineId(null)} className="p-1 text-gray-400 hover:text-gray-600">
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
                      {line.is_assembly && isExpanded && (
                        <ComponentEditor
                          line={line}
                          isLocked={bordereau.is_locked}
                          onSave={(comps) => replaceComponentsMutation.mutate({ lineId: line.id, comps })}
                          isSaving={replaceComponentsMutation.isPending}
                          projectId={projectId}
                          onToast={toast}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-100 dark:border-gray-800 px-4 py-2">
          <p className="text-xs text-gray-400">{t('bordereau.footerInfo')}</p>
        </div>
      </div>
    </div>
  );
}

// ── Assembly component editor ─────────────────────────────────────────────────

interface ComponentEditorProps {
  line: BordereauLine;
  isLocked: boolean;
  onSave: (comps: CreateComponentData[]) => void;
  isSaving: boolean;
  projectId: string;
  onToast: ReturnType<typeof useToastStore>['addToast'];
}

function ComponentEditor({ line, isLocked, onSave, isSaving, projectId, onToast }: ComponentEditorProps) {
  const { t } = useTranslation();
  const [comps, setComps] = useState<CreateComponentData[]>(
    line.components.map((c) => ({
      description: c.description,
      unit: c.unit,
      unit_cost: c.unit_cost,
      factor: c.factor,
      quantity: c.quantity,
      resource_type: c.resource_type as CreateComponentData['resource_type'],
    })),
  );
  const [showPicker, setShowPicker] = useState(false);

  // Sync if the line's components change externally
  useEffect(() => {
    setComps(line.components.map((c) => ({
      description: c.description,
      unit: c.unit,
      unit_cost: c.unit_cost,
      factor: c.factor,
      quantity: c.quantity,
      resource_type: c.resource_type as CreateComponentData['resource_type'],
    })));
  }, [line.id, line.components.length]);

  const runningTotal = useMemo(
    () => comps.reduce((sum, c) => sum + (c.factor ?? 1) * (c.quantity ?? 1) * (c.unit_cost ?? 0), 0),
    [comps],
  );

  function updateComp(idx: number, field: keyof CreateComponentData, value: unknown) {
    setComps((prev) => prev.map((c, i) => (i === idx ? { ...c, [field]: value } : c)));
  }

  function removeComp(idx: number) {
    setComps((prev) => prev.filter((_, i) => i !== idx));
  }

  function addComp() {
    setComps((prev) => [...prev, { description: '', unit: '', unit_cost: 0, factor: 1, quantity: 1 }]);
  }

  function handleImport(assembly: AssemblyWithComponents) {
    const imported: CreateComponentData[] = assembly.components.map((c) => ({
      description: c.description,
      unit: c.unit,
      unit_cost: c.unit_cost,
      factor: c.factor,
      quantity: c.quantity,
      resource_type: c.resource_type as CreateComponentData['resource_type'],
      cost_item_id: c.cost_item_id ?? undefined,
    }));
    setComps(imported);
    setShowPicker(false);
    onToast({ type: 'info', title: t('bordereau.assembly.importedFrom', { name: assembly.name }) });
  }

  return (
    <div className="bg-amber-50 dark:bg-amber-900/10 border-t border-amber-100 dark:border-amber-900/30 px-3 py-2">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-amber-700 dark:text-amber-400">
          {t('bordereau.components')}
        </span>
        {!isLocked && (
          <button
            onClick={() => setShowPicker(true)}
            className="flex items-center gap-1 text-xs text-amber-600 hover:text-amber-800"
          >
            <Download className="w-3 h-3" />
            {t('bordereau.importFromAssembly')}
          </button>
        )}
      </div>

      {showPicker && (
        <AssemblyPickerModal
          projectId={projectId}
          onSelect={handleImport}
          onClose={() => setShowPicker(false)}
        />
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500">
              <th className="text-left pb-1 pr-1">{t('bordereau.component.description')}</th>
              <th className="w-10 text-center pb-1">{t('bordereau.component.resourceType')}</th>
              <th className="w-10 text-right pb-1">{t('bordereau.unit')}</th>
              <th className="w-10 text-right pb-1">{t('bordereau.component.qty')}</th>
              <th className="w-10 text-right pb-1">F</th>
              <th className="w-16 text-right pb-1">{t('bordereau.component.unitCost')}</th>
              <th className="w-16 text-right pb-1">{t('bordereau.component.total')}</th>
              {!isLocked && <th className="w-6 pb-1" />}
            </tr>
          </thead>
          <tbody>
            {comps.map((comp, idx) => {
              const total = (comp.factor ?? 1) * (comp.quantity ?? 1) * (comp.unit_cost ?? 0);
              const rtColor: Record<string, string> = {
                material: 'bg-blue-100 text-blue-700',
                labor: 'bg-green-100 text-green-700',
                equipment: 'bg-orange-100 text-orange-700',
                operator: 'bg-purple-100 text-purple-700',
                subcontractor: 'bg-pink-100 text-pink-700',
                overhead: 'bg-gray-100 text-gray-600',
              };
              const rtLabel: Record<string, string> = {
                material: 'M', labor: 'L', equipment: 'E',
                operator: 'Op', subcontractor: 'Sc', overhead: 'Oh',
              };

              return (
                <tr key={idx} className="border-t border-amber-100 dark:border-amber-900/20">
                  <td className="py-1 pr-1">
                    {isLocked ? (
                      <span>{comp.description}</span>
                    ) : (
                      <input
                        type="text"
                        className="w-full border-b border-gray-200 bg-transparent focus:outline-none focus:border-indigo-400 text-xs"
                        value={comp.description}
                        onChange={(e) => updateComp(idx, 'description', e.target.value)}
                        placeholder="Description…"
                      />
                    )}
                  </td>
                  <td className="py-1 text-center">
                    {isLocked ? (
                      <span className={`px-1 rounded text-xs ${rtColor[comp.resource_type ?? ''] ?? ''}`}>
                        {rtLabel[comp.resource_type ?? ''] ?? '—'}
                      </span>
                    ) : (
                      <select
                        className="text-xs border border-gray-200 rounded px-0.5 bg-white dark:bg-gray-800 dark:border-gray-700"
                        value={comp.resource_type ?? ''}
                        onChange={(e) => updateComp(idx, 'resource_type', e.target.value || undefined)}
                      >
                        <option value="">—</option>
                        {RESOURCE_TYPES.map((rt) => (
                          <option key={rt} value={rt}>{rtLabel[rt]}</option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td className="py-1 text-right">
                    {isLocked ? comp.unit : (
                      <input
                        type="text"
                        className="w-full text-right border-b border-gray-200 bg-transparent focus:outline-none focus:border-indigo-400 text-xs"
                        value={comp.unit}
                        onChange={(e) => updateComp(idx, 'unit', e.target.value)}
                      />
                    )}
                  </td>
                  <td className="py-1 text-right">
                    {isLocked ? comp.quantity : (
                      <input
                        type="number"
                        className="w-full text-right border-b border-gray-200 bg-transparent focus:outline-none focus:border-indigo-400 text-xs"
                        value={comp.quantity}
                        onChange={(e) => updateComp(idx, 'quantity', parseFloat(e.target.value) || 1)}
                        min={0}
                        step="any"
                      />
                    )}
                  </td>
                  <td className="py-1 text-right">
                    {isLocked ? comp.factor : (
                      <input
                        type="number"
                        className="w-full text-right border-b border-gray-200 bg-transparent focus:outline-none focus:border-indigo-400 text-xs"
                        value={comp.factor}
                        onChange={(e) => updateComp(idx, 'factor', parseFloat(e.target.value) || 1)}
                        min={0}
                        step="any"
                      />
                    )}
                  </td>
                  <td className="py-1 text-right">
                    {isLocked ? comp.unit_cost.toFixed(2) : (
                      <input
                        type="number"
                        className="w-full text-right border-b border-gray-200 bg-transparent focus:outline-none focus:border-indigo-400 text-xs"
                        value={comp.unit_cost}
                        onChange={(e) => updateComp(idx, 'unit_cost', parseFloat(e.target.value) || 0)}
                        min={0}
                        step="any"
                      />
                    )}
                  </td>
                  <td className="py-1 text-right text-gray-600 font-mono tabular-nums">
                    {total.toFixed(2)}
                  </td>
                  {!isLocked && (
                    <td className="py-1 pl-1">
                      <button
                        onClick={() => removeComp(idx)}
                        className="p-0.5 text-gray-300 hover:text-red-400"
                        title={t('bordereau.component.delete')}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
          {comps.length > 0 && (
            <tfoot>
              <tr className="border-t-2 border-amber-200 dark:border-amber-800">
                <td colSpan={isLocked ? 6 : 6} className="py-1 text-right text-xs font-medium text-gray-600 pr-1">
                  {t('bordereau.component.runningTotal')}
                </td>
                <td className="py-1 text-right text-xs font-semibold font-mono tabular-nums text-amber-700">
                  {runningTotal.toFixed(2)}
                </td>
                {!isLocked && <td />}
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {!isLocked && (
        <div className="flex justify-between mt-2">
          <button
            onClick={addComp}
            className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
          >
            <Plus className="w-3 h-3" />
            {t('common.add')}
          </button>
          <Button size="sm" onClick={() => onSave(comps)} disabled={isSaving}>
            {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : t('common.save')}
          </Button>
        </div>
      )}
    </div>
  );
}

// ── Assembly picker modal ─────────────────────────────────────────────────────

interface AssemblyPickerModalProps {
  projectId: string;
  onSelect: (assembly: AssemblyWithComponents) => void;
  onClose: () => void;
}

function AssemblyPickerModal({ projectId, onSelect, onClose }: AssemblyPickerModalProps) {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [loadingId, setLoadingId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['assemblies-for-bordereau', search, projectId],
    queryFn: () => assembliesApi.list(
      search
        ? { search, limit: '20' }
        : { project_id: projectId, limit: '30' }
    ),
    staleTime: 30_000,
  });

  const assemblies = data?.items ?? [];

  async function handlePick(id: string) {
    setLoadingId(id);
    try {
      const full = await assembliesApi.get(id);
      onSelect(full);
    } finally {
      setLoadingId(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="bg-white dark:bg-gray-900 rounded-lg shadow-xl w-[400px] max-h-[480px] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <span className="font-semibold text-sm">{t('bordereau.assembly.pickTitle')}</span>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-4 py-2 border-b border-gray-100 dark:border-gray-800">
          <div className="flex items-center gap-2 border border-gray-300 dark:border-gray-600 rounded px-2 py-1">
            <Search className="w-3.5 h-3.5 text-gray-400" />
            <input
              type="text"
              className="flex-1 text-xs bg-transparent focus:outline-none"
              placeholder={t('bordereau.assembly.search')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              autoFocus
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto py-1">
          {isLoading && (
            <div className="flex justify-center py-6">
              <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
            </div>
          )}
          {!isLoading && assemblies.length === 0 && (
            <p className="text-xs text-gray-400 text-center py-6">{t('bordereau.assembly.noResults')}</p>
          )}
          {assemblies.map((a) => (
            <button
              key={a.id}
              className="w-full flex items-center gap-3 px-4 py-2 text-left hover:bg-indigo-50 dark:hover:bg-indigo-900/20 disabled:opacity-50"
              onClick={() => handlePick(a.id)}
              disabled={!!loadingId}
            >
              {loadingId === a.id ? (
                <Loader2 className="w-4 h-4 animate-spin text-indigo-500 flex-shrink-0" />
              ) : (
                <Package className="w-4 h-4 text-amber-500 flex-shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">{a.name}</div>
                <div className="text-xs text-gray-400">
                  {a.code} · {a.unit}
                  {a.component_count > 0 && <span className="ml-1">· {a.component_count} composants</span>}
                </div>
              </div>
              <span className="text-xs font-mono text-gray-600 flex-shrink-0">
                {Number(a.total_rate).toFixed(2)}
              </span>
            </button>
          ))}
        </div>

        <div className="px-4 py-2 border-t border-gray-100 dark:border-gray-800">
          <Button size="sm" variant="ghost" className="w-full" onClick={onClose}>
            {t('common.cancel')}
          </Button>
        </div>
      </div>
    </div>
  );
}
