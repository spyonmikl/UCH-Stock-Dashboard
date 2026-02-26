# Workflow: [Name]

## Objective
What this workflow accomplishes in one sentence.

## Required Inputs
- `input_1`: Description of what this is and where it comes from
- `input_2`: Description

## Steps

### Step 1: [Action]
- Tool: `tools/script_name.py`
- Input: `input_1`
- Command: `python tools/script_name.py --arg value`
- Output: A file saved to `.tmp/output.json`

### Step 2: [Action]
- Tool: `tools/another_script.py`
- Input: `.tmp/output.json` from Step 1
- Command: `python tools/another_script.py`
- Output: Data written to Google Sheets

## Expected Outputs
- Where final deliverables land (e.g., Google Sheet URL, Slides deck)
- What the data looks like

## Edge Cases & Known Constraints
- Rate limits: e.g., YouTube Data API v3 — 10,000 units/day quota
- Auth: Requires `credentials.json` (Google OAuth) and `token.json` to be present
- If Step 1 fails: check `.tmp/` for partial output before re-running

## Notes
Document anything discovered during runs that future executions should know about.
