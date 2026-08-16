# Run contract

The final system will have one command that processes every company in
`challenge/companies.json` and writes the four exact workbooks required by the
organisers.

The pipeline stages are:

1. load and validate the challenge manifest;
2. gather cited evidence from the supplied point-in-time corpus;
3. turn evidence and explicit assumptions into three forecasts per company;
4. validate metric identity, units, ranges and completeness;
5. write only the forecast cells in copies of the supplied workbooks; and
6. save a timestamped, inspectable run record.

The numerical and workbook stages must be deterministic given a saved forecast
record. Failures must be explicit: the runner must not silently omit a company or
metric.

## Current state

The initial runner validates the organiser manifest and creates an auditable run
directory. Retrieval, forecast generation and workbook writing are intentionally
not implemented in the first commit.

