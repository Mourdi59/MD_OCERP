// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "See every field mark on one sheet".
//
// Open a drawing with every overlay the platform holds for that page composited
// on it, read what has actually been recorded there, add a pin in place and
// take the items that need owning into the punch list. Content strings are key
// plus inline English default and live only here.

import type { Playbook } from "../types";

const playbook: Playbook = {
  id: "see-every-field-mark-on-one-sheet",
  order: 1043,
  category: "site",
  companyTypes: ["general-contractor", "subcontractor", "project-manager"],
  roles: ["site-manager", "foreman", "document-controller"],
  stage: "build",
  icon: "Layers",
  titleKey: "cases.see_every_field_mark_on_one_sheet.title",
  titleDefault: "See every field mark on one sheet",
  descKey: "cases.see_every_field_mark_on_one_sheet.desc",
  descDefault:
    "Open one drawing and see every mark the project has recorded against it, punch pins, plan pins, markups, takeoff measurements and photos, each on its own toggle, then drop a pin where something needs attention.",
  longDescKey: "cases.see_every_field_mark_on_one_sheet.longdesc",
  longDescDefault:
    "Field marks scatter by tool: the snag sits in the punch list, the dimension in takeoff, the annotation in markups and the photo in the gallery, so nobody ever looks at a drawing and sees all of it at once. This case opens a sheet with all five overlays composited on the page, each carrying its own live count for that page, so you can read what has actually happened at that location, add to it in place, and hand the items that need closing to the register that owns them.",
  estMinutes: 7,
  steps: [
    {
      id: "open",
      icon: "FolderOpen",
      inputs: [
        {
          labelKey: "cases.see_every_field_mark_on_one_sheet.step.open.in.set",
          label: "Project drawing set",
        },
        {
          labelKey: "cases.see_every_field_mark_on_one_sheet.step.open.in.area",
          label: "Area you are working",
        },
      ],
      outputs: [
        {
          labelKey: "cases.see_every_field_mark_on_one_sheet.step.open.out.sheet",
          label: "Open sheet page",
        },
        {
          labelKey:
            "cases.see_every_field_mark_on_one_sheet.step.open.out.revision",
          label: "Revision it is on",
        },
      ],
      titleKey: "cases.see_every_field_mark_on_one_sheet.step.open.title",
      titleDefault: "Open the sheet",
      whatKey: "cases.see_every_field_mark_on_one_sheet.step.open.what",
      whatDefault:
        "Pick the drawing and the page covering the area you are working, and check the revision indicator beside it before you read anything off the page.",
      whyKey: "cases.see_every_field_mark_on_one_sheet.step.open.why",
      whyDefault:
        "Marks are recorded against a page, not a project, so being on the right page of the right sheet is the whole basis of what follows. The revision matters too, because a snag raised against revision B can be describing a detail that revision C already deleted.",
      moduleLabel: "Plan Room",
      moduleLabelKey: "nav.plan_room",
      to: "/plan-room",
    },
    {
      id: "layers",
      icon: "Layers",
      inputs: [
        {
          labelKey: "cases.see_every_field_mark_on_one_sheet.step.layers.in.sheet",
          label: "Open sheet page",
        },
        {
          labelKey:
            "cases.see_every_field_mark_on_one_sheet.step.layers.in.overlays",
          label: "Recorded field marks",
        },
      ],
      outputs: [
        {
          labelKey:
            "cases.see_every_field_mark_on_one_sheet.step.layers.out.picture",
          label: "One composited picture",
        },
        {
          labelKey:
            "cases.see_every_field_mark_on_one_sheet.step.layers.out.counts",
          label: "Per-layer count for the page",
        },
      ],
      titleKey: "cases.see_every_field_mark_on_one_sheet.step.layers.title",
      titleDefault: "Turn the layers on and read what is there",
      whatKey: "cases.see_every_field_mark_on_one_sheet.step.layers.what",
      whatDefault:
        "Switch the five overlays on and off, punch pins, plan pins, markups, takeoff measurements and photos, and read the count each one carries for this page. Turn the noisy ones off when you want to look at one kind of mark on its own.",
      whyKey: "cases.see_every_field_mark_on_one_sheet.step.layers.why",
      whyDefault:
        "Every trade records into its own tool, so the full picture only exists in somebody's head. Seeing that one stair core carries nine punch pins, two markups and no photos at all tells you in a second what a walk round the building and four separate registers would take an afternoon to say.",
      moduleLabel: "Plan Room",
      moduleLabelKey: "nav.plan_room",
      to: "/plan-room",
    },
    {
      id: "pin",
      icon: "MapPin",
      inputs: [
        {
          labelKey: "cases.see_every_field_mark_on_one_sheet.step.pin.in.finding",
          label: "Something found on site",
        },
        {
          labelKey: "cases.see_every_field_mark_on_one_sheet.step.pin.in.location",
          label: "Where it is on the sheet",
        },
      ],
      outputs: [
        {
          labelKey: "cases.see_every_field_mark_on_one_sheet.step.pin.out.pin",
          label: "Plan pin on the page",
        },
        {
          labelKey: "cases.see_every_field_mark_on_one_sheet.step.pin.out.note",
          label: "Note the next person can act on",
        },
      ],
      titleKey: "cases.see_every_field_mark_on_one_sheet.step.pin.title",
      titleDefault: "Drop a pin where something needs attention",
      whatKey: "cases.see_every_field_mark_on_one_sheet.step.pin.what",
      whatDefault:
        "Click the exact point on the sheet and drop a plan pin there with the note that makes it actionable. If you put one down in the wrong place, open it and remove it, the page is not a document you have to reissue.",
      whyKey: "cases.see_every_field_mark_on_one_sheet.step.pin.why",
      whyDefault:
        "A note that reads crack near the lift lobby sends the next person hunting along forty metres of corridor. A pin sitting on the drawing at the point in question is unambiguous, and it still means the same thing to somebody who was not on the walk with you.",
      moduleLabel: "Plan Room",
      moduleLabelKey: "nav.plan_room",
      to: "/plan-room",
    },
    {
      id: "act",
      icon: "ListChecks",
      inputs: [
        {
          labelKey: "cases.see_every_field_mark_on_one_sheet.step.act.in.pins",
          label: "Pins read off the sheet",
        },
        {
          labelKey: "cases.see_every_field_mark_on_one_sheet.step.act.in.trades",
          label: "Trade responsible",
        },
      ],
      outputs: [
        {
          labelKey: "cases.see_every_field_mark_on_one_sheet.step.act.out.items",
          label: "Owned punch items",
        },
        {
          labelKey: "cases.see_every_field_mark_on_one_sheet.step.act.out.status",
          label: "Priority and status",
        },
      ],
      titleKey: "cases.see_every_field_mark_on_one_sheet.step.act.title",
      titleDefault: "Open a pin and act on it",
      whatKey: "cases.see_every_field_mark_on_one_sheet.step.act.what",
      whatDefault:
        "Click a pin to read its detail on the sheet, then take the ones that need chasing into the punch list, where an item carries a priority, an owner and a status through to closure.",
      whyKey: "cases.see_every_field_mark_on_one_sheet.step.act.why",
      whyDefault:
        "The plan room shows you what has been recorded, it is not where work gets closed out. Marks that never become owned items are exactly the ones still sitting on the drawing at handover, with nobody able to say whether they were ever fixed.",
      moduleLabel: "Punch List",
      moduleLabelKey: "nav.punchlist",
      to: "/punchlist",
    },
  ],
};

export default playbook;
