# DocToMd Docker Service

A simple Docker-based service to convert documents in `documents/` into Markdown files in `outputs/`.

Supported via `markitdown` first (Microsoft MarkItDown, installed with PDF extras), with `pandoc` as fallback.

## What it does

- Reads source files from `./documents`
- Converts to Markdown (`.md`)
- Writes output files to `./outputs`
- Keeps folder structure
- Can process all files or only selected files (patterns)

## Supported input formats

Common formats include:

- PDF (`.pdf`)
- Word (`.docx`)
- HTML (`.html`, `.htm`)
- OpenDocument (`.odt`)
- Rich Text (`.rtf`)
- Text (`.txt`)
- EPUB (`.epub`)

## Project structure

```text
.
├── Dockerfile
├── docker-compose.yml
├── documents/        # put files to convert here
├── outputs/          # converted markdown appears here
└── service/
    └── convert_service.py
```

## Prerequisites

- Docker
- Docker Compose (v2, usually included as `docker compose`)

## Build and run

### 1) Start watch mode (continuous service)

```bash
docker compose up --build
```

This runs continuously and checks `documents/` every 5 seconds for new/changed files.

### 2) Stop service

```bash
docker compose down
```

## One-time conversion (manual run)

Run the converter once and exit:

```bash
docker compose run --rm doc-to-md --mode once
```

## User-friendly file selection

You can process only selected documents with `--select` patterns.

### Examples

Convert only PDF files:

```bash
docker compose run --rm doc-to-md --mode once --select "*.pdf"
```

Convert one specific file:

```bash
docker compose run --rm doc-to-md --mode once --select "report.docx"
```

Convert files in a subfolder:

```bash
docker compose run --rm doc-to-md --mode once --select "invoices/*.pdf"
```

Combine patterns:

```bash
docker compose run --rm doc-to-md --mode once --select "*.pdf" "*.docx"
```

## Reprocessing files

By default, unchanged files are skipped. To force reprocessing:

```bash
docker compose run --rm doc-to-md --mode once --force
```

You can combine `--force` with `--select`.

## Notes

- Input root: `/workspace/documents`
- Output root: `/workspace/outputs`
- Output filenames keep source paths and change extension to `.md`
