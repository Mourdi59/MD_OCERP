// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Submit a permit package to the authority".
//
// Assemble the documents an authority submission needs, build the submission
// and validate it against the checking authority's requirements, generate the
// export package, then send it and track its status. Content strings are key
// plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "submit-a-permit-package-to-the-authority",
  order: 1030,
  category: "quality",
  companyTypes: ["general-contractor", "project-manager", "designer"],
  roles: ["document-controller", "design-lead", "project-manager"],
  stage: "define",
  icon: "Landmark",
  titleKey: "cases.submit_a_permit_package_to_the_authority.title",
  titleDefault: "Submit a permit package to the authority",
  descKey: "cases.submit_a_permit_package_to_the_authority.desc",
  descDefault:
    "Pull together the drawings and supporting documents an authority submission needs, build and validate the submission, generate the package, then send it and track it through to a decision.",
  longDescKey: "cases.submit_a_permit_package_to_the_authority.longdesc",
  longDescDefault:
    "A rejected submission does not just cost the resubmission, it costs the weeks the reviewing body takes to look at it a second time. Assembling the right documents up front and validating the package before it goes out is what keeps a submission moving on the first pass.",
  estMinutes: 12,
  steps: [
    {
      id: "assemble",
      icon: "FolderInput",
      inputs: [
        {
          labelKey:
            "cases.submit_a_permit_package_to_the_authority.step.assemble.in.drawings",
          label: "Design drawings",
        },
        {
          labelKey:
            "cases.submit_a_permit_package_to_the_authority.step.assemble.in.requirements",
          label: "Authority requirements",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.submit_a_permit_package_to_the_authority.step.assemble.out.set",
          label: "Document set",
        },
      ],
      titleKey: "cases.submit_a_permit_package_to_the_authority.step.assemble.title",
      titleDefault: "Assemble the required documents",
      whatKey: "cases.submit_a_permit_package_to_the_authority.step.assemble.what",
      whatDefault:
        "Gather the drawings, calculations, reports and forms the submission needs, and check each one is current before it goes into the package.",
      whyKey: "cases.submit_a_permit_package_to_the_authority.step.assemble.why",
      whyDefault:
        "A missing report or an outdated drawing is the single most common reason a package bounces back unread. Sorting the set first means the build step starts from documents that are actually complete.",
      moduleLabel: "Documents",
      moduleLabelKey: "nav.documents",
      to: "/projects/:projectId/files",
    },
    {
      id: "build",
      icon: "FileCheck2",
      inputs: [
        {
          labelKey:
            "cases.submit_a_permit_package_to_the_authority.step.build.in.set",
          label: "Document set",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.submit_a_permit_package_to_the_authority.step.build.out.submission",
          label: "Draft submission",
        },
        {
          labelKey:
            "cases.submit_a_permit_package_to_the_authority.step.build.out.checks",
          label: "Validation results",
        },
      ],
      titleKey: "cases.submit_a_permit_package_to_the_authority.step.build.title",
      titleDefault: "Build and validate the submission",
      whatKey: "cases.submit_a_permit_package_to_the_authority.step.build.what",
      whatDefault:
        "Create the submission, attach the document set, and run the built-in validation so missing items, wrong formats and unsigned pages surface before anyone outside the team sees them.",
      whyKey: "cases.submit_a_permit_package_to_the_authority.step.build.why",
      whyDefault:
        "Catching a gap here costs minutes. Catching the same gap after the authority has opened the file costs the whole review cycle again.",
      moduleLabel: "Authority Submissions",
      moduleLabelKey: "authority_submission.title",
      to: "/projects/:projectId/authority-submissions",
    },
    {
      id: "package",
      icon: "PackageCheck",
      inputs: [
        {
          labelKey:
            "cases.submit_a_permit_package_to_the_authority.step.package.in.submission",
          label: "Validated submission",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.submit_a_permit_package_to_the_authority.step.package.out.export",
          label: "Export package",
        },
      ],
      titleKey: "cases.submit_a_permit_package_to_the_authority.step.package.title",
      titleDefault: "Generate the export package",
      whatKey: "cases.submit_a_permit_package_to_the_authority.step.package.what",
      whatDefault:
        "Generate the package in the format the authority accepts, with a consistent file structure and a cover index so a reviewer can find every item without asking.",
      whyKey: "cases.submit_a_permit_package_to_the_authority.step.package.why",
      whyDefault:
        "A clean, indexed package reads as a competent submission before the reviewer has opened a single drawing. A loose pile of files invites the kind of scrutiny that slows everything down.",
      moduleLabel: "Authority Submissions",
      moduleLabelKey: "authority_submission.title",
      to: "/projects/:projectId/authority-submissions",
    },
    {
      id: "submit",
      icon: "Send",
      inputs: [
        {
          labelKey:
            "cases.submit_a_permit_package_to_the_authority.step.submit.in.export",
          label: "Export package",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.submit_a_permit_package_to_the_authority.step.submit.out.status",
          label: "Submission status",
        },
      ],
      titleKey: "cases.submit_a_permit_package_to_the_authority.step.submit.title",
      titleDefault: "Submit and track the decision",
      whatKey: "cases.submit_a_permit_package_to_the_authority.step.submit.what",
      whatDefault:
        "Send the package to the authority and track its status, review comments and decision date in one place instead of a side email thread.",
      whyKey: "cases.submit_a_permit_package_to_the_authority.step.submit.why",
      whyDefault:
        "A submission that only lives in someone's inbox is a submission the rest of the team cannot plan around. Tracking it against the record keeps the programme honest about when approval will actually land.",
      moduleLabel: "Authority Submissions",
      moduleLabelKey: "authority_submission.title",
      to: "/projects/:projectId/authority-submissions",
    },
  ],
};

export default playbook;
