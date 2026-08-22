# README diagrams

The diagrams on the front page are images rather than fenced `mermaid` blocks,
and each one keeps its source next to it as an `.mmd` file.

## Why they are images

GitHub renders a `mermaid` block inside its own iframe and paints that frame
from the reader's GitHub theme. In dark mode the diagram therefore sits on a
near black canvas. Nothing in the block can change it: the svg mermaid produces
is transparent, so the frame shows through, and setting `background` in
`themeVariables`, or `themeCSS` against the svg or against the diagram id, all
leave the svg transparent. That was measured against mermaid 10 and mermaid 11
on a deliberately black page, and all of them came back transparent.

An image is the one thing whose background we own, so these files carry an
opaque white rectangle behind the diagram and look the same for every reader in
either theme.

## Changing a diagram

Edit the `.mmd` file, then re-render:

```bash
node scripts/render_readme_diagrams.mjs
```

The script reads the fenced blocks from `README.md` when there are any, so if a
diagram is added back to the front page as a fence it will be picked up, written
out here, and the fence replaced. Rendering needs Playwright, which the frontend
workspace already installs, and it fetches mermaid from a CDN at render time
rather than adding it as a dependency.

Check the result before committing: put each file on a black page as an `<img>`
and confirm the corner pixel is white. A file that looks fine in an editor with
a white canvas can still be transparent.
