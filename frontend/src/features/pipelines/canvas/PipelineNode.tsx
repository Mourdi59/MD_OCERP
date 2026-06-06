/**
 * `<PipelineNode>` — a single pipeline node rendered as an xyflow node.
 *
 * Cloned from the EAC `BlockNode`:
 *   - Outer wrapper carries the category color + selected state via Tailwind
 *     token classes (auto dark-mode).
 *   - Header: category icon + double-click-editable title + `ⓘ` + caret.
 *   - Param chips: short read-only summary (full edit in the Inspector).
 *   - Typed port rows: input handles logical-start, output handles logical-end,
 *     each with a shape-coded glyph + label (color + shape = not color alone).
 *   - Run-state accent bar on the logical-start edge + a status icon so state
 *     never relies on color alone (03_ux_visual §2.3).
 */
import { Handle, Position, type NodeProps } from '@xyflow/react';
import clsx from 'clsx';
import {
  ChevronDown,
  ChevronRight,
  CircleSlash,
  Clock,
  Info,
  Loader2,
  Play,
  XCircle,
  type LucideProps,
} from 'lucide-react';
import {
  useCallback,
  useMemo,
  useState,
  type ComponentType,
  type KeyboardEvent,
} from 'react';
import { useTranslation } from 'react-i18next';

import { useIsRTL } from '@/shared/hooks/useIsRTL';

import { getCategoryTokens, getPortTokens, PORT_SHAPE_SVG } from '../tokens';
import { usePipelineStore, type CanvasNode } from '../usePipelineStore';
import type { RunStatus } from '../api';

export interface PipelineNodeData extends Record<string, unknown> {
  node: CanvasNode;
}

export type PipelineNodeProps = NodeProps;

/** Small inline SVG glyph for a port's data type (shape encoding). */
function PortGlyph({ type, size = 12 }: { type: string; size?: number }) {
  const tok = getPortTokens(type);
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 12 12"
      aria-hidden="true"
      style={{ fill: tok.color, stroke: tok.color }}
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: PORT_SHAPE_SVG[tok.shape] }}
    />
  );
}

/** Map a run status → {icon, accent-bar token class}. */
function runVisual(status: RunStatus | undefined): {
  Icon: ComponentType<LucideProps> | null;
  accent: string;
  spin?: boolean;
} {
  switch (status) {
    case 'queued':
      return { Icon: Clock, accent: 'bg-oe-blue/60' };
    case 'running':
      return { Icon: Loader2, accent: 'bg-oe-blue', spin: true };
    case 'done':
    case 'success':
      return { Icon: Play, accent: 'bg-semantic-success' };
    case 'error':
    case 'failed':
      return { Icon: XCircle, accent: 'bg-semantic-error' };
    case 'paused':
      return { Icon: Clock, accent: 'bg-semantic-warning' };
    case 'cancelled':
      return { Icon: CircleSlash, accent: 'bg-content-tertiary' };
    default:
      return { Icon: null, accent: 'bg-transparent' };
  }
}

export function PipelineNode({ id, data, selected }: PipelineNodeProps) {
  const { t } = useTranslation();
  const isRTL = useIsRTL();
  const node = (data as PipelineNodeData | undefined)?.node;
  const setNodeTitle = usePipelineStore((s) => s.setNodeTitle);
  const toggleExpanded = usePipelineStore((s) => s.toggleNodeExpanded);
  const runNodeState = usePipelineStore((s) =>
    node ? s.run.nodeStates[node.id] : undefined,
  );

  const [editingTitle, setEditingTitle] = useState(false);
  const [draftTitle, setDraftTitle] = useState(node?.title ?? '');
  const [showHelp, setShowHelp] = useState(false);

  const tokens = useMemo(
    () => (node ? getCategoryTokens(node.category) : null),
    [node],
  );

  const commitTitle = useCallback(() => {
    if (!node) return;
    const next = draftTitle.trim() || node.title;
    if (next !== node.title) setNodeTitle(node.id, next);
    setEditingTitle(false);
  }, [node, draftTitle, setNodeTitle]);

  const handleTitleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        commitTitle();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        setDraftTitle(node?.title ?? '');
        setEditingTitle(false);
      }
    },
    [node?.title, commitTitle],
  );

  if (!node || !tokens) return null;

  const Icon = tokens.Icon;
  const inputSide = isRTL ? Position.Right : Position.Left;
  const outputSide = isRTL ? Position.Left : Position.Right;
  const rows = Math.max(node.inputs.length, node.outputs.length);
  const paramChips = Object.entries(node.params).filter(
    ([, v]) => v !== undefined && v !== null && v !== '',
  );
  const rv = runVisual(runNodeState?.status);
  const isAi = node.category === 'ai';

  return (
    <div
      data-testid={`pipeline-node-${id}`}
      data-node-category={node.category}
      data-node-type={node.type}
      data-node-selected={selected ? 'true' : 'false'}
      className={clsx(
        'relative min-w-[220px] max-w-[340px] overflow-hidden rounded-lg border-2 ps-3 pe-3 py-2 text-sm shadow-sm',
        'transition-colors',
        selected ? tokens.classes.bgSelected : tokens.classes.bg,
        selected ? tokens.classes.borderSelected : tokens.classes.border,
        tokens.classes.text,
      )}
    >
      {/* Run-state accent bar on the logical-start edge (no layout shift) */}
      <span
        aria-hidden="true"
        className={clsx(
          'absolute inset-y-0 start-0 w-1',
          rv.accent,
          runNodeState?.status === 'queued' && 'animate-pulse',
        )}
      />

      {/* Header — icon + editable title + help + caret */}
      <div className="flex items-center gap-2">
        <span
          className={clsx(
            'flex h-5 w-5 shrink-0 items-center justify-center',
            tokens.classes.icon,
          )}
        >
          <Icon size={16} aria-hidden="true" />
        </span>
        {editingTitle ? (
          <input
            type="text"
            data-testid={`pipeline-node-title-input-${id}`}
            value={draftTitle}
            onChange={(e) => setDraftTitle(e.target.value)}
            onBlur={commitTitle}
            onKeyDown={handleTitleKeyDown}
            autoFocus
            aria-label={t('pipeline.node.rename', {
              defaultValue: 'Rename node',
            })}
            className="h-6 w-full rounded border border-border bg-white px-1 text-sm dark:bg-gray-900"
          />
        ) : (
          <button
            type="button"
            data-testid={`pipeline-node-title-${id}`}
            onDoubleClick={() => {
              setDraftTitle(node.title);
              setEditingTitle(true);
            }}
            className="truncate text-start font-medium hover:underline"
            title={t('pipeline.node.rename_hint', {
              defaultValue: 'Double-click to rename',
            })}
          >
            {node.title}
          </button>
        )}
        {isAi && (
          <span
            className="ms-1 shrink-0 rounded bg-violet-200 px-1 text-2xs font-semibold text-violet-800 dark:bg-violet-800 dark:text-violet-100"
            title={t('pipeline.node.ai_confidence', {
              defaultValue: 'AI suggestion - review the confidence score',
            })}
          >
            {t('pipeline.node.ai_badge', { defaultValue: 'AI' })}
          </span>
        )}
        <button
          type="button"
          aria-label={t('pipeline.node.help', {
            defaultValue: 'What this node does',
          })}
          aria-expanded={showHelp}
          onClick={() => setShowHelp((v) => !v)}
          className={clsx(
            'ms-auto flex h-5 w-5 shrink-0 items-center justify-center rounded',
            'hover:bg-black/5 dark:hover:bg-white/10',
            tokens.classes.icon,
          )}
        >
          <Info size={13} aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label={
            node.expanded
              ? t('pipeline.node.collapse', { defaultValue: 'Collapse' })
              : t('pipeline.node.expand', { defaultValue: 'Expand' })
          }
          data-testid={`pipeline-node-toggle-${id}`}
          onClick={() => toggleExpanded(node.id)}
          className={clsx(
            'flex h-5 w-5 shrink-0 items-center justify-center rounded',
            'hover:bg-black/5 dark:hover:bg-white/10',
            tokens.classes.icon,
          )}
        >
          {node.expanded ? (
            <ChevronDown size={14} aria-hidden="true" />
          ) : (
            <ChevronRight size={14} aria-hidden="true" />
          )}
        </button>
      </div>

      {/* Per-node help — what it does (localized, plain language) */}
      {showHelp && (
        <p
          data-testid={`pipeline-node-help-${id}`}
          className={clsx('mt-1.5 text-xs leading-relaxed', tokens.classes.textSubtle)}
        >
          {t(`pipeline.nodehelp.${node.type}`, {
            defaultValue: t('pipeline.node.help_generic', {
              defaultValue:
                'Configure this step in the Inspector. It receives data from the connected step before it and passes its result on.',
            }),
          })}
        </p>
      )}

      {/* Param chips */}
      {paramChips.length > 0 && (
        <div
          data-testid={`pipeline-node-params-${id}`}
          className={clsx('mt-1 flex flex-wrap gap-1 text-xs', tokens.classes.textSubtle)}
        >
          {(node.expanded ? paramChips : paramChips.slice(0, 3)).map(
            ([key, value]) => (
              <span
                key={key}
                className="inline-flex items-center rounded bg-black/5 px-1.5 py-0.5 dark:bg-white/10"
              >
                <span className="font-medium">{key}</span>
                <span className="mx-1">:</span>
                <span className="max-w-[120px] truncate">{String(value)}</span>
              </span>
            ),
          )}
          {!node.expanded && paramChips.length > 3 && (
            <span className="inline-flex items-center px-1 text-xs italic">
              {t('pipeline.node.more_params', {
                defaultValue: '+{{count}} more',
                count: paramChips.length - 3,
              })}
            </span>
          )}
        </div>
      )}

      {/* Typed port rows */}
      {rows > 0 && (
        <div className="mt-2 space-y-1">
          {Array.from({ length: rows }).map((_, idx) => {
            const input = node.inputs[idx];
            const output = node.outputs[idx];
            return (
              <div
                key={idx}
                className="relative flex items-center justify-between text-xs"
              >
                <span className="flex items-center gap-1.5">
                  {input && (
                    <>
                      <Handle
                        type="target"
                        position={inputSide}
                        id={input.id}
                        data-testid={`pipeline-node-input-${id}-${input.id}`}
                        aria-label={t('pipeline.port.aria_input', {
                          defaultValue: 'input: {{label}}, type {{type}}',
                          label: input.label,
                          type: t(getPortTokens(input.dataType).labelKey, {
                            defaultValue: getPortTokens(input.dataType)
                              .labelDefault,
                          }),
                        })}
                        style={{
                          background: '#fff',
                          border: `1px solid ${getPortTokens(input.dataType).color}`,
                          width: 9,
                          height: 9,
                        }}
                      />
                      <PortGlyph type={input.dataType} />
                      <span>{input.label}</span>
                    </>
                  )}
                </span>
                <span className="flex items-center gap-1.5">
                  {output && (
                    <>
                      <span>{output.label}</span>
                      <PortGlyph type={output.dataType} />
                      <Handle
                        type="source"
                        position={outputSide}
                        id={output.id}
                        data-testid={`pipeline-node-output-${id}-${output.id}`}
                        aria-label={t('pipeline.port.aria_output', {
                          defaultValue: 'output: {{label}}, type {{type}}',
                          label: output.label,
                          type: t(getPortTokens(output.dataType).labelKey, {
                            defaultValue: getPortTokens(output.dataType)
                              .labelDefault,
                          }),
                        })}
                        style={{
                          background: '#fff',
                          border: `1px solid ${getPortTokens(output.dataType).color}`,
                          width: 9,
                          height: 9,
                        }}
                      />
                    </>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Live status strip — icon + text so state never relies on color alone */}
      {runNodeState && rv.Icon && (
        <div
          data-testid={`pipeline-node-status-${id}`}
          className={clsx(
            'mt-2 flex items-center gap-1.5 border-t pt-1.5 text-xs',
            tokens.classes.textSubtle,
          )}
          aria-live="polite"
        >
          <rv.Icon
            size={13}
            aria-hidden="true"
            className={rv.spin ? 'animate-spin' : undefined}
          />
          <span>
            {t(`pipeline.runstatus.${runNodeState.status}`, {
              defaultValue: String(runNodeState.status ?? ''),
            })}
          </span>
          {typeof runNodeState.took_ms === 'number' && (
            <span className="ms-auto tabular-nums">
              {t('pipeline.node.took_ms', {
                defaultValue: '{{ms}} ms',
                ms: runNodeState.took_ms,
              })}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default PipelineNode;
