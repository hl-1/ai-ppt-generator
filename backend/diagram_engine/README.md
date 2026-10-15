# Diagram Runtime

The Python backend invokes `engine.mjs` through JSON stdin/stdout. Mermaid parses
authored source; ELK lays out measured nodes and orthogonal edges, including
branches, cycles, condition labels and wrapped layers. The derived point geometry
is saved with each slide and consumed by both the browser and editable PPTX export.

Requires Node.js 22 or newer. Run `npm ci --no-audit --no-fund` here, or `make install`
at the repository root. The API and worker both need this runtime. The backend
Dockerfile installs it in a separate build stage.

After changing the renderer, remeasure an existing project without a model call:

```powershell
cd backend
uv run python -m scripts.repair_visual_layout PROJECT_UUID
uv run python -m scripts.repair_visual_layout PROJECT_UUID --apply
```

The first command writes a local preview. Applying backs up the original slides
and outline under ignored `backend/var/visual-repair/` and skips locked slides.
Table overflow creates continuation slides after generation, keeping outline and
slide order aligned. A single row that cannot fit is an explicit export error.
