// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// What the screen tests share: the answers of an empty project, and the page under a router.

import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { MockedObject } from 'vitest';

import type * as Api from '../api';
import { QualityConceptPage } from '../QualityConceptPage';
import { catalogue, concept, matrix, page, readiness } from './fixtures';

/** The answers of a project that has a draft concept and nothing else. */
export function emptyProject(api: MockedObject<typeof Api>): void {
  api.getConcept.mockResolvedValue(concept());
  api.getCatalogue.mockResolvedValue(catalogue);
  api.getReadiness.mockResolvedValue(readiness);
  api.getValidation.mockResolvedValue(page([]));
  api.listRevisions.mockResolvedValue(page([]));
  api.listStandards.mockResolvedValue(page([]));
  api.listRequirements.mockResolvedValue(page([]));
  api.listCertifications.mockResolvedValue({ ...page([]), findings: [] });
  api.listProofs.mockResolvedValue(page([]));
  api.getCoverage.mockResolvedValue({ ...page([]), findings: [] });
  api.getStageMatrix.mockResolvedValue(matrix([], []));
  api.listUnits.mockResolvedValue(page([]));
  api.listSurveys.mockResolvedValue({ ...page([]), findings: [] });
  api.listExpertReports.mockResolvedValue(page([]));
  api.listLinks.mockResolvedValue(page([]));
}

export function renderPage(tab?: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const at = `/projects/p1/quality-concept${tab ? `?tab=${tab}` : ''}`;
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[at]}>
        <Routes>
          <Route path="/projects/:projectId/quality-concept" element={<QualityConceptPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
