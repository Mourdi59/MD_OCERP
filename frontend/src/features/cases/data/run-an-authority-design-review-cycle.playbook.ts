// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run an authority design review cycle".
//
// Open a review cycle against a document or model version, log the remarks
// that come back, respond to and decide each one, then close the cycle with a
// clear record of what changed and why. Content strings are key plus inline
// English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "run-an-authority-design-review-cycle",
  order: 1031,
  category: "quality",
  companyTypes: ["designer", "bim-consultant", "project-manager"],
  roles: ["design-lead", "document-controller", "project-manager"],
  stage: "design",
  icon: "FileSearch",
  titleKey: "cases.run_an_authority_design_review_cycle.title",
  titleDefault: "Run an authority design review cycle",
  descKey: "cases.run_an_authority_design_review_cycle.desc",
  descDefault:
    "Open a review cycle against a document version, log and respond to the remarks that come back, decide each one, and close the cycle with a clear record of what changed.",
  longDescKey: "cases.run_an_authority_design_review_cycle.longdesc",
  longDescDefault:
    "A design review that lives in scattered emails loses track of which remark was actually resolved. Running the cycle as one record, from the document that was reviewed to the decision on the last remark, is what lets the team prove the design was checked and closed.",
  estMinutes: 10,
  steps: [
    {
      id: "open-document",
      icon: "FolderOpen",
      inputs: [
        {
          labelKey:
            "cases.run_an_authority_design_review_cycle.step.open-document.in.design",
          label: "Design version",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_an_authority_design_review_cycle.step.open-document.out.reference",
          label: "Reviewed document reference",
        },
      ],
      titleKey: "cases.run_an_authority_design_review_cycle.step.open-document.title",
      titleDefault: "Bring in the document to be reviewed",
      whatKey: "cases.run_an_authority_design_review_cycle.step.open-document.what",
      whatDefault:
        "Pick the exact document or drawing version the authority will review, so the remarks that come back can be tied to a fixed point rather than a moving target.",
      whyKey: "cases.run_an_authority_design_review_cycle.step.open-document.why",
      whyDefault:
        "If the design keeps changing while the review is open, nobody can say which remark applies to which version. Fixing the reviewed version first is what keeps the cycle honest.",
      moduleLabel: "Documents",
      moduleLabelKey: "nav.documents",
      to: "/projects/:projectId/files",
    },
    {
      id: "open-cycle",
      icon: "MessageSquarePlus",
      inputs: [
        {
          labelKey:
            "cases.run_an_authority_design_review_cycle.step.open-cycle.in.reference",
          label: "Reviewed document reference",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_an_authority_design_review_cycle.step.open-cycle.out.cycle",
          label: "Open review cycle",
        },
      ],
      titleKey: "cases.run_an_authority_design_review_cycle.step.open-cycle.title",
      titleDefault: "Open the review cycle",
      whatKey: "cases.run_an_authority_design_review_cycle.step.open-cycle.what",
      whatDefault:
        "Start a review cycle against the document version, set the reviewing body and the response deadline, and share it with the team that will handle the remarks.",
      whyKey: "cases.run_an_authority_design_review_cycle.step.open-cycle.why",
      whyDefault:
        "An open cycle with a deadline is what stops a review sitting unanswered until it becomes a programme problem. Everyone can see it is live and whose turn it is to act.",
      moduleLabel: "Review Authority",
      moduleLabelKey: "review_authority.title",
      to: "/projects/:projectId/review-authority",
    },
    {
      id: "log-remarks",
      icon: "ListTodo",
      inputs: [
        {
          labelKey:
            "cases.run_an_authority_design_review_cycle.step.log-remarks.in.cycle",
          label: "Open review cycle",
        },
        {
          labelKey:
            "cases.run_an_authority_design_review_cycle.step.log-remarks.in.comments",
          label: "Authority comments",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_an_authority_design_review_cycle.step.log-remarks.out.remarks",
          label: "Logged remarks",
        },
        {
          labelKey:
            "cases.run_an_authority_design_review_cycle.step.log-remarks.out.responses",
          label: "Recorded responses",
        },
      ],
      titleKey: "cases.run_an_authority_design_review_cycle.step.log-remarks.title",
      titleDefault: "Log and respond to each remark",
      whatKey: "cases.run_an_authority_design_review_cycle.step.log-remarks.what",
      whatDefault:
        "Log every remark the authority raises as its own item, assign it to whoever owns the answer, and record the response against the specific point it addresses.",
      whyKey: "cases.run_an_authority_design_review_cycle.step.log-remarks.why",
      whyDefault:
        "A remark answered in a general reply is a remark that is easy to argue was never actually addressed. One remark, one response, is what makes the closeout defensible.",
      moduleLabel: "Review Authority",
      moduleLabelKey: "review_authority.title",
      to: "/projects/:projectId/review-authority",
    },
    {
      id: "close-cycle",
      icon: "CheckCheck",
      inputs: [
        {
          labelKey:
            "cases.run_an_authority_design_review_cycle.step.close-cycle.in.responses",
          label: "Recorded responses",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.run_an_authority_design_review_cycle.step.close-cycle.out.decisions",
          label: "Remark decisions",
        },
        {
          labelKey:
            "cases.run_an_authority_design_review_cycle.step.close-cycle.out.closed",
          label: "Closed review record",
        },
      ],
      titleKey: "cases.run_an_authority_design_review_cycle.step.close-cycle.title",
      titleDefault: "Decide each remark and close the cycle",
      whatKey: "cases.run_an_authority_design_review_cycle.step.close-cycle.what",
      whatDefault:
        "Mark each remark as accepted, addressed or disputed, then close the cycle once every remark has a decision, leaving a full record of what changed and why.",
      whyKey: "cases.run_an_authority_design_review_cycle.step.close-cycle.why",
      whyDefault:
        "An unclosed remark is a risk the design can still be challenged on later. Closing the cycle with a decision on every point is what turns the review into a finished design check, not an open thread.",
      moduleLabel: "Review Authority",
      moduleLabelKey: "review_authority.title",
      to: "/projects/:projectId/review-authority",
    },
  ],
};

export default playbook;
