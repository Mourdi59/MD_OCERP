/** Upload dialog — multi-file uploader for the file manager.
 *
 * Reuses the documents module's upload endpoint and the global upload
 * queue store so completed uploads roll up into the same FloatingQueuePanel
 * that runs everywhere else in the app.
 *
 * Migration target: TODO — once each kind has its own upload endpoint
 * (BIM, DWG, photos), branch on selectedKind here and route accordingly.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { UploadCloud, X, FileUp } from 'lucide-react';
import clsx from 'clsx';
import { uuid } from '@/shared/lib/browser';
import { useToastStore } from '@/stores/useToastStore';
import { useAuthStore } from '@/stores/useAuthStore';
import { useUploadQueueStore } from '@/stores/useUploadQueueStore';
import { fileManagerKeys } from '../hooks';
import type { FileKind } from '../types';

interface UploadDialogProps {
  open: boolean;
  projectId: string;
  defaultKind: FileKind | null;
  onClose: () => void;
}

export function UploadDialog({
  open,
  projectId,
  defaultKind,
  onClose,
}: UploadDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const addQueueTask = useUploadQueueStore((s) => s.addTask);
  const updateQueueTask = useUploadQueueStore((s) => s.updateTask);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);

  // Map FileKind → documents-module category. The current upload endpoint
  // only accepts the documents-module taxonomy; mapping here keeps the
  // unified UI honest while we wait for per-kind endpoints (TODO above).
  const categoryForKind = useCallback((kind: FileKind | null): string => {
    if (kind === 'photo') return 'photo';
    if (kind === 'sheet' || kind === 'dwg_drawing' || kind === 'bim_model') return 'drawing';
    return 'other';
  }, []);

  // Lock background scroll when modal is open.
  useEffect(() => {
    if (!open) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = original;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  const doUpload = useCallback(
    async (files: FileList | File[]) => {
      if (!projectId) {
        addToast({
          type: 'error',
          title: t('files.upload_no_project', { defaultValue: 'No active project' }),
        });
        return;
      }

      const fileArray = Array.from(files);
      if (fileArray.length === 0) return;

      const validFiles = fileArray;
      if (validFiles.length === 0) return;

      const token = useAuthStore.getState().accessToken;
      const cat = categoryForKind(defaultKind);
      setUploading(true);

      for (const file of validFiles) {
        const taskId = uuid();
        addQueueTask({
          id: taskId,
          type: 'file_upload',
          filename: file.name,
          status: 'processing',
          progress: 0,
          message: t('files.uploading', { defaultValue: 'Uploading…' }),
        });

        // Fire-and-forget — same pattern as DocumentsPage so progress
        // shows up in the global FloatingQueuePanel.
        (async () => {
          try {
            const formData = new FormData();
            formData.append('file', file);

            const headers: Record<string, string> = { 'X-DDC-Client': 'OE/1.0' };
            if (token) headers['Authorization'] = `Bearer ${token}`;

            // Estimate progress so the user gets feedback while the
            // upload is still in flight.
            const estimatedMs = Math.max(2000, (file.size / (1024 * 1024)) * 500);
            const progressTimer = setInterval(() => {
              const task = useUploadQueueStore.getState().tasks.find((tk) => tk.id === taskId);
              if (task && task.status === 'processing' && task.progress < 90) {
                updateQueueTask(taskId, { progress: task.progress + 5 });
              }
            }, estimatedMs / 18);

            const res = await fetch(
              `/api/v1/documents/upload/?project_id=${projectId}&category=${cat}`,
              { method: 'POST', headers, body: formData },
            );

            clearInterval(progressTimer);

            if (!res.ok) {
              let detail = file.name;
              try {
                const body = await res.json();
                if (body?.detail) detail = body.detail;
              } catch {
                /* ignore — keep filename */
              }
              updateQueueTask(taskId, {
                status: 'error',
                error: detail,
                completedAt: Date.now(),
              });
            } else {
              updateQueueTask(taskId, {
                status: 'completed',
                progress: 100,
                message: t('files.uploaded', { defaultValue: 'Uploaded' }),
                completedAt: Date.now(),
              });
              queryClient.invalidateQueries({ queryKey: [fileManagerKeys.tree, projectId] });
              queryClient.invalidateQueries({ queryKey: [fileManagerKeys.list, projectId] });
            }
          } catch (err) {
            updateQueueTask(taskId, {
              status: 'error',
              error: err instanceof Error ? err.message : 'Upload failed',
              completedAt: Date.now(),
            });
          }
        })();
      }

      addToast({
        type: 'info',
        title: t('files.upload_queued', {
          defaultValue: '{{count}} file(s) queued',
          count: validFiles.length,
        }),
      });

      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
      onClose();
    },
    [
      projectId,
      defaultKind,
      categoryForKind,
      addToast,
      addQueueTask,
      updateQueueTask,
      queryClient,
      t,
      onClose,
    ],
  );

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t('files.upload', { defaultValue: 'Upload files' })}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-lg animate-fade-in"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg mx-4 rounded-xl bg-surface-elevated shadow-2xl border border-border-light overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-border-light">
          <h3 className="text-sm font-semibold text-content-primary">
            {t('files.upload', { defaultValue: 'Upload files' })}
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close', { defaultValue: 'Close' })}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-content-tertiary hover:bg-surface-secondary hover:text-content-primary"
          >
            <X size={14} />
          </button>
        </div>

        <div className="p-5">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files && e.target.files.length > 0) {
                void doUpload(e.target.files);
              }
            }}
          />

          <div
            role="button"
            tabIndex={0}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={(e) => {
              e.preventDefault();
              setDragOver(false);
            }}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              if (e.dataTransfer.files.length > 0) void doUpload(e.dataTransfer.files);
            }}
            className={clsx(
              'flex flex-col items-center justify-center text-center cursor-pointer',
              'rounded-xl border-2 border-dashed py-10 px-6 transition-all',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue focus-visible:ring-offset-1',
              dragOver
                ? 'border-oe-blue bg-oe-blue/5 scale-[1.005] shadow-md'
                : 'border-border-medium bg-gradient-to-br from-blue-50/60 via-transparent to-violet-50/40 dark:from-blue-950/20 dark:to-violet-950/20 hover:border-oe-blue/50',
            )}
          >
            <div
              className={clsx(
                'mb-3 flex h-14 w-14 items-center justify-center rounded-xl transition-all',
                dragOver
                  ? 'bg-oe-blue/15'
                  : 'bg-gradient-to-br from-oe-blue/10 to-violet-500/10',
              )}
            >
              <UploadCloud size={26} className="text-oe-blue" />
            </div>
            <p className="text-sm font-semibold text-content-primary">
              {dragOver
                ? t('files.upload_drop_here', { defaultValue: 'Drop files to upload' })
                : t('files.upload_drag', { defaultValue: 'Drag & drop files here' })}
            </p>
            <p className="mt-1 text-xs text-content-tertiary">
              {t('files.upload_hint', {
                defaultValue: 'PDF, images, Excel, DWG, IFC - any file type',
              })}
            </p>
            <button
              type="button"
              disabled={uploading}
              onClick={(e) => {
                e.stopPropagation();
                fileInputRef.current?.click();
              }}
              className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold bg-oe-blue text-white hover:bg-oe-blue-hover shadow-sm transition-colors disabled:opacity-60"
            >
              <FileUp size={14} />
              {t('files.upload_browse', { defaultValue: 'Browse files' })}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
