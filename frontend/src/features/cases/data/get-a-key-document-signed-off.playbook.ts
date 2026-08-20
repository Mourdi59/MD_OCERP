// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Get a key document signed off".
//
// Pick the document that needs formal sign-off, open a signing session with
// the right signatories, collect their attestations, then download the signed
// manifest as the record. Content strings are key plus inline English default
// and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "get-a-key-document-signed-off",
  order: 1032,
  category: "handover",
  companyTypes: ["general-contractor", "project-manager", "owner-operator"],
  roles: ["document-controller", "contract-administrator", "project-manager"],
  stage: "handover",
  icon: "PenTool",
  titleKey: "cases.get_a_key_document_signed_off.title",
  titleDefault: "Get a key document signed off",
  descKey: "cases.get_a_key_document_signed_off.desc",
  descDefault:
    "Pick the document that needs formal sign-off, open a signing session with the right signatories, collect their attestations, and download the signed manifest as the record.",
  longDescKey: "cases.get_a_key_document_signed_off.longdesc",
  longDescDefault:
    "A completion certificate or a handover statement without a clean signature trail is worth little in a dispute. Running the sign-off as one tracked session, from picking the document to the downloaded manifest, is what makes it stand up later.",
  estMinutes: 8,
  steps: [
    {
      id: "pick-document",
      icon: "FileText",
      inputs: [
        {
          labelKey:
            "cases.get_a_key_document_signed_off.step.pick-document.in.candidates",
          label: "Documents awaiting sign-off",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.get_a_key_document_signed_off.step.pick-document.out.selected",
          label: "Selected document",
        },
      ],
      titleKey: "cases.get_a_key_document_signed_off.step.pick-document.title",
      titleDefault: "Pick the document",
      whatKey: "cases.get_a_key_document_signed_off.step.pick-document.what",
      whatDefault:
        "Find the final version of the certificate, statement or agreement that needs signing, and confirm it is the one everyone has actually agreed to, not an earlier draft.",
      whyKey: "cases.get_a_key_document_signed_off.step.pick-document.why",
      whyDefault:
        "A signature on the wrong version is worse than no signature at all, it looks final while it is not. Confirming the exact document first is what the rest of the sign-off depends on.",
      moduleLabel: "Documents",
      moduleLabelKey: "nav.documents",
      to: "/projects/:projectId/files",
    },
    {
      id: "open-session",
      icon: "UserPlus",
      inputs: [
        {
          labelKey:
            "cases.get_a_key_document_signed_off.step.open-session.in.selected",
          label: "Selected document",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.get_a_key_document_signed_off.step.open-session.out.session",
          label: "Signing session",
        },
      ],
      titleKey: "cases.get_a_key_document_signed_off.step.open-session.title",
      titleDefault: "Open the session and add signatories",
      whatKey: "cases.get_a_key_document_signed_off.step.open-session.what",
      whatDefault:
        "Start a signing session on the document, add every party who needs to sign in the right order, and send it out.",
      whyKey: "cases.get_a_key_document_signed_off.step.open-session.why",
      whyDefault:
        "Chasing signatures over email loses track of who has actually signed and who is still sitting on it. A session with a fixed signatory list is what lets you see the gap at a glance.",
      moduleLabel: "E-Signatures",
      moduleLabelKey: "signing.title",
      to: "/signing",
    },
    {
      id: "collect",
      icon: "Signature",
      inputs: [
        {
          labelKey:
            "cases.get_a_key_document_signed_off.step.collect.in.session",
          label: "Signing session",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.get_a_key_document_signed_off.step.collect.out.attestations",
          label: "Recorded attestations",
        },
      ],
      titleKey: "cases.get_a_key_document_signed_off.step.collect.title",
      titleDefault: "Collect the attestations",
      whatKey: "cases.get_a_key_document_signed_off.step.collect.what",
      whatDefault:
        "Track each signatory as they sign, follow up the ones still outstanding, and let the session capture the time and identity behind every signature.",
      whyKey: "cases.get_a_key_document_signed_off.step.collect.why",
      whyDefault:
        "A signature with no timestamp or identity behind it is easy to dispute later. Capturing both as part of the session is what makes the sign-off actually evidential.",
      moduleLabel: "E-Signatures",
      moduleLabelKey: "signing.title",
      to: "/signing",
    },
    {
      id: "download",
      icon: "Download",
      inputs: [
        {
          labelKey:
            "cases.get_a_key_document_signed_off.step.download.in.attestations",
          label: "Recorded attestations",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.get_a_key_document_signed_off.step.download.out.manifest",
          label: "Signed manifest",
        },
      ],
      titleKey: "cases.get_a_key_document_signed_off.step.download.title",
      titleDefault: "Download the signed manifest",
      whatKey: "cases.get_a_key_document_signed_off.step.download.what",
      whatDefault:
        "Once every signatory has signed, download the manifest that binds the document to its signatures and file it with the project record.",
      whyKey: "cases.get_a_key_document_signed_off.step.download.why",
      whyDefault:
        "The manifest is the piece that outlives the session, it is what you hand to a client, an auditor or a court years later. Filing it now is easier than trying to reconstruct the trail after the fact.",
      moduleLabel: "E-Signatures",
      moduleLabelKey: "signing.title",
      to: "/signing",
    },
  ],
};

export default playbook;
