# AEP Failed Batch Recovery Guidance

## Safety boundaries

- Retrieve validation metadata only; do not expose failed customer records.
- Never request credentials in chat or include credentials in an agent response.
- Treat replay, schema modification, mapping modification, and data deletion as approval-required.
- Preserve the batch ID and failed-file name for traceability.

## Common validation categories

- `required`: populate or correctly map the required XDM field.
- `format`: normalize the value to the format required by the XDM schema.
- `type`: convert the source value to the target XDM data type.
- `enum`: map the source value to an allowed schema value.

## Recovery sequence

1. Confirm the batch, sandbox, dataset, and impact scope.
2. List the failed files and select the relevant file.
3. Inspect validation metadata without returning the failed source record.
4. Group errors by keyword and affected XDM pointer.
5. Correct source mapping or transformation in a controlled environment.
6. Validate a small corrected sample.
7. Obtain approval before re-ingestion.
8. Record the original and replacement batch identifiers.

