# Generated APL Schema

Generated APL documents use schema version `coa-apl-v1`.

## Purpose

Generated APL documents are editable Phase 1 rotation scaffolds. They are canonical structured data. SimC-like text is an export format.

## Required Fields

- `schema_version`
- `source`
- `profile_id`
- `class_name`
- `spec_key`
- `role`
- `encounter`
- `actions`
- `assumptions`
- `warnings`
- `provenance`

## Action Fields

- `action_key`
- `action_name`
- `node_id`
- `spell_id`
- `category`
- `condition`
- `priority`
- `confidence`
- `notes`
- `evidence`

## Source Label

M1.5 uses `source: theorycraft`. Generated APLs must not be labeled as simulated or empirical.
