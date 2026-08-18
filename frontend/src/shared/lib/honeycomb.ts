// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The honeycomb: the two hexagon clip paths the product draws with, and the
// geometry that lays cells out into an interlocking band.
//
// TWO SHAPES, NOT ONE. They are different hexagons and they are not
// interchangeable:
//
//   HEX_PORTRAIT_CLIP  points at the TOP and BOTTOM, flat left and right
//                      edges. This is the crop a person's photo is cut to on
//                      a case card. A portrait wants the tall axis vertical.
//
//   HEX_CELL_CLIP      points at the LEFT and RIGHT, flat top and bottom
//                      edges. This is the face of a module cell in the
//                      honeycomb. A label wants the wide axis horizontal, and
//                      this orientation is what the layout maths below tiles.
//
// Both used to be written out by hand at their call sites - the portrait one
// in three separate places, once as a bare inline literal with no name at all.
// Three copies of a polygon do not stay equal, and a cell that is a few
// percent off its neighbours reads as a rendering fault rather than as a
// design. They live here so there is one of each.
//
// The clip paths match the marketing site's honeycomb component character for
// character, so a case card and the public page for the same case cut to the
// same shape. Changing one here without changing it there splits them.

/**
 * Pointy-top hexagon: vertices at top and bottom centre, flat left and right
 * edges. Used to crop portraits on case cards and on the sign-in art.
 */
export const HEX_PORTRAIT_CLIP =
  'polygon(50% 2%, 100% 26%, 100% 74%, 50% 98%, 0% 74%, 0% 26%)';

/**
 * Flat-top hexagon: flat top and bottom edges, vertices at left and right.
 * The face of a module cell in a honeycomb, and the shape {@link hiveBand}
 * tiles. Its 6:1 width-to-inset ratio is what makes neighbouring columns
 * interlock at a 3/4 horizontal pitch.
 */
export const HEX_CELL_CLIP =
  'polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%)';

/**
 * Height of a flat-top hex as a fraction of its width (sqrt(3)/2). A cell laid
 * out at any other ratio stops interlocking and leaves gaps between columns.
 */
export const HEX_ASPECT = 0.866;

/** Where one cell sits inside the stage, in pixels from its top-inline-start corner. */
export interface HivePlacement {
  /** Offset along the inline axis. Apply as `insetInlineStart`, NEVER as
   *  `left`: the app ships Arabic, Hebrew, Persian and Urdu, and a band
   *  anchored to the left edge reads backwards in all four. */
  inlineStart: number;
  /** Offset from the top of the stage. */
  top: number;
}

/** A laid-out honeycomb: where every cell goes, and how big the stage must be. */
export interface HiveLayout {
  /** One placement per cell, in the order the cells were given. */
  placements: HivePlacement[];
  /** Width of the box that contains every cell. */
  width: number;
  /** Height of the box that contains every cell. */
  height: number;
  /** Width of a single cell. */
  cellWidth: number;
  /** Height of a single cell (`cellWidth * HEX_ASPECT`, rounded). */
  cellHeight: number;
}

/**
 * Lay `count` flat-top cells out as a horizontal band `rows` cells deep.
 *
 * Cells fill a column top to bottom before moving to the next column, so two
 * consecutive cells are always neighbours in the comb. That matters because
 * the callers feed these in the order a case runs: step 1's module touches
 * step 2's module, and the eye should be able to follow that without hunting
 * across the band.
 *
 * Columns advance at 3/4 of a cell width and every other column drops by half
 * a cell height, which is what makes the hexagons interlock rather than sit in
 * a grid with gaps at the corners.
 *
 * Positions are computed once and baked into inline styles: the band renders
 * statically, with no measurement pass and nothing to recompute on resize.
 */
export function hiveBand(count: number, cellWidth: number, rows = 2): HiveLayout {
  const cellHeight = Math.round(cellWidth * HEX_ASPECT);
  const columnPitch = Math.round(cellWidth * 0.75);
  const safeRows = Math.max(1, rows);
  const placements: HivePlacement[] = [];
  for (let i = 0; i < Math.max(0, count); i += 1) {
    const column = Math.floor(i / safeRows);
    const rowInColumn = i % safeRows;
    placements.push({
      inlineStart: column * columnPitch,
      // Odd columns are pushed down half a cell. That is the interlock.
      top: rowInColumn * cellHeight + (column % 2) * Math.round(cellHeight / 2),
    });
  }
  // Measure the stage from the cells that are actually there. A band of three
  // is three cells wide, not the width of the row it could have filled.
  const width = placements.length
    ? Math.max(...placements.map((p) => p.inlineStart)) + cellWidth
    : 0;
  const height = placements.length
    ? Math.max(...placements.map((p) => p.top)) + cellHeight
    : 0;
  return { placements, width, height, cellWidth, cellHeight };
}
