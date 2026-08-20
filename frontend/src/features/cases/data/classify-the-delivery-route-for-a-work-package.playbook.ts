// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Classify the delivery route for a work package".
//
// Pick the work type, classify the delivery and approval route it needs to
// follow, confirm the route with the team, then carry it straight into the
// authority submission it triggers. Content strings are key plus inline
// English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "classify-the-delivery-route-for-a-work-package",
  order: 1034,
  category: "planning",
  companyTypes: ["project-manager", "designer", "developer-client"],
  roles: ["project-manager", "design-lead", "contract-administrator"],
  stage: "define",
  icon: "SignpostBig",
  titleKey: "cases.classify_the_delivery_route_for_a_work_package.title",
  titleDefault: "Classify the delivery route for a work package",
  descKey: "cases.classify_the_delivery_route_for_a_work_package.desc",
  descDefault:
    "Pick the work type, classify the delivery and approval route it needs to follow, confirm the route with the team, then carry it into an authority submission.",
  longDescKey: "cases.classify_the_delivery_route_for_a_work_package.longdesc",
  longDescDefault:
    "Two work packages that look similar can need completely different approval routes depending on scope, use and location. Classifying the route before the design or the programme is locked in is what stops a team discovering the real route halfway through.",
  estMinutes: 7,
  steps: [
    {
      id: "pick-work",
      icon: "SearchCheck",
      inputs: [
        {
          labelKey:
            "cases.classify_the_delivery_route_for_a_work_package.step.pick-work.in.package",
          label: "Work package",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.classify_the_delivery_route_for_a_work_package.step.pick-work.out.profile",
          label: "Work profile",
        },
      ],
      titleKey: "cases.classify_the_delivery_route_for_a_work_package.step.pick-work.title",
      titleDefault: "Describe the work type",
      whatKey: "cases.classify_the_delivery_route_for_a_work_package.step.pick-work.what",
      whatDefault:
        "Set out what the work package actually is: its scope, its use, its scale and where it sits, the details the routing depends on.",
      whyKey: "cases.classify_the_delivery_route_for_a_work_package.step.pick-work.why",
      whyDefault:
        "The route is only as accurate as the description behind it. A vague answer here produces a route classification nobody can actually rely on later.",
      moduleLabel: "Route Classifier",
      moduleLabelKey: "project_route.title",
      to: "/projects/:projectId/project-route",
    },
    {
      id: "classify",
      icon: "GitBranch",
      inputs: [
        {
          labelKey:
            "cases.classify_the_delivery_route_for_a_work_package.step.classify.in.profile",
          label: "Work profile",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.classify_the_delivery_route_for_a_work_package.step.classify.out.route",
          label: "Classified route",
        },
      ],
      titleKey: "cases.classify_the_delivery_route_for_a_work_package.step.classify.title",
      titleDefault: "Classify the delivery route",
      whatKey: "cases.classify_the_delivery_route_for_a_work_package.step.classify.what",
      whatDefault:
        "Run the work profile through the route classifier to get the delivery and approval path it needs to follow, along with the reviews and sign-offs that path requires.",
      whyKey: "cases.classify_the_delivery_route_for_a_work_package.step.classify.why",
      whyDefault:
        "Getting the route wrong is not a paperwork slip, it means budgeting and programming for the wrong sequence of approvals entirely. Classifying it early is what lets the rest of the plan be built on solid ground.",
      moduleLabel: "Route Classifier",
      moduleLabelKey: "project_route.title",
      to: "/projects/:projectId/project-route",
    },
    {
      id: "confirm",
      icon: "UserCheck",
      inputs: [
        {
          labelKey:
            "cases.classify_the_delivery_route_for_a_work_package.step.confirm.in.route",
          label: "Classified route",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.classify_the_delivery_route_for_a_work_package.step.confirm.out.confirmed",
          label: "Confirmed route",
        },
      ],
      titleKey: "cases.classify_the_delivery_route_for_a_work_package.step.confirm.title",
      titleDefault: "Confirm the route with the team",
      whatKey: "cases.classify_the_delivery_route_for_a_work_package.step.confirm.what",
      whatDefault:
        "Walk the classified route past whoever owns programme and design sign-off, and lock it in as the route the package will actually follow.",
      whyKey: "cases.classify_the_delivery_route_for_a_work_package.step.confirm.why",
      whyDefault:
        "A route nobody has agreed to is still just a suggestion. Confirming it turns the classification into the plan the rest of the team can commit dates and fees against.",
      moduleLabel: "Route Classifier",
      moduleLabelKey: "project_route.title",
      to: "/projects/:projectId/project-route",
    },
    {
      id: "carry-forward",
      icon: "ArrowRightCircle",
      inputs: [
        {
          labelKey:
            "cases.classify_the_delivery_route_for_a_work_package.step.carry-forward.in.confirmed",
          label: "Confirmed route",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.classify_the_delivery_route_for_a_work_package.step.carry-forward.out.submission",
          label: "Authority submission started",
        },
      ],
      titleKey: "cases.classify_the_delivery_route_for_a_work_package.step.carry-forward.title",
      titleDefault: "Carry the route into the submission",
      whatKey: "cases.classify_the_delivery_route_for_a_work_package.step.carry-forward.what",
      whatDefault:
        "Start the authority submission the classified route requires, with the route and its reasoning already attached so the submission opens on the right track.",
      whyKey: "cases.classify_the_delivery_route_for_a_work_package.step.carry-forward.why",
      whyDefault:
        "Reclassifying the route at the submission stage, after the design has already moved on, is expensive rework. Carrying the confirmed route straight through is what keeps the two records in step.",
      moduleLabel: "Authority Submissions",
      moduleLabelKey: "authority_submission.title",
      to: "/projects/:projectId/authority-submissions",
    },
  ],
};

export default playbook;
